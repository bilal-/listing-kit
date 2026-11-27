#!/usr/bin/env python3
"""Drive installed apps and capture the selected jobs from a listing-kit plan."""
import argparse
from collections import Counter, deque
import errno
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
import imginfo
import json_input
import plan


class CaptureError(Exception):
    pass


class MissingTool(CaptureError):
    pass


def required(name, hint):
    if not shutil.which(name):
        raise MissingTool(f"{name} is missing. {hint}")


def run_tool(args, *, flow=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=None):
    setting, default = ("LK_CAPTURE_TIMEOUT", 600) if flow else ("LK_TOOL_TIMEOUT", 120)
    try:
        timeout = float(os.environ.get(setting, default))
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError
    except ValueError:
        raise CaptureError(f"{setting} must be a positive number of seconds.") from None

    # Shell helpers and Maestro can spawn children that keep pipes or devices open.
    with subprocess.Popen(args, cwd=cwd, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                          start_new_session=True) as proc:
        try:
            output, errors = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            label = Path(args[1] if args[0] == "bash" else args[0]).name
            raise CaptureError(f"{label} timed out after {timeout:g} seconds ({setting}).") from None
        return subprocess.CompletedProcess(args, proc.returncode, output, errors)


def command(*args, stdout=subprocess.PIPE, stderr=subprocess.PIPE):
    result = run_tool(args, stdout=stdout, stderr=stderr)
    if result.returncode:
        message = (result.stderr or b"").decode("utf-8", "replace").strip()
        raise CaptureError(f"{Path(args[0]).name} exited {result.returncode}: {message}")
    if stdout == subprocess.PIPE:
        return result.stdout.decode("utf-8", "replace").strip()


def ios_inventory():
    try:
        inventory = json.loads(command("xcrun", "simctl", "list", "devices", "available", "-j"))["devices"]
        devices = [(runtime, d) for runtime, group in inventory.items() for d in group
                   if d.get("isAvailable", True)]
        # Simulator names are editable. Modern simctl reports the immutable type ID.
        types = {}
        if any(d.get("deviceTypeIdentifier") for _, d in devices):
            rows = json.loads(command("xcrun", "simctl", "list", "devicetypes", "-j"))["devicetypes"]
            types = {row["identifier"]: row["name"] for row in rows}
        return [(runtime, types.get(d.get("deviceTypeIdentifier"), d["name"]), d["udid"], d["state"])
                for runtime, d in devices]
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise CaptureError(f"Could not read simulator inventory: {exc}") from exc


def ios_device(job, pin, dry_run):
    available = set()
    candidates = []
    wanted = job["deviceType"]
    runtime = job["runtime"]
    for runtime_id, name, udid, state in ios_inventory():
        available.add(name)
        version = runtime_id.rsplit("iOS-", 1)[-1].replace("-", ".")
        if runtime and runtime not in (runtime_id, version, "iOS " + version):
            continue
        if (not wanted or name == wanted) and (not pin or pin == udid):
            if state in ("Booted", "Shutdown"):
                candidates.append((state, udid))

    if not wanted and not pin:
        raise CaptureError("set capture.deviceType or select an iOS simulator with --device")
    if not candidates:
        label = wanted or pin
        create = "xcrun simctl create " + shlex.quote(label) + " " + shlex.quote(label)
        if runtime:
            create += " " + shlex.quote(runtime)
        raise CaptureError(f"No available simulator matches {label} (device {pin or 'auto'}, "
                           f"runtime {runtime or 'any'}). Available types: "
                           f"{', '.join(sorted(available)) or 'none'}. To create one: {create}")
    state, udid = min(candidates, key=lambda item: item[0] != "Booted")
    if not dry_run and state == "Shutdown":
        command("xcrun", "simctl", "boot", udid)
        command("xcrun", "simctl", "bootstatus", udid, "-b")
    return udid


def avd_value(serial, field):
    result = run_tool(("adb", "-s", serial, "emu", "avd", field))
    if result.returncode == 0:
        for line in result.stdout.decode("utf-8", "replace").splitlines():
            value = line.strip()
            if value and value != "OK" and not value.startswith("KO:"):
                return value
    return ""


