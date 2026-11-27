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

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import plan as listing_plan
import screenshots
import specs
from imginfo import EXTENSIONS, format_allowed, image_info, validate_many
from listing import (paths, apple_locales as listing_apple_locales,
                     has_apple_app_metadata, images)


def header_dir(tree, locale):
    return tree["storeAssets"] / locale


def header_files(tree, locale):
    return sorted(p for p in Path(header_dir(tree, locale)).glob("*")
                  if not p.name.startswith(".") and p.is_file() and p.suffix.lower() in EXTENSIONS + (".mov", ".mp4"))


def header_locales(tree):
    base = tree["storeAssets"]
    return sorted(p.name for p in base.glob("*") if not p.name.startswith(".") and p.is_dir()
                  and (header_files(tree, p.name) or (p / "screenshots").is_dir()))


LEGACY = Path(".listing-kit/asset-plan.json")


def load_coverage(root, rules=None, view=None):
    """Read a private view snapshot, the listing plan, or the older Apple-only plan."""
    rules = rules if rules is not None else specs.load(root)
    if view:
        with open(view, encoding="utf-8") as source:
            snapshot = json.load(source)
        if snapshot is not None:
            return snapshot
    elif (Path(root) / listing_plan.LISTING).is_file():
        data = listing_plan.read_listing(Path(root).resolve())
        manifest = listing_plan.manifest(data, rules, root)
        return planned_coverage(root, data, rules, manifest["outputs"])
    return {"apple": load_legacy(root, rules)}


def planned_coverage(root, data, rules, outputs, publish_store=None, text_locales=()):
    disk = set()
    if listing_plan.targets(data, "apple", "deferred"):
        tree = paths(root)["apple"]
        disk.update(Path(loc).name for loc in listing_apple_locales(tree, rules, files_only=True))
        disk.update(loc for loc in header_locales(tree) if header_files(tree, loc)
                    or any(images(folder) for folder in (header_dir(tree, loc) / "screenshots").glob("*")))
    result = listing_plan.coverage(data, rules, outputs, publish_store, disk_apple=disk, text_locales=text_locales)
    if not publish_store:
        result["descriptions"] = {row["outputPath"]: row["text"]["altText"]["value"]
                                  for row in outputs if "altText" in row["text"]}
        result["console"] = data.get("console", {})
    return result


def load_plan(root, rules=None):
    return load_coverage(root, rules)["apple"]


def load_legacy(root, rules=None):
    plan_path = Path(root) / LEGACY
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


def legacy_advisory(root, rules, coverage):
    prefix = "asset-plan.json is ignored for coverage. Other tooling in this repository may still use it."
    try:
        legacy = load_legacy(root, rules)
    except (OSError, ValueError) as exc:
        return "WARN", f"{prefix} Cannot compare declarations: {exc}"
    lost = []
    for locale, entry in legacy.items():
        modern = coverage.get(locale, {})
        for name in entry.get("headers", []):
            if name not in modern.get("headers", []):
                lost.append(f"{locale}/{name}")
        for label, count in entry.get("screenshots", {}).items():
            ids = deferred_slots(rules, [label])
            if sum(modern.get("screenshots", {}).get(key, 0) for key in ids) != count:
                lost.append(f"{locale}/{label} ({count} screenshots)")
        for label, reason in entry.get("deferredScreenshots", {}).items():
            if any(modern.get("deferredScreenshots", {}).get(key) != reason
                   for key in deferred_slots(rules, [label])):
                lost.append(f"{locale}/{label} (deferred: {reason})")
    if lost:
        return "WARN", prefix + " listing.json does not cover: " + ", ".join(lost)
    return "NOTE", prefix + " Its declarations are covered by listing.json."


def display_name(rules, key, planned):
    return specs.slot(rules, "apple", key)["label"] if planned else key


def reported_deferrals(entry, rules, planned):
    for key, reason in entry.get("deferredScreenshots", {}).items():
        yield display_name(rules, key, planned), reason
    yield from entry.get("deferredTargets", {}).items()


def planned_screenshot_locales(targets):
    return {code for code, entry in targets.items() if entry.get("screenshots")}


def deferred_slots(rules, displays, planned=False):
    if planned:
        return set(displays)
    return {s["id"] for label in displays for s in specs.slot_by_label(rules, "apple", label)}


