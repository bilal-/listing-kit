#!/usr/bin/env python3
"""Where things are in a fastlane listing tree. Shared by validate-listing.sh and
build-review.sh so both see the same locales and images.

CLI:    listing.py {apple-locales|play-locales} <fastlane-dir>
Prints one locale directory per line (apple-locales: metadata/<locale> paths, some
of which may not exist yet when a locale only has screenshots).
"""
import os
import sys

from imginfo import is_image

# deliver folders under metadata/ that are not locales.
NOT_LOCALES = {"android", "default", "review_information", "trade_representative_contact_information"}


def _subdirs(d):
    try:
        return sorted(e for e in os.listdir(d) if os.path.isdir(os.path.join(d, e)))
    except OSError:
        return []


def apple_locales(fl):
    """metadata/<locale> paths: every metadata dir except deliver's non-locale ones,
    plus any locale that only has screenshots (so its missing copy is reported)."""
    meta = os.path.join(fl, "metadata")
    names = {n for n in _subdirs(meta) if n not in NOT_LOCALES}
    names |= set(_subdirs(os.path.join(fl, "screenshots")))
    return [os.path.join(meta, n) for n in sorted(names)]


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
    return [os.path.join(d, n) for n in names if os.path.isfile(os.path.join(d, n)) and is_image(n)]


if __name__ == "__main__":
    kind, fl = sys.argv[1], sys.argv[2]
    for loc in {"apple-locales": apple_locales, "play-locales": play_locales}[kind](fl):
        print(loc)
