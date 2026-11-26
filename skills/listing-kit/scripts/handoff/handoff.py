#!/usr/bin/env python3
"""Build .listing-kit/upload from an app's listing for manual console upload."""

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import apple_assets
import detect
import imginfo
import listing
import rules_check
import screenshots as store_shots
import specs

import handoff_output as output


ASC = "App Store Connect > your app > "
VERSION = ASC + "the version under iOS App (for example 1.0 Prepare for Submission)"
PLAY = "Play Console > your app > "
MAIN_LISTING = PLAY + "Grow users > Store presence > Main store listing"
CATEGORY_NAMES = {
    "FOOD_AND_DRINK": "Food & Drink", "GRAPHICS_AND_DESIGN": "Graphics & Design",
    "HEALTH_AND_FITNESS": "Health & Fitness", "MAGAZINES_AND_NEWSPAPERS": "Magazines & Newspapers",
    "PHOTO_AND_VIDEO": "Photo & Video",
}


class Plan:
    def __init__(self, root):
        self.root = root
        self.trees = listing.paths(root)
        self.missing = []
        self.items = []
        self.omitted = []
        self.paths = set()

    def nonempty(self, path):
        path = Path(path)
        if path.stat().st_size:
            return True
        self.omitted.append("%s — empty file" % path.relative_to(self.root))
        return False

    def add(self, src, dest, place, content=None):
        if dest.is_absolute() or ".." in dest.parts:
            raise ValueError("invalid upload path: %s" % dest)
        key = str(dest).casefold()
        if key in self.paths:
            raise ValueError("two files map to %s" % dest)
        self.paths.add(key)
        self.items.append((src, dest, place, content))


def check_inputs(root, trees):
    """Follow internal links once, including links reached through a locale alias."""
    seen = set()

    def check(path):
        real = path.resolve()
        if root != real and root not in real.parents:
            raise ValueError("listing path points outside the app: %s" % path)
        if real in seen or not real.exists():
            return
        seen.add(real)
        if real.is_dir():
            for child in path.iterdir():
                check(child)
        elif not real.is_file():
            raise ValueError("not a regular listing file: %s" % path)

    for tree in trees.values():
        for key in ("metadata", "screenshots", "storeAssets"):
            check(tree[key])
    for name in (specs.OVERRIDE, ".listing-kit/asset-plan.json"):
        check(root / name)


def child(directory, name):
    if not name or Path(name).name != name or name == "..":
        raise ValueError("invalid store rule path: %s" % name)
    return directory / name


def read_text(path, apple=False):
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("%s: invalid UTF-8 (%s)" % (path, error))
    return raw.strip(b" \t\r\n\v\f\0") if apple else raw


def field_place(store, field, content):
    stem, label = field["stem"], field["label"]
    if store == "play":
        return MAIN_LISTING + " > " + ("App name" if stem == "title" else label)
    page = VERSION
    if stem == "privacy_url":
        page = ASC + "App Privacy"
    elif stem in ("name", "subtitle") or (field["scope"] == "app" and stem != "copyright"):
        page = ASC + "App Information"
    if stem == "release_notes":
        label += " (updates only: not shown for a first version)"
    if field.get("values") == "appleCategories" and content:
        code = content.decode()
        label += " — choose %s from the list" % CATEGORY_NAMES.get(code, code.replace("_", " ").title())
    return page + " > " + label


def text_fields(plan, data, store, directory, base):
    app_wide = base == Path("apple/app-wide")
    for field in specs.fields(data, store):
        if (field["scope"] == "app") != app_wide:
            continue
        name = field["stem"] + ".txt"
        content = read_text(child(directory, name), apple=store == "apple")
        source = ""
        if (content is None and store == "apple" and not app_wide and
                directory.name != "default" and directory.is_dir()):
            content = read_text(directory.parent / "default" / name, apple=True)
            source = " (from default)"
        place = field_place(store, field, content)
        if content and content.strip():
            plan.add(None, base / name, place + source, content)
        elif specs.requirement(field.get("required"), {})[0] == "required":
            plan.missing.append("%s — %s" % (base.parts[1], place))


