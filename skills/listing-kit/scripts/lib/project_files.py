"""Discover app-owned files used by static platform detection."""

import os
import re
from pathlib import Path

# The installed review hook embeds review_hook.py and runs before the kit is loaded.
from review_hook import skipped_directory


def project_files(root):
    for parent, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not skipped_directory(d))
        for name in sorted(names):
            path = Path(parent) / name
            if (name == "project.pbxproj" and path.parent.suffix == ".xcodeproj"
                    or path.parts[-3:] == ("src", "main", "AndroidManifest.xml")
                    or path.parts[-2:] == ("gradle", "libs.versions.toml")
                    or name in ("build.gradle", "build.gradle.kts", "Info.plist")
                    or path.parent == root and (name == "app.json" or name.startswith("app.config."))):
                yield path


ANDROID = "{http://schemas.android.com/apk/res/android}"
ANDROID_PLUGIN = re.compile(
    r"""(?:(?:\bid\s*\(?|\bapply\s*\(?\s*plugin\s*[:=])\s*["']com\.android\."""
    r"""(?P<kind>application|library|dynamic-feature|test)["'](?:[ \t]*\))?|"""
    r"""\balias\s*\(\s*libs\.plugins\.(?P<alias>[\w.]+)\s*\))"""
    r"""(?:(?:\s*\.\s*|\s+)version\s*(?:\([^)]*\)|["'][^"']*["']|[\w.$-]+))?"""
    r"""(?:(?:\s*\.\s*|\s+)apply\s*\(?\s*(?P<disabled>false)\b)?"""
)


def catalog_plugin(module, alias, root):
    """Read the plugin ID behind a libs.plugins accessor without running Gradle."""
    for folder in (module, *module.parents):
        catalog = folder / "gradle/libs.versions.toml"
        if catalog.is_file():
            in_plugins = False
            for line in catalog.read_text(encoding="utf-8").splitlines():
                line = line.partition("#")[0].strip()
                if line.startswith("["):
                    in_plugins = line == "[plugins]"
                key, _, value = line.partition("=")
                accessor = re.sub(r"[-_]", ".", key.strip().strip("\"'"))
                if in_plugins and accessor == alias:
                    match = re.search(r"""\bid\s*=\s*["']([^"']+)["']""", value)
                    return match[1] if match else value.strip().strip("\"'").partition(":")[0]
            return None
        if (folder == root or (folder / ".git").exists() or (folder / "settings.gradle").is_file()
                or (folder / "settings.gradle.kts").is_file()):
            break
    # A standalone module can be inspected without its workspace catalog.
    for kind in ("application", "library", "test"):
        if alias in ("android." + kind, "android" + kind.title()):
            return "com.android." + kind
    return None


def android_application_plugin(module, root):
    for gradle in (module / "build.gradle", module / "build.gradle.kts"):
        if gradle.is_file():
            source = re.sub(r"/\*.*?\*/|//[^\n]*", "", gradle.read_text(encoding="utf-8"), flags=re.S)
            found_android = False
            for match in ANDROID_PLUGIN.finditer(source):
                plugin = ("com.android." + match["kind"] if match["kind"]
                          else catalog_plugin(module, match["alias"], root))
                if plugin and plugin.startswith("com.android."):
                    found_android = True
                    if plugin == "com.android.application" and not match["disabled"]:
                        return True
            if found_android:
                return False
    return None


def app_manifest(path, doc, root):
    if doc.getroot().tag != "manifest":
        return False
    application = android_application_plugin(path.parents[2], root)
    if application is not None:
        return application
    for tag in ("activity", "activity-alias"):
        for category in doc.findall("application/" + tag + "/intent-filter/category"):
            if category.get(ANDROID + "name") in ("android.intent.category.LAUNCHER",
                                                  "android.intent.category.LEANBACK_LAUNCHER"):
                return True
    return False
