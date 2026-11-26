#!/usr/bin/env python3
"""Where things are in a fastlane listing tree. Shared by validate-listing.sh and
build-review.sh so both see the same locales and images.

CLI:    listing.py {apple-locales|play-locales} <fastlane-dir>
Prints one locale directory per line (apple-locales: metadata/<locale> paths, some
of which may not exist yet when a locale only has screenshots).
"""
import os
import sys

import specs
from imginfo import is_image

SPECIAL_SCREENSHOT_ROOTS = ("appleTV", "iMessage")


def _subdirs(d):
    try:
        return sorted(e for e in os.listdir(d)
                      if not e.startswith(".") and os.path.isdir(os.path.join(d, e)))
    except OSError:
        return []


def apple_screenshot_dirs(fl, locale):
    base = os.path.join(fl, "screenshots")
    return [(kind, os.path.join(base, kind, locale)) for kind in ("",) + SPECIAL_SCREENSHOT_ROOTS]


def apple_locales(fl, data=None):
    meta = os.path.join(fl, "metadata")
    screens = os.path.join(fl, "screenshots")
    excluded = (data or specs.load())["stores"]["apple"]["nonLocaleFolders"]
    names = set(_subdirs(meta)).difference(excluded)
    names.update(set(_subdirs(screens)).difference(SPECIAL_SCREENSHOT_ROOTS))
    for kind in SPECIAL_SCREENSHOT_ROOTS:
        names.update(_subdirs(os.path.join(screens, kind)))
    return [os.path.join(meta, name) for name in sorted(names)]


def apple_default(fl):
    """metadata/default (deliver's fallback values) if present, else None."""
    d = os.path.join(fl, "metadata", "default")
    return d if os.path.isdir(d) else None


def play_locales(fl):
    a = os.path.join(fl, "metadata", "android")
    return [os.path.join(a, n) for n in _subdirs(a)]


def images(d):
    """PNG/JPEG files directly in d (extension case-insensitive), sorted."""
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return []
    return [os.path.join(d, n) for n in names
            if not n.startswith(".") and os.path.isfile(os.path.join(d, n)) and is_image(n)]


def manual_screenshots(root, store, locale):
    base = os.path.join(root, "store-assets", store, locale, "screenshots")
    for slot in _subdirs(base):
        for path in images(os.path.join(base, slot)):
            yield slot, path


if __name__ == "__main__":
    kind, fl = sys.argv[1], sys.argv[2]
    for loc in {"apple-locales": apple_locales, "play-locales": play_locales}[kind](fl):
        print(loc)
