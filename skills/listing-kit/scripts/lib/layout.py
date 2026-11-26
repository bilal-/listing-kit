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


def app_candidate(folder):
    """Libraries can depend on a mobile SDK without shipping an application."""
    return ((folder / ".listing-kit/listing.json").is_file()
            or (folder / "app.json").is_file()
            or any(folder.glob("app.config.*"))
            or (folder / "lib/main.dart").is_file()
            or any(p.is_dir() for base in (folder, folder / "ios")
                   for pattern in ("*.xcodeproj", "*.xcworkspace") for p in base.glob(pattern))
            or any((base / "app" / gradle).is_file() for base in (folder, folder / "android")
                   for gradle in ("build.gradle", "build.gradle.kts")))


def project(root):
    groups = ["apps/*", "packages/*"]
    workspaces = json_object(root / "package.json").get("workspaces", [])
    if isinstance(workspaces, dict):
        workspaces = workspaces.get("packages", [])
    if isinstance(workspaces, list):
        groups.extend(g for g in workspaces if isinstance(g, str) and g not in ("", ".")
                      and not Path(g).is_absolute() and ".." not in Path(g).parts)
    candidates = sorted({p.relative_to(root).as_posix() for group in groups for p in root.glob(group)
                         if p != root and not p.is_symlink() and p.is_dir() and app_candidate(p)})
    if candidates:
        raise ValueError("Mobile app candidates: {}. Choose one and run inside its app folder."
                         .format(", ".join(candidates)))
    return stack(root)


SHARED = Path("fastlane")
NATIVE = {"apple": Path("ios/fastlane"), "play": Path("android/fastlane")}


def listing_file(store, path):
    parts = path.parts
    image = path.suffix.lower() in (".png", ".jpg", ".jpeg")
    if store == "play":
        screenshot = (len(parts) == 6 and parts[3] == "images"
                      and parts[4].lower().endswith("screenshots") and image)
        return parts[:2] == ("metadata", "android") and (path.suffix == ".txt" or screenshot)
    return ((parts[:1] == ("metadata",) and parts[:2] != ("metadata", "android") and path.suffix == ".txt")
            or (parts[:1] == ("screenshots",) and image))


def holds_listing(root, store, folder):
    base = root / folder
    for subtree in (("metadata", "screenshots") if store == "apple" else ("metadata/android",)):
        for path in (base / subtree).rglob("*"):
            if listing_file(store, path.relative_to(base)) and path.is_file():
                return True
    return False


def fastlane_dir(root, store):
    native = NATIVE[store]
    holders = [folder for folder in (SHARED, native) if holds_listing(root, store, folder)]
    if len(holders) == 2:
        raise ValueError(f"{store} listing content in both {SHARED} and {native}. "
                         f"Set trees.{store}.fastlaneDir in .listing-kit/listing.json.")
    if holders:
        return holders[0]
    if not (root / SHARED / "Fastfile").is_file() and (root / native / "Fastfile").is_file():
        return native
    return SHARED