def android_profile(serial):
    directory = avd_value(serial, "path")
    if directory and Path(directory).is_absolute():
        try:
            with (Path(directory) / "config.ini").open(encoding="utf-8", errors="replace") as config:
                for line in config:
                    key, sep, value = line.partition("=")
                    if sep and key.strip() == "hw.device.name" and value.strip():
                        return value.strip()
        except OSError:
            pass
    return avd_value(serial, "name")


def android_device(job, pin, allow_device):
    serials = [parts[0] for parts in (line.split() for line in command("adb", "devices").splitlines())
               if len(parts) >= 2 and parts[1] == "device"]
    emulators = [s for s in serials if s.startswith("emulator-")]
    if pin and pin not in serials:
        raise CaptureError(f"{pin} is offline or absent. Online Android devices: {', '.join(serials) or 'none'}")
    if pin:
        if pin in emulators or allow_device:
            return pin
    elif emulators:
        profiles = {serial: android_profile(serial) for serial in emulators}
        wanted = job["deviceType"] or ""
        matches = [s for s, profile in profiles.items() if profile and profile.casefold() == wanted.casefold()]
        if len(matches) == 1:
            return matches[0]
        listing = ", ".join(f"{s} ({profile or 'unknown'})" for s, profile in profiles.items())
        raise CaptureError(f"Expected one emulator matching {wanted or 'capture.deviceType'}. "
                           f"Running emulators: {listing}. Please start the right emulator "
                           "or pin one with --device or .listing-kit/local.json.")
    elif allow_device and len(serials) == 1:
        return serials[0]
    elif not serials:
        raise CaptureError(f"Running emulators: none. Please start an emulator for {job['deviceType']} "
                           "or pin an online device with --device or .listing-kit/local.json.")
    elif allow_device:
        raise CaptureError("Select --device from " + ", ".join(serials))
    raise CaptureError(f"Physical Android device ({pin or ', '.join(serials)}) requires --allow-device "
                       "because capture can clear app data and enable demo mode.")


def prepare(job, pin, args):
    ios = job["store"] == "apple"
    if ios:
        required("xcrun", "Please install Xcode and the iOS Simulator tools.")
    else:
        required("adb", "Please install Android SDK Platform-Tools.")
    magick = shutil.which("magick") or shutil.which("convert")
    if not args.dry_run:
        if not args.manual:
            required("maestro", "Please install Maestro CLI and JDK 17+.")
        if not magick or os.environ.get("LK_NO_IMAGEMAGICK"):
            raise MissingTool("ImageMagick is missing. Run brew install imagemagick or apt install imagemagick.")
    device = ios_device(job, pin, args.dry_run) if ios else android_device(job, pin, args.allow_device)
    if not args.dry_run:
        app = job["appId"]
        if not app:
            raise CaptureError("Set the app ID in the listing plan before capture.")
        probe = (("xcrun", "simctl", "get_app_container", device, app) if ios else
                 ("adb", "-s", device, "shell", "pm", "path", app))
        result = run_tool(probe)
        installed = (result.stdout.strip() if ios else
                     any(path.startswith(b"package:") for path in result.stdout.splitlines()))
        if result.returncode or not installed:
            raise CaptureError(f"Could not find {app} on {device}. Please build and install it first "
                               "(see references/stacks/).")
    return device, magick


def check_flow_app(path, app_id):
    # The Maestro config is the first YAML document. Inspect its top-level appId,
    # leaving command arguments and other nested appId keys to Maestro.
    indent = None
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            field = line.strip()
            if not field or field.startswith(("#", "%")):
                continue
            if re.fullmatch(r"---(?:\s+#.*)?", field):
                if indent is not None:
                    break
                continue
            level = len(line) - len(line.lstrip())
            if indent is None:
                indent = level
            if level != indent:
                continue
            key, _, value = field.partition(":")
            if key.strip().strip("'\"") != "appId":
                continue
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if "${" not in value and value != app_id:
                raise CaptureError(f"{path.name} declares appId {value!r}, but the job requires {app_id!r}.")
            break


