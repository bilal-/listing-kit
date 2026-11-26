"""Static app markers and fastlane directory conventions, relative to an app root."""

import json
import plistlib
import re
from pathlib import Path
from xml.etree import ElementTree
from xml.parsers.expat import ExpatError

from project_files import android_application_plugin, app_manifest
from xcode_project import application_settings

APPLE = ("apple",)
PLAY = ("play",)
BOTH = APPLE + PLAY


def json_object(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, IsADirectoryError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def dependencies(root):
    package = json_object(root / "package.json")
    deps = set()
    for key in ("dependencies", "devDependencies"):
        if isinstance(package.get(key), dict):
            deps.update(package[key])
    return deps


def stack(root):
    ios = root / "ios"
    android = root / "android"
    deps = dependencies(root)
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


def native_app(folder):
    for base in (folder, folder / "ios"):
        for project in base.glob("*.xcodeproj/project.pbxproj"):
            try:
                for _ in application_settings(project):
                    return True
            except (ValueError, KeyError, TypeError, AttributeError, ExpatError, plistlib.InvalidFileException):
                continue
    for module in (folder / "app", folder / "android/app"):
        manifest = module / "src/main/AndroidManifest.xml"
        if manifest.is_file():
            try:
                if app_manifest(manifest, ElementTree.parse(manifest)):
                    return True
            except ElementTree.ParseError:
                pass
        elif android_application_plugin(module):
            return True
    return False


def app_candidate(folder):
    """A workspace package needs an application declaration or entry point."""
    if (folder / ".listing-kit/listing.json").is_file():
        return True
    config = json_object(folder / "app.json")
    if any(isinstance(data.get("expo"), dict) for data in (config, json_object(folder / "app.config.json"))):
        return True
    deps = dependencies(folder)
    if "expo" in deps and any((folder / ("app.config." + ext)).is_file()
                              for ext in ("js", "ts", "mjs", "cjs")):
        return True
    if "react-native" in deps and config.get("name"):
        return True
    pubspec = folder / "pubspec.yaml"
    if pubspec.is_file() and (folder / "lib/main.dart").is_file():
        if re.search(r"(?m)^\s+sdk:\s*flutter\s*(?:#.*)?$", pubspec.read_text(encoding="utf-8")):
            return True
    return native_app(folder)


def project(root):
    groups = ["apps/*", "packages/*"]
    workspaces = json_object(root / "package.json").get("workspaces", [])
    if isinstance(workspaces, dict):
        workspaces = workspaces.get("packages", [])
    if isinstance(workspaces, list):
        groups.extend(g for g in workspaces if isinstance(g, str) and g not in ("", ".")
                      and not Path(g).is_absolute() and ".." not in Path(g).parts)
    folders = {p for group in groups for p in root.glob(group)
               if p != root and not p.is_symlink() and p.is_dir()}
    if folders and not any(holds_listing(root, store, base)
                           for store, native in NATIVE.items() for base in (SHARED, native)):
        candidates = sorted(p.relative_to(root).as_posix() for p in folders if app_candidate(p))
        if candidates:
            raise ValueError(f"Mobile app candidates: {', '.join(candidates)}. Choose one and run inside "
                             "its app folder, or set trees in the root .listing-kit/listing.json.")
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
    if not (root / native / "Fastfile").is_file() or (root / SHARED / "Fastfile").is_file():
        return SHARED
    other_store = "play" if store == "apple" else "apple"
    return SHARED if holds_listing(root, other_store, SHARED) else native
