#!/usr/bin/env python3
"""Validate Apple headers and explicitly planned upload sets (stdlib only)."""

import json
import os
import re
import sys
from collections import Counter

from imginfo import APPLE_SIZES, apple_class, image_info
from listing import images

HEADER_SIZES = {(5244, 2950), (3840, 1646)}


def header_dir(root, locale):
    return os.path.join(root, "store-assets", "apple", locale)


def header_locales(root):
    base = os.path.join(root, "store-assets", "apple")
    if not os.path.isdir(base):
        return []
    return sorted(n for n in os.listdir(base)
                  if not n.startswith(".") and os.path.isdir(os.path.join(base, n)))


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


def validate(root):
    results = []
    for locale in header_locales(root):
        for path in images(header_dir(root, locale)):
            w, h, depth, color = image_info(path)
            with open(path, "rb") as source:
                is_png = source.read(8) == b"\x89PNG\r\n\x1a\n"
            valid = ((w, h) in HEADER_SIZES and depth == 8 and color == 2
                     and ((w, h) != (5244, 2950) or
                          (is_png and path.lower().endswith(".png"))))
            label = "{}/{}".format(locale, os.path.basename(path))
            results.append(("PASS" if valid else "FAIL", "Apple header {}: {}".format(
                label, "{}x{} RGB/no-alpha".format(w, h) if valid else
                "expected 5244x2950 PNG or 3840x1646 PNG/JPEG, 8-bit RGB/no-alpha")))

    try:
        for locale, target in load_plan(root).items():
            shots, headers = target.get("screenshots", {}), target.get("headers", [])
            for display, reason in target.get("deferredScreenshots", {}).items():
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
    return results


if __name__ == "__main__":
    for level, message in validate(sys.argv[1]):
        print(level + "\t" + message)
