"""Discover app-owned files used by static platform detection."""

import os
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
