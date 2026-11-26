#!/usr/bin/env python3
"""Read-only Duo preflight. JSON result; exit 0 ready, 3 defer, 2 usage.

Honors DEVELOPER_DIR. Does not install Xcode, boot a device or change a plan.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import specs

def version(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d+){0,2}", value):
        raise ValueError("unrecognized version")
    parts = tuple(int(n) for n in value.split("."))
    return parts + (0,) * (3 - len(parts))


def run(*args):
    return subprocess.run(["xcrun", *args], check=True, capture_output=True,
                          text=True, timeout=20).stdout.strip()


def probe(device, threshold):
    min_sdk = version(threshold or "0")
    device_type = "com.apple.CoreSimulator.SimDeviceType." + device.replace(" ", "-")
    if not shutil.which("xcrun"):
        return {"status": "deferred", "reason": f"Xcode tools are unavailable; install the {device} simulator and a compatible iOS runtime."}
    try:
        sdk = run("--sdk", "iphonesimulator", "--show-sdk-version")
        if version(sdk) < min_sdk:
            return {"status": "deferred", "reason": "Selected iOS simulator SDK is {}; Duo capture needs {}+.".format(sdk, threshold)}
        types = json.loads(run("simctl", "list", "--json", "devicetypes"))["devicetypes"]
        device_record = next((d for d in types if d["identifier"] == device_type), None)
        if device_record is None:
            return {"status": "deferred", "reason": f"Selected Xcode does not provide the {device} simulator device type."}
        minimum = max(min_sdk, version(device_record.get("minRuntimeVersionString", threshold or "0")))
        maximum = version(device_record.get("maxRuntimeVersionString", "65535.255.255"))
        runtimes = json.loads(run("simctl", "list", "--json", "runtimes"))["runtimes"]
        compatible = [r for r in runtimes if r.get("isAvailable") is True
                      and r["identifier"].startswith("com.apple.CoreSimulator.SimRuntime.iOS-")
                      and minimum <= version(r["version"]) <= maximum]
        if not compatible:
            return {"status": "deferred", "reason": "No available iOS runtime compatible with the iPhone Duo device type is installed."}
        runtime = max(compatible, key=lambda r: version(r["version"]))
        return {"status": "ready", "sdk": sdk, "deviceType": device_type,
                "runtime": runtime["identifier"]}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError):
        return {"status": "deferred", "reason": "Could not verify the selected Xcode SDK, Duo device type and runtime; check DEVELOPER_DIR and simctl before capturing."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        slot = specs.slot(specs.load("."), "apple", "iphone-duo-outer")
        device = slot["capture"]["deviceType"]
        condition = slot["required"].get("unless", "")
        threshold = condition.split(":", 1)[1] if condition.startswith("iosSdkBelow:") else None
        result = probe(device, threshold)
    except (specs.SpecsError, KeyError, ValueError) as exc:
        parser.exit(2, f"Duo capture rules: {exc}\n")
    result["target"] = device
    print(json.dumps(result))
    raise SystemExit(0 if result["status"] == "ready" else 3)
