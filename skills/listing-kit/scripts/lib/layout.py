"""Static app markers and fastlane directory conventions, relative to an app root."""

import json
from pathlib import Path

APPLE = ("apple",)
PLAY = ("play",)
BOTH = APPLE + PLAY


def json_object(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def stack(root):
    ios = root / "ios"
    android = root / "android"
    package = json_object(root / "package.json")
    deps = set()
    for key in ("dependencies", "devDependencies"):
        if isinstance(package.get(key), dict):
            deps.update(package[key])
    if (isinstance(json_object(root / "app.json").get("expo"), dict) or "expo" in deps
            or any((root / ("app.config." + ext)).is_file() for ext in ("json", "ts", "js", "mjs", "cjs"))):
        return ("expo-prebuild" if ios.is_dir() or android.is_dir() else "expo-managed"), BOTH
    if (root / "pubspec.yaml").is_file():
        return "flutter", BOTH
    if "react-native" in deps:
        return "react-native-bare", tuple(s for s, folder in zip(BOTH, (ios, android)) if folder.is_dir()) or BOTH
    if any(p.is_dir() for ext in ("*.xcodeproj", "*.xcworkspace") for p in root.glob(ext)):
        return "native-ios", APPLE
    if any((root / "app" / filename).is_file() for filename in ("build.gradle", "build.gradle.kts")):
        return "native-android", PLAY
    return "unknown", ()


def project(root):
    # Look inside workspace containers before considering dependencies declared
    # at the workspace root. Only app folders own a listing.
    candidates = sorted(p.relative_to(root).as_posix() for group in ("apps", "packages")
                        for p in (root / group).glob("*") if p.is_dir() and stack(p)[1])
    if candidates:
        raise ValueError("Mobile app candidates: {}. Choose one and run inside its app folder."
                         .format(", ".join(candidates)))
    return stack(root)


def fastlane_dirs(root):
    project(root)
    shared = Path("fastlane")
    native = {"apple": Path("ios/fastlane"), "play": Path("android/fastlane")}
    if (root / shared / "Fastfile").is_file():
        return dict.fromkeys(BOTH, shared)

    existing = [p for p in native.values() if (root / p).is_dir()]
    if existing:
        if all((root / p.parent).is_dir() for p in native.values()):
            return native
        if (root / existing[0] / "Fastfile").is_file() or not (root / shared).is_dir():
            shared = existing[0]
    return dict.fromkeys(BOTH, shared)