def apple_locales(root, rules=None, plan=None, tree=None):
    """Metadata paths for every locale visible in the Apple asset preview."""
    rules = rules if rules is not None else specs.load(root)
    if plan is None:
        try:
            plan = load_plan(root, rules)
        except (OSError, ValueError):
            plan = {}  # validate() reports malformed plans separately.
    tree = tree if tree is not None else paths(root)["apple"]
    meta = tree["metadata"]
    locales = set(listing_apple_locales(tree, rules))
    locales.update(os.path.join(meta, loc) for loc in set(header_locales(tree)) | set(plan))
    return sorted(locales)


def has_apple_listing(root, rules=None, locales=None, tree=None):
    """True when root has recognized Apple deliver metadata, screenshots, headers, or plan."""
    tree = tree if tree is not None else paths(root)["apple"]
    rules = rules if rules is not None else specs.load(root)
    return bool(
        (apple_locales(root, rules, tree=tree) if locales is None else locales)
        or has_apple_app_metadata(tree["metadata"], rules)
        or (not (Path(root) / listing_plan.LISTING).is_file() and (Path(root) / LEGACY).is_file())
    )


def header_rule(path, info, rules):
    w, h, depth, color = info
    for graphic in rules["stores"]["apple"]["graphics"]:
        alpha = graphic.get("alpha")
        if (graphic["size"] == [w, h] and depth == graphic.get("bitDepth", depth)
                and (color == 2 and alpha != "required" or color == 6 and alpha)
                and format_allowed(path, graphic["formats"])):
            return graphic
    return None


def validate(root, required_displays=(), rules=None, requirements=None, tree=None, coverage=None, planned=False):
    tree = tree if tree is not None else paths(root)["apple"]
    rules = rules if rules is not None else specs.load(root)
    headers = rules["stores"]["apple"]["graphics"]
    present = set()
    results = []
    saw_unavailable = False
    header_items = [(locale, path) for locale in header_locales(tree) for path in images(header_dir(tree, locale))]
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
        for locale_path in apple_locales(root, rules, coverage, tree):
            locale = os.path.basename(locale_path)
            for graphic in headers:
                level, reason = requirements.evaluate(graphic["required"])
                if level == "upcoming" and "from" not in graphic["required"] and not requirements.verbose:
                    continue
                if level != "optional" and (locale, graphic["id"]) not in present:
                    results.append(("FAIL" if level == "required" else "WARN",
                                    f'{graphic["label"]} MISSING ({locale}) {reason}'.rstrip()))
    try:
        if coverage is None:
            snapshot = load_coverage(root, rules)
            planned = "play" in snapshot
            coverage = snapshot["apple"]
            if planned:
                required_displays = deferred_slots(rules, required_displays)
        capture_locales = planned_screenshot_locales(coverage) if planned else set()
        for locale, target in coverage.items():
            shots, headers = target.get("screenshots", {}), target.get("headers", [])
            for key, reason in target.get("deferredScreenshots", {}).items():
                display = display_name(rules, key, planned)
                required = (key in required_displays if planned else any(
                    s["label"] in required_displays for s in specs.slot_by_label(rules, "apple", key)))
                if required and (not capture_locales or locale in capture_locales):
                    results.append(("FAIL", f"cannot defer required screenshot class: {display} ({locale})"))
                else:
                    results.append(("WARN", f"deferred {locale}/{display}: {reason}"))
            for target_id, reason in target.get("deferredTargets", {}).items():
                results.append(("WARN", f"deferred {locale}/{target_id}: {reason}"))
            deferred = deferred_slots(rules, target.get("deferredScreenshots", {}), planned)
            counts = Counter(shot.slot["id" if planned else "label"] for shot in screenshots.active(
                root, "apple", locale, rules, deferred, tree=tree, suffixes=target.get("suffixes"))
                if not shot.error and not shot.platform)
            for key, expected in shots.items():
                display = display_name(rules, key, planned)
                actual = counts[key] if planned else sum(counts[s["label"]] for s in specs.slot_by_label(rules, "apple", key))
                prefix = f"planned {locale}/{display}: "
                if expected == 0:
                    results.append(("WARN", prefix + "nothing planned yet"))
                else:
                    results.append(("PASS" if actual == expected else "FAIL", prefix + f"{actual} of {expected} screenshots"))
            for name in headers:
                exists = os.path.isfile(os.path.join(header_dir(tree, locale), name))
                results.append(("PASS" if exists else "FAIL", "planned Apple header {}/{}: {}".format(
                    locale, name, "present" if exists else "MISSING")))
    except (OSError, ValueError) as error:
        name = listing_plan.LISTING if (Path(root) / listing_plan.LISTING).is_file() else LEGACY
        results.append(("FAIL", name.name + ": " + str(error)))
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