def screenshot_groups(plan, data, store, locale, deferred=(), suffixes=None):
    groups = defaultdict(list)
    for shot in store_shots.active(plan.root, store, locale, data, deferred, plan.nonempty,
                                   tree=plan.trees[store], suffixes=suffixes):
        if shot.error:
            if not shot.manual:
                raise ValueError("{}: {}x{} matches no App Store slot".format(shot.path, *shot.size))
            raise ValueError(shot.error)
        groups[shot.platform, shot.slot["id"]].append(shot.path)
    return groups


def natural(path):
    return [int(part) if i % 2 else part.lower() for i, part in enumerate(re.split(r"([0-9]+)", path.name))]


def screenshots(plan, data, store, base, groups, place):
    number = 0
    for platform in ("", "iMessage"):
        for slot in specs.slots(data, store):
            paths = groups.get((platform, slot["id"]))
            if not paths:
                continue
            number += 1
            label = (platform + " " if platform else "") + slot["label"]
            safe = re.sub(r'[\\/:*?<>|]', "-", label.replace('"', "in")).strip(" .")
            folder = base / ("%02d %s" % (number, safe))
            for i, path in enumerate(sorted(paths, key=natural if store == "apple" else str), 1):
                name = re.sub(r"^(?:[0-9]+[ ._-]+)+", "", path.stem) + path.suffix
                plan.add(path, folder / ("%02d-%s" % (i, name)), place + " > Screenshots > " + label)


def screenshot_shortfalls(plan, data, store, locale, entry, groups):
    for key, wanted in entry.get("screenshots", {}).items():
        actual = len(groups.get(("", key), ()))
        if actual < wanted:
            label = specs.slot(data, store, key)["label"] if store == "apple" else key
            plan.missing.append(f"{store} {locale}/{label}: {actual} of {wanted} screenshots")


def apple(root, data, plan, coverage):
    tree = plan.trees["apple"]
    meta = tree["metadata"]
    targets = coverage["apple"]
    planned = "play" in coverage
    if planned:
        capture_locales = apple_assets.planned_screenshot_locales(targets)
        requirements = detect.Requirements(root, data)
        requirements.apply_inferred(coverage["inferred"])
    locales = {Path(d).name for d in apple_assets.apple_locales(root, data, targets, tree)}
    if listing.apple_default(meta, data) and not any((meta / loc).is_dir() for loc in locales):
        locales.add("default")
    if apple_assets.has_apple_listing(root, data, locales, tree):
        text_fields(plan, data, "apple", meta, Path("apple/app-wide"))
    for locale in sorted(locales):
        base = Path("apple") / locale
        text_fields(plan, data, "apple", meta / locale, base / "text")
        entry = targets.get(locale, {})
        for display, reason in apple_assets.reported_deferrals(entry, data, planned):
            plan.omitted.append("%s (%s) — %s" % (display, locale, reason))
        deferred_ids = apple_assets.deferred_slots(data, entry.get("deferredScreenshots", {}), planned)
        groups = screenshot_groups(plan, data, "apple", locale, deferred_ids, entry.get("suffixes"))
        if planned and (not capture_locales or locale in capture_locales):
            screenshot_shortfalls(plan, data, "apple", locale, entry, groups)
            counts = {key: len(files) for (platform, key), files in groups.items() if not platform}
            for key in sorted(deferred_ids):
                slot = specs.slot(data, "apple", key)
                if requirements.evaluate(slot["required"])[0] == "required":
                    plan.missing.append(f"cannot defer required screenshot class: {slot['label']} ({locale})")
                for level, message in rules_check.apple_count_rows(slot, counts, requirements, deferred=True):
                    if level == "FAIL":
                        plan.missing.append(f"{locale}: {message}")
        screenshots(plan, data, "apple", base, groups, VERSION)
        headers = data["stores"]["apple"]["graphics"]
        packaged_headers = set()
        for path in apple_assets.header_files(tree, locale):
            if not plan.nonempty(path):
                continue
            size = list(imginfo.image_info(path)[:2])
            variant = next((g for g in headers if g["size"] == size), None)
            if variant is None:
                variant = next((g for g in headers if g["id"] == path.stem.lower()), None)
            label = variant["label"] if variant else "Header Asset (16:9 or 21:9)"
            plan.add(path, base / "graphics" / path.name, ASC + "Product page > " + label)
            packaged_headers.add(path.name)
        if planned:
            for name in entry.get("headers", []):
                if name not in packaged_headers:
                    plan.missing.append(f"Apple header {locale}/{name}: MISSING")


