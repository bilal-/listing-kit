#!/usr/bin/env python3
"""Validate Apple headers and explicitly planned upload sets (stdlib only).

CLI: apple_assets.py <root> [<required-display> ...]
     apple_assets.py --locales <root>
     apple_assets.py --has-apple <root>
"""

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import specs
from imginfo import APPLE_SIZES, EXTENSIONS, apple_class, image_info, validate_many
from listing import (apple_locales as listing_apple_locales, apple_screenshot_dirs,
                     has_apple_app_metadata, images, manual_screenshots)

HEADER_SIZES = {(5244, 2950), (3840, 1646)}


def header_dir(root, locale):
    return os.path.join(root, "store-assets", "apple", locale)


def header_files(root, locale):
    return sorted(p for p in Path(header_dir(root, locale)).glob("*")
                  if not p.name.startswith(".") and p.is_file() and p.suffix.lower() in EXTENSIONS + (".mov", ".mp4"))


def header_locales(root):
    base = Path(root, "store-assets", "apple")
    return sorted(p.name for p in base.glob("*") if not p.name.startswith(".") and p.is_dir()
                  and (header_files(root, p.name) or any(manual_screenshots(root, "apple", p.name))))


def load_plan(root):
    plan_path = os.path.join(root, ".listing-kit", "asset-plan.json")
    if not os.path.isfile(plan_path):
        return {}
    with open(plan_path, encoding="utf-8") as source:
        plan = json.load(source)
    if not isinstance(plan, dict) or set(plan) != {"apple"} or not isinstance(plan["apple"], dict):
        raise ValueError("expected an object containing an apple locale map")
    if not plan["apple"]:
        raise ValueError("apple locale map is empty")
    for locale, target in plan["apple"].items():
        if not re.fullmatch(r"[A-Za-z0-9_-]+", locale):
            raise ValueError("invalid locale")
        if not isinstance(target, dict) or set(target) - {"screenshots", "headers", "deferredScreenshots"}:
            raise ValueError("invalid target fields " + locale)
        shots, headers = target.get("screenshots", {}), target.get("headers", [])
        deferred = target.get("deferredScreenshots", {})
        if (not isinstance(shots, dict) or not isinstance(headers, list)
                or not isinstance(deferred, dict) or not (shots or headers or deferred)):
            raise ValueError("specify screenshots, headers and/or deferredScreenshots " + locale)
        for display, expected in shots.items():
            if display not in APPLE_SIZES.values() or type(expected) is not int or not 1 <= expected <= 10:
                raise ValueError("unknown display class or invalid screenshot count for " + locale)
        for name in headers:
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+\.(png|jpg|jpeg)", name):
                raise ValueError("header must be a PNG/JPEG basename, not a path")
        for display, reason in deferred.items():
            if display not in APPLE_SIZES.values() or display in shots:
                raise ValueError("unknown or both active and deferred display class for " + locale)
            if not isinstance(reason, str) or not reason.strip() or len(reason) > 500 or any(ord(c) < 32 for c in reason):
                raise ValueError("deferred screenshot reason must be nonempty single-line text (up to 500 characters)")
    return plan["apple"]


def is_deferred(path, deferred):
    return bool(deferred) and apple_class(*image_info(path)[:2]) in deferred


def active_screenshots(root, locale, deferred, data=None, nonempty=os.path.getsize):
    """Yield (deliver platform folder, path) after deliver's framing and plan filters."""
    for platform, directory in apple_screenshot_dirs(os.path.join(root, "fastlane"), locale):
        paths = [p for p in images(directory) if nonempty(p)]
        framed = any(Path(p).stem.lower().endswith("_framed") for p in paths)
        for path in paths:
            name = Path(path).stem.lower()
            if framed and not name.endswith("_framed"):
                # Deliver uses the name, while hand upload uses the Watch console slot.
                watch = ("watch" in name if data is None else
                         any(s["id"] == "watch" for s in specs.apple_slots_for_size(data, *image_info(path)[:2])))
                if not watch:
                    continue
            if is_deferred(path, deferred):
                continue
            yield platform, path


