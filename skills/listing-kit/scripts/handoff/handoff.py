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
import imginfo
import listing
import specs

import handoff_output as output


class Plan:
    def __init__(self):
        self.items = []
        self.deferred = []
        self.paths = set()

    def add(self, src, dest, place, content=None):
        if dest.is_absolute() or ".." in dest.parts:
            raise ValueError("invalid upload path: %s" % dest)
        key = str(dest).casefold()
        if key in self.paths:
            raise ValueError("two files map to %s" % dest)
        self.paths.add(key)
        self.items.append((src, dest, place, content))


def check_inputs(root):
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

    for name in ("fastlane/metadata", "fastlane/screenshots", "store-assets/apple",
                 "store-assets/play", specs.OVERRIDE, ".listing-kit/asset-plan.json"):
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


def apple_text(plan, data, meta, locale):
    app_wide = locale is None
    for field in specs.fields(data, "apple"):
        if (field["scope"] == "app") != app_wide:
            continue
        name = field["stem"] + ".txt"
        directory = meta if app_wide else meta / locale
        content = read_text(child(directory, name), apple=True)
        source = ""
        if content is None and not app_wide and locale != "default" and directory.is_dir():
            content = read_text(meta / "default" / name, apple=True)
            source = " (from default)"
        if content:
            page = "Version page"
            if name in ("name.txt", "subtitle.txt") or (app_wide and name != "copyright.txt"):
                page = "App Information"
            elif name == "privacy_url.txt":
                page = "App Privacy"
            base = Path("apple/app-wide") if app_wide else Path("apple") / locale / "text"
            plan.add(None, base / name, page + " > " + field["label"] + source, content)


def apple_slot(data, path, platform):
    w, h = imginfo.image_info(path)[:2]
    slots = specs.apple_slots_for_size(data, w, h)
    if platform == "appleTV":
        slots = [s for s in slots if s["id"] == "apple-tv"]
    if len(slots) > 1:
        suffixes = [s["suffix"] for s in slots]
        # A framed screenshot keeps the slot suffix before the framing suffix.
        stem = re.sub(r"_framed$", "", path.stem.lower())
        matches = [s for s in slots if re.search(r"(?:^|[-_ ])" + re.escape(s["suffix"]) + "$", stem)]
        if len(matches) != 1:
            raise ValueError("%s: ambiguous %sx%s; end the name with %s" % (path, w, h, " or ".join(suffixes)))
        return matches[0]
    if not slots:
        raise ValueError("%s: %sx%s matches no App Store slot" % (path, w, h))
    return slots[0]


def manual(data, root, store, locale, groups, deferred=()):
    for slot_id, name in listing.manual_screenshots(root, store, locale):
        path = Path(name)
        if not path.stat().st_size:
            continue
        slot = specs.slot(data, store, slot_id)
        if not slot:
            raise ValueError("%s: unknown %s slot %s" % (path, store, slot_id))
        if store == "apple" and slot not in specs.apple_slots_for_size(data, *imginfo.image_info(path)[:2]):
            raise ValueError("%s does not fit Apple slot %s" % (path, slot_id))
        if not apple_assets.is_deferred(path, deferred):
            groups["", slot_id].append(path)


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
                name = re.sub(r"^(?:[0-9]+[-_])+", "", path.name)
                plan.add(path, folder / ("%02d-%s" % (i, name)), place + " > Screenshots > " + label)


def apple(root, data, plan):
    meta = root / "fastlane/metadata"
    targets = apple_assets.load_plan(root)
    apple_text(plan, data, meta, None)
    locales = {Path(d).name for d in apple_assets.apple_locales(root, data, targets)}
    if (meta / "default").is_dir() and not any((meta / loc).is_dir() for loc in locales):
        locales.add("default")
    for locale in sorted(locales):
        base = Path("apple") / locale
        apple_text(plan, data, meta, locale)
        groups = defaultdict(list)
        deferred = targets.get(locale, {}).get("deferredScreenshots", {})
        for display, reason in deferred.items():
            plan.deferred.append("- %s (%s) — %s" % (display, locale, reason))
        for platform, name in apple_assets.active_screenshots(root, locale, deferred):
            path = Path(name)
            slot = apple_slot(data, path, platform)
            groups["iMessage" if platform == "iMessage" else "", slot["id"]].append(path)
        manual(data, root, "apple", locale, groups, deferred)
        screenshots(plan, data, "apple", base, groups, "Version page")
        headers = data["stores"]["apple"]["graphics"]
        for path in sorted((root / "store-assets/apple" / locale).glob("*")):
            if (path.name.startswith(".") or not path.is_file() or not path.stat().st_size or
                    path.suffix.lower() not in imginfo.EXTENSIONS + (".mov", ".mp4")):
                continue
            size = list(imginfo.image_info(path)[:2])
            variant = next((g for g in headers if g["size"] == size), None)
            if variant is None:
                variant = next((g for g in headers if g["id"] == path.stem.lower()), None)
            label = variant["label"] if variant else "Header Asset (16:9 or 21:9)"
            plan.add(path, base / "graphics" / path.name, "Product page > " + label)


def play_images(directory):
    return [Path(p) for p in listing.images(directory) if os.path.getsize(p)]


def play(root, data, plan):
    android = root / "fastlane/metadata/android"
    assets = root / "store-assets/play"
    locales = {p.name for d in (android, assets) if d.is_dir() for p in d.iterdir()
               if p.is_dir() and not p.name.startswith(".")}
    for locale in sorted(locales):
        loc = android / locale
        base = Path("play") / locale
        page = "Main store listing"
        for field in specs.fields(data, "play"):
            name = field["stem"] + ".txt"
            raw = read_text(child(loc, name))
            if raw:
                plan.add(None, base / "text" / name, page + " > " + field["label"], raw)
        for path in sorted((loc / "changelogs").glob("*.txt")):
            raw = read_text(path)
            if raw:
                plan.add(None, base / "text" / ("release-notes-" + path.name),
                         "Release > Release notes (%s)" % path.stem, raw)
        images = loc / "images"
        graphics = play_images(images)
        for graphic in data["stores"]["play"]["graphics"]:
            matches = [p for p in graphics if p.stem.casefold() == graphic["file"].casefold()]
            if len(matches) > 1:
                raise ValueError("duplicate %s: %s" % (graphic["label"], ", ".join(map(str, matches))))
            if matches:
                path = matches[0]
                plan.add(path, base / "graphics" / path.name, page + " > " + graphic["label"])
        groups = defaultdict(list)
        for slot in specs.slots(data, "play"):
            if slot.get("folder"):
                groups["", slot["id"]].extend(play_images(child(images, slot["folder"])))
        manual(data, root, "play", locale, groups)
        screenshots(plan, data, "play", base, groups, page)


def build(root):
    root = Path(root).resolve()
    with output.locked_upload(root) as destination:
        check_inputs(root)
        plan = Plan()
        data = specs.load(root)
        try:
            apple(root, data, plan)
            play(root, data, plan)
        except KeyError as error:
            raise ValueError("store rules override is missing %s" % error)
        if not plan.items:
            raise ValueError("nothing to hand over from %s" % root)
        output.install(destination, plan)
    return str(destination), len(plan.items)


def open_folder(path):
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
    print("Upload folder: %s (%d listing files). Open INDEX.md for instructions." % (path, count))
    print("Drag from the opened Finder window or press Cmd+Shift+. in a file picker to show the hidden folder.")
    if args.open and not open_folder(path):
        print("Could not open a file manager. Open the folder above.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
