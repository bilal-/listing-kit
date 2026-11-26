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

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import specs
from imginfo import format_allowed, apple_class, image_info, validate_many
from listing import apple_locales as listing_apple_locales, has_apple_app_metadata, images



def header_dir(root, locale):
    return os.path.join(root, "store-assets", "apple", locale)


def header_locales(root):
    base = os.path.join(root, "store-assets", "apple")
    if not os.path.isdir(base):
        return []
    return sorted(n for n in os.listdir(base)
                  if not n.startswith(".") and images(os.path.join(base, n)))


def load_plan(root, rules=None):
    plan_path = os.path.join(root, ".listing-kit", "asset-plan.json")
    if not os.path.isfile(plan_path):
        return {}
    rules = rules if rules is not None else specs.load(root)
    header_extensions = {fmt for g in rules["stores"]["apple"]["graphics"] for fmt in g["formats"]}
    if "jpeg" in header_extensions:
        header_extensions.add("jpg")
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
            matching = specs.slot_by_label(rules, "apple", display)
            if not matching or type(expected) is not int or not 1 <= expected <= max(s["max"] for s in matching):
                raise ValueError("unknown display class or invalid screenshot count for " + locale)
        for name in headers:
            if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name)
                    or os.path.splitext(name)[1][1:] not in header_extensions):
                raise ValueError("unsupported header filename; use a basename in an accepted graphic format")
        for display, reason in deferred.items():
            if not specs.slot_by_label(rules, "apple", display) or display in shots:
                raise ValueError("unknown or both active and deferred display class for " + locale)
            if not isinstance(reason, str) or not reason.strip() or len(reason) > 500 or any(ord(c) < 32 for c in reason):
                raise ValueError("deferred screenshot reason must be nonempty single-line text (up to 500 characters)")
    return plan["apple"]


def apple_locales(root, rules=None):
    """Metadata paths for every locale visible in the Apple asset preview."""
    rules = specs.load(root) if rules is None else rules
    try:
        planned = set(load_plan(root, rules))
    except (OSError, ValueError):
        planned = set()  # validate() reports malformed plans separately.
    fastlane = os.path.join(root, "fastlane")
    return sorted(set(listing_apple_locales(fastlane, rules)) | {
        os.path.join(fastlane, "metadata", locale)
        for locale in set(header_locales(root)) | planned | set(console_locales(root, rules))
    })


def has_apple_listing(root, rules=None):
    """True when root has recognized Apple deliver metadata, screenshots, headers, or plan."""
    fastlane = os.path.join(root, "fastlane")
    return bool(
        apple_locales(root)
        or has_apple_app_metadata(fastlane)
        or os.path.isfile(os.path.join(root, ".listing-kit", "asset-plan.json"))
    )


def console_locales(root, rules):
    base = os.path.join(root, "store-assets", "apple")
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if not name.startswith(".") and any(images(os.path.join(base, name, "screenshots", s["id"]))
                                                 for s in specs.slots(rules, "apple")):
                yield name


def screenshot_paths(directory, rules, console=None):
    folders = sorted({s["folder"] for s in specs.slots(rules, "apple") if s.get("folder")})
    paths = images(directory) + [p for folder in folders for p in images(os.path.join(directory, folder))]
    if console is not None:
        for slot in specs.slots(rules, "apple"):
            paths.extend(images(os.path.join(console, slot["id"])))
    return paths


def header_rule(path, info, rules):
    w, h, depth, color = info
    for graphic in rules["stores"]["apple"]["graphics"]:
        alpha = graphic.get("alpha")
        if (graphic["size"] == [w, h] and depth == graphic.get("bitDepth", depth)
                and (color == 2 and alpha != "required" or color == 6 and alpha)
                and format_allowed(path, graphic["formats"])):
            return graphic
    return None


def validate(root, required_displays=(), rules=None, requirements=None):
    rules = rules if rules is not None else specs.load(root)
    headers = rules["stores"]["apple"]["graphics"]
    present = set()
    results = []
    saw_unavailable = False
    header_items = [(locale, path) for locale in header_locales(root) for path in images(header_dir(root, locale))]
    header_statuses = validate_many([path for _, path in header_items], accept=lambda p, info: header_rule(p, info, rules))
    for (locale, path), (info, dec) in zip(header_items, header_statuses):
        w, h, _, _ = info
        graphic = header_rule(path, info, rules)
        if graphic:
            present.add((locale, graphic["id"]))
        if dec == "unavailable":
            saw_unavailable = True
        label = "{}/{}".format(locale, os.path.basename(path))
        if dec.startswith("bad:"):
            results.append(("FAIL", "Apple header {}: {}".format(label, dec[5:])))
        elif not graphic:
            results.append(("FAIL", "Apple header {}: dimensions, format, depth or alpha differ from store header rules".format(label)))
        elif dec.startswith("could not decode:"):
            results.append(("WARN", "Apple header {}: {} ({}x{} RGB/no-alpha)".format(label, dec, w, h)))
        elif dec == "bad":
            results.append(("FAIL", "Apple header {}: image failed full decode".format(label)))
        else:
            results.append(("PASS", "Apple header {}: {}x{} RGB/no-alpha".format(label, w, h)))

    if requirements:
        for locale_path in apple_locales(root, rules):
            locale = os.path.basename(locale_path)
            for graphic in headers:
                level, reason = requirements.evaluate(graphic["required"])
                if level != "optional" and (locale, graphic["id"]) not in present:
                    results.append(("FAIL" if level == "required" else "WARN",
                                    f'{graphic["label"]} MISSING ({locale}) {reason}'.rstrip()))
    try:
        for locale, target in load_plan(root, rules).items():
            shots, headers = target.get("screenshots", {}), target.get("headers", [])
            for display, reason in target.get("deferredScreenshots", {}).items():
                if any(s["label"] in required_displays for s in specs.slot_by_label(rules, "apple", display)):
                    results.append(("FAIL", "cannot defer required screenshot class: {} ({})".format(display, locale)))
                else:
                    results.append(("WARN", "deferred {}/{}: {}".format(locale, display, reason)))
            counts = Counter(apple_class(*image_info(path)[:2], path, rules) for path in screenshot_paths(
                os.path.join(root, "fastlane", "screenshots", locale), rules,
                os.path.join(header_dir(root, locale), "screenshots")))
            for display, expected in shots.items():
                actual = sum(counts[s["label"]] for s in specs.slot_by_label(rules, "apple", display))
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
