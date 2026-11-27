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
                    or name in ("build.gradle", "build.gradle.kts", "Info.plist")
                    or path.parent == root and (name == "app.json" or name.startswith("app.config."))):
                yield path


ANDROID = "{http://schemas.android.com/apk/res/android}"
ANDROID_PLUGIN = re.compile(
    r"""(?:\bid\s*\(?|\bapply\s*\(?\s*plugin\s*[:=])\s*["']com\.android\."""
    r"""(application|library|dynamic-feature|test)["'][ \t]*\)?"""
    r"""(?:[ \t]+version[ \t]+[^\s}]+)?(?:[ \t]+apply[ \t]+(false))?"""
)


def android_application_plugin(module):
    for gradle in (module / "build.gradle", module / "build.gradle.kts"):
        if gradle.is_file():
            source = re.sub(r"/\*.*?\*/|//[^\n]*", "", gradle.read_text(encoding="utf-8"), flags=re.S)
            plugins = list(ANDROID_PLUGIN.finditer(source))
            if plugins:
                return any(match[1] == "application" and not match[2] for match in plugins)
    return None


def app_manifest(path, doc):
    if doc.getroot().tag != "manifest":
        return False
    application = android_application_plugin(path.parents[2])
    if application is not None:
        return application
    for tag in ("activity", "activity-alias"):
        for category in doc.findall("application/" + tag + "/intent-filter/category"):
            if category.get(ANDROID + "name") in ("android.intent.category.LAUNCHER",
                                                  "android.intent.category.LEANBACK_LAUNCHER"):
                return True
    return False
