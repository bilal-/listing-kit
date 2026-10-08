#!/usr/bin/env python3
"""Read-only Duo preflight. JSON result; exit 0 ready, 3 defer, 2 usage.

Honors DEVELOPER_DIR. Does not install Xcode, boot a device or change a plan.
"""
import argparse
import json
import re
import shutil
import subprocess

DEVICE_TYPE = "com.apple.CoreSimulator.SimDeviceType.iPhone-Duo"
MIN_SDK = (27, 1, 0)


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d+){0,2}", value):
        raise ValueError("unrecognized version")
    parts = tuple(int(n) for n in value.split("."))
    return parts + (0,) * (3 - len(parts))


def run(*args):
    return subprocess.run(["xcrun", *args], check=True, capture_output=True,
                          text=True, timeout=20).stdout.strip()


def probe():
    if not shutil.which("xcrun"):
        return {"status": "deferred", "reason": "Xcode tools are unavailable; Duo capture needs Xcode 27.1+ and a compatible iOS runtime."}
    try:
        sdk = run("--sdk", "iphonesimulator", "--show-sdk-version")
        if version(sdk) < MIN_SDK:
            return {"status": "deferred", "reason": "Selected iOS simulator SDK is {}; Duo capture needs 27.1+.".format(sdk)}
        types = json.loads(run("simctl", "list", "--json", "devicetypes"))["devicetypes"]
        device = next((d for d in types if d["identifier"] == DEVICE_TYPE), None)
        if device is None:
            return {"status": "deferred", "reason": "Selected Xcode does not provide the iPhone Duo simulator device type."}
        minimum = max(MIN_SDK, version(device.get("minRuntimeVersionString", "27.1")))
        maximum = version(device.get("maxRuntimeVersionString", "65535.255.255"))
        runtimes = json.loads(run("simctl", "list", "--json", "runtimes"))["runtimes"]
        compatible = [r for r in runtimes if r.get("isAvailable") is True
                      and r["identifier"].startswith("com.apple.CoreSimulator.SimRuntime.iOS-")
                      and minimum <= version(r["version"]) <= maximum]
        if not compatible:
            return {"status": "deferred", "reason": "No available iOS runtime compatible with the iPhone Duo device type is installed."}
        runtime = max(compatible, key=lambda r: version(r["version"]))
        return {"status": "ready", "sdk": sdk, "deviceType": DEVICE_TYPE,
                "runtime": runtime["identifier"]}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError):
        return {"status": "deferred", "reason": "Could not verify the selected Xcode SDK, Duo device type and runtime; check DEVELOPER_DIR and simctl before capturing."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    result = probe()
    result["target"] = "iPhone Duo"
    print(json.dumps(result))
    raise SystemExit(0 if result["status"] == "ready" else 3)