def drive(job, root, device):
    target, screen, locale = job["targetId"], job["screenId"], job["localeId"]
    check_flow_app(root / job["flowPath"], job["appId"])
    folder = root / ".listing-kit/logs" / target
    if root not in folder.resolve().parents:
        raise CaptureError(f"log directory escapes app root: {folder}")
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / f"{screen}.{locale}.log"
    args = ["maestro", "--device", device, "test", job["flowPath"], "-e", "LK_APP_ID=" + job["appId"],
            "-e", "LK_LOCALE=" + job["deviceLocale"],
            "-e", "LK_TARGET=" + target, "-e", "LK_SCREEN=" + screen]
    with tempfile.TemporaryDirectory(dir=folder) as tmp:
        staged = Path(tmp) / "maestro.log"
        with staged.open("wb") as stream:
            try:
                result = run_tool(args, flow=True, cwd=root, stdout=stream, stderr=subprocess.STDOUT)
            except CaptureError as exc:
                raise CaptureError(f"{exc} Log: {log}") from exc
            finally:
                staged.replace(log)
    if result.returncode:
        with log.open(encoding="utf-8", errors="replace") as stream:
            tail = "".join(deque(stream, maxlen=15)).rstrip()
        raise CaptureError(f"Maestro exited {result.returncode}. Log: {log}\n{tail}")


def dimensions(size):
    return "%dx%d" % tuple(size)


def check_frame(size, job, row):
    w, h = size
    if not w or not h:
        raise CaptureError("Invalid screenshot image")
    native = job["nativeSize"]
    swapped = native and w != h and [h, w] == native
    if swapped or (w != h and ("landscape" if w > h else "portrait") != job["orientation"]):
        raise CaptureError(f"{dimensions(size)} has the wrong orientation. "
                           f"Set {job['orientation']} in the flow.")
    if row["styleMode"] == "raw" and list(size) != row["size"]:
        raise CaptureError(f"Capture is {dimensions(size)}. A raw upload requires the exact target size "
                           f"{dimensions(row['size'])}. Select a matching device profile.")
    if job["nativeSize"] and list(size) != job["nativeSize"]:
        raise CaptureError(f"Capture is {dimensions(size)}, expected native size {dimensions(job['nativeSize'])}.")


def capture_size(job, row, device):
    native = job["nativeSize"] or (row["size"] if row["styleMode"] == "raw" else None)
    if job["store"] == "apple" and not native:
        raise CaptureError("Set capture.nativeSize for this simulator display.")
    if job["store"] == "play" and job["nativeSize"]:
        output = command("adb", "-s", device, "shell", "wm", "size")
        sizes = dict(re.findall(r"(?m)^\s*(Physical|Override) size:\s*(\d+x\d+)\s*$", output))
        actual = sizes.get("Override") or sizes.get("Physical")
        if not actual:
            raise CaptureError(f"Could not read wm size on {device}: {output}")
        # wm reports the base display axes regardless of the flow's orientation.
        if sorted(map(int, actual.split("x"))) != sorted(job["nativeSize"]):
            raise CaptureError(f"{device} wm size is {actual}, expected native size {dimensions(job['nativeSize'])}.")
    return native