def play_images(plan, directory):
    return [Path(p) for p in listing.images(directory) if plan.nonempty(p)]


def play(root, data, plan, coverage):
    android = plan.trees["play"]["metadata"]
    for locale in listing.play_asset_locales(plan.trees["play"], coverage):
        loc = android / locale
        base = Path("play") / locale
        text_fields(plan, data, "play", loc, base / "text")
        for path in sorted((loc / "changelogs").glob("*.txt")):
            if path.name.startswith("."):
                continue
            raw = read_text(path)
            if raw:
                plan.add(None, base / "text" / ("release-notes-" + path.name),
                         PLAY + "Test and release > your release > Release notes (%s)" % path.stem, raw)
        images = loc / "images"
        graphics = play_images(plan, images)
        packaged_graphics = set()
        for graphic in data["stores"]["play"]["graphics"]:
            matches = [p for p in graphics if p.stem.casefold() == graphic["file"].casefold()]
            if len(matches) > 1:
                raise ValueError("duplicate %s: %s" % (graphic["label"], ", ".join(map(str, matches))))
            if matches:
                path = matches[0]
                plan.add(path, base / "graphics" / path.name, MAIN_LISTING + " > " + graphic["label"])
                packaged_graphics.add(path.name)
        entry = coverage.get(locale, {})
        for name in entry.get("graphics", []):
            if name not in packaged_graphics:
                plan.missing.append(f"Play graphic {locale}/{name}: MISSING")
        groups = screenshot_groups(plan, data, "play", locale)
        screenshot_shortfalls(plan, data, "play", locale, entry, groups)
        screenshots(plan, data, "play", base, groups, MAIN_LISTING)


def build(root):
    root = Path(root).resolve()
    plan = Plan(root)
    with output.locked_upload(root) as destination:
        check_inputs(root, plan.trees)
        data = specs.load(root)
        try:
            coverage = apple_assets.load_coverage(root, data)
            apple(root, data, plan, coverage)
            play(root, data, plan, coverage.get("play", {}))
        except KeyError as error:
            rules = "store rules override" if data.get("_override") else "store rules"
            raise ValueError("%s missing %s" % (rules, error))
        planned_assets = "play" in coverage and (coverage["apple"] or coverage["play"])
        if not plan.items and not (planned_assets and plan.missing):
            raise ValueError("nothing to hand over from %s" % root)
        output.install(destination, plan)
    return str(destination), len(plan.items)


def open_index(path):
    cmd = "open" if sys.platform == "darwin" else "xdg-open"
    if not shutil.which(cmd):
        return False
    streams = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if sys.platform == "darwin":
            return subprocess.call([cmd, path], **streams) == 0
        subprocess.Popen([cmd, path], stdin=subprocess.DEVNULL, start_new_session=True, **streams)
        return True
    except OSError:
        return False


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("root")
    parser.add_argument("--open", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return error.code
    if not os.path.isdir(args.root):
        parser.print_usage(sys.stderr)
        return 2
    try:
        path, count = build(args.root)
    except (OSError, ValueError, RuntimeError, specs.SpecsError) as error:
        print("handoff: %s" % error, file=sys.stderr)
        return 1
    index = str(Path(path) / "INDEX.html")
    print("Upload instructions: %s (%d listing files)." % (index, count))
    if args.open and not open_index(index):
        print("Could not open the instructions. Open the INDEX.html file above.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