def apple_locales(root, data=None, plan=None):
    """Metadata paths for every locale visible in the Apple asset preview."""
    if plan is None:
        try:
            plan = load_plan(root)
        except (OSError, ValueError):
            plan = {}  # validate() reports malformed plans separately.
    fastlane = os.path.join(root, "fastlane")
    meta = os.path.join(fastlane, "metadata")
    locales = set(listing_apple_locales(fastlane, data))
    locales.update(os.path.join(meta, loc) for loc in set(header_locales(root)) | set(plan))
    return sorted(locales)


def has_apple_listing(root, locales=None, data=None):
    """True when root has recognized Apple deliver metadata, screenshots, headers, or plan."""
    fastlane = os.path.join(root, "fastlane")
    return bool(
        (apple_locales(root, data) if locales is None else locales)
        or has_apple_app_metadata(fastlane, data)
        or os.path.isfile(os.path.join(root, ".listing-kit", "asset-plan.json"))
    )


def _valid_header(path, info):
    w, h, depth, color = info
    if (w, h) not in HEADER_SIZES or depth != 8 or color != 2:
        return False
    if (w, h) == (5244, 2950):
        with open(path, "rb") as source:
            return path.lower().endswith(".png") and source.read(8) == b"\x89PNG\r\n\x1a\n"
    return True


def validate(root, required_displays=()):
    results = []
    saw_unavailable = False
    header_items = [(locale, path) for locale in header_locales(root) for path in images(header_dir(root, locale))]
    header_statuses = validate_many([path for _, path in header_items], accept=_valid_header)
    for (locale, path), (info, dec) in zip(header_items, header_statuses):
        w, h, _, _ = info
        struct_ok = _valid_header(path, info)
        if dec == "unavailable":
            saw_unavailable = True
        label = "{}/{}".format(locale, os.path.basename(path))
        if dec.startswith("bad:"):
            results.append(("FAIL", "Apple header {}: {}".format(label, dec[5:])))
        elif not struct_ok:
            results.append(("FAIL", "Apple header {}: expected 5244x2950 PNG or 3840x1646 PNG/JPEG, 8-bit RGB/no-alpha".format(label)))
        elif dec.startswith("could not decode:"):
            results.append(("WARN", "Apple header {}: {}".format(label, dec)))
        elif dec == "bad":
            results.append(("FAIL", "Apple header {}: image failed full decode".format(label)))
        else:
            results.append(("PASS", "Apple header {}: {}x{} RGB/no-alpha".format(label, w, h)))

    try:
        for locale, target in load_plan(root).items():
            shots, headers = target.get("screenshots", {}), target.get("headers", [])
            for display, reason in target.get("deferredScreenshots", {}).items():
                if display in required_displays:
                    results.append(("FAIL", "cannot defer required screenshot class: {} ({})".format(display, locale)))
                else:
                    results.append(("WARN", "deferred {}/{}: {}".format(locale, display, reason)))
            counts = Counter(apple_class(*image_info(path)[:2]) for path in images(
                os.path.join(root, "fastlane", "screenshots", locale)))
            for display, expected in shots.items():
                actual = counts[display]
                results.append(("PASS" if actual == expected else "FAIL",
                                "planned {}/{}: {} of {} screenshots".format(locale, display, actual, expected)))
            for name in headers:
                exists = os.path.isfile(os.path.join(header_dir(root, locale), name))
                results.append(("PASS" if exists else "FAIL", "planned Apple header {}/{}: {}".format(
                    locale, name, "present" if exists else "MISSING")))
    except (OSError, ValueError) as error:
        results.append(("FAIL", "asset-plan.json: " + str(error)))
    if saw_unavailable:
        results.append(("IM_UNAVAILABLE", "images were checked structurally only"))
    return results


if __name__ == "__main__":
    if sys.argv[1] == "--locales":
        for path in apple_locales(sys.argv[2]):
            print(path)
    elif sys.argv[1] == "--has-apple":
        print("1" if has_apple_listing(sys.argv[2]) else "0")
    else:
        for level, message in validate(sys.argv[1], sys.argv[2:]):
            print(level + "\t" + message)