def capture(job, row, root, device, magick, manual, native):
    ios = job["store"] == "apple"
    if ios:
        app = job["appId"]
        stopped = run_tool(("xcrun", "simctl", "terminate", device, app))
        # simctl returns ESRCH when the installed app is already stopped.
        if stopped.returncode not in (0, errno.ESRCH):
            raise CaptureError(f"Could not terminate {app}: {stopped.stderr.decode('utf-8', 'replace').strip()}")
        command("xcrun", "simctl", "launch", device, app)
    if manual:
        print(f"Navigate to {job['screenId']} ({job['deviceLocale']}) on {device}, "
              "then press Enter to capture.", file=sys.stderr, flush=True)
        if not sys.stdin.readline():
            raise CaptureError("Manual capture received no confirmation.")
    else:
        drive(job, root, device)
    command("bash", HERE / "sanitize-status-bar.sh", "ios" if ios else "android", device,
            stdout=None, stderr=None)
    dest = root / job["rawPath"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        ready = Path(tmp) / "ready.png"
        if ios:
            # capture-ios validates and normalizes into our staging directory.
            try:
                command("bash", HERE / "capture-ios.sh", device, job["display"] or "internal",
                        dimensions(native), ready)
            except CaptureError as exc:
                if row["styleMode"] == "raw":
                    raise CaptureError(f"{exc} This raw upload requires {dimensions(row['size'])}.") from exc
                raise
            check_frame(imginfo.image_info(ready)[:2], job, row)
        else:
            frame = Path(tmp) / "frame.png"
            with frame.open("wb") as stream:
                command("adb", "-s", device, "exec-out", "screencap", "-p", stdout=stream)
            check_frame(imginfo.image_info(frame)[:2], job, row)
            variation = float(command(magick, frame, "-alpha", "off", "-format", "%[fx:standard_deviation]", "info:"))
            if not math.isfinite(variation) or variation <= 0:
                raise CaptureError("Blank or solid Android screenshot. Wait for app content.")
            command("bash", HERE / "normalize-screenshot.sh", frame, ready)
        ready.replace(dest)


def select_jobs(manifest, args, selected):
    outputs = manifest["outputs"]
    for option, values, key in (("--target", args.target, "targetId"), ("--screen", args.screen, "screenId")):
        unknown = set(values) - {row[key] for row in outputs}
        if unknown:
            raise ValueError(f"{option} has no active output for {', '.join(sorted(unknown))}")
    groups = {}
    for job in manifest["captures"]:
        if selected(job):
            groups.setdefault(job["targetId"], []).append(job)
    if not groups:
        raise ValueError("No capture jobs match the selected targets and screens.")
    return groups


def device_pins(root):
    path = root / ".listing-kit/local.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as stream:
        data = json_input.read(stream)
    pins = data.get("devices", {}) if isinstance(data, dict) else None
    if not isinstance(pins, dict) or not all(isinstance(v, str) and v.strip() for v in pins.values()):
        raise ValueError(f"{path}: expected a devices object mapping target IDs to device IDs")
    return pins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app_root", type=Path)
    parser.add_argument("--target", action="append", default=[], metavar="ID")
    parser.add_argument("--screen", action="append", default=[], metavar="ID")
    parser.add_argument("--device", metavar="UDID_OR_SERIAL")
    parser.add_argument("--allow-device", action="store_true", help="allow physical Android devices")
    parser.add_argument("--dry-run", action="store_true", help="show jobs and device choices using read-only discovery")
    parser.add_argument("--keep-going", action="store_true", help="continue after a job fails")
    parser.add_argument("--manual", action="store_true", help="wait for manual navigation before each capture")
    args = parser.parse_args()
    root = args.app_root.resolve()

    def selected(job):
        return ((not args.target or job["targetId"] in args.target)
                and (not args.screen or job["screenId"] in args.screen))

    try:
        manifest = plan.load_manifest(root, purpose="capture", capture_filter=selected)
        groups = select_jobs(manifest, args, selected)
        pins = device_pins(root)
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2
    rows = {r["rawPath"]: r for r in manifest["outputs"] if r["rawPath"]}
    counts = Counter()
    status = 0
    for target, jobs in groups.items():
        setup_error = None
        if not status or args.keep_going:
            try:
                device, magick = prepare(jobs[0], args.device or pins.get(target), args)
            except (CaptureError, OSError, ValueError) as exc:
                setup_error = exc
        for job in jobs:
            label = "/".join(job[k] for k in ("targetId", "screenId", "localeId"))
            if status and not args.keep_going:
                action, detail = "skipped", "stopped after failure"
            else:
                try:
                    if setup_error:
                        raise setup_error
                    detail = f"{device} {job['flowPath']} -> {job['rawPath']}"
                    row = rows[job["rawPath"]]
                    native = capture_size(job, row, device)
                    if args.dry_run:
                        action = "planned"
                    else:
                        capture(job, row, root, device, magick, args.manual, native)
                        if row["styleMode"] == "raw":
                            detail += f" (raw upload {dimensions(row['size'])})"
                        action = "captured"
                except (CaptureError, OSError, ValueError) as exc:
                    action, detail = "failed", str(exc)
                    status = max(status, 3 if isinstance(exc, MissingTool) else 1)
            print(f"{action} {label}: {detail}", flush=True)
            counts[action] += 1
    success = "planned" if args.dry_run else "captured"
    print(f"Summary: {counts[success]} {success}, {counts['failed']} failed, {counts['skipped']} skipped")
    return status


if __name__ == "__main__":
    sys.exit(main())
