#!/usr/bin/env python3
"""Build a folder for uploading a listing by hand, sorted the way the consoles ask.

fastlane needs Apple screenshots in one flat folder per locale. That is awkward to
upload from by hand, so this writes a throwaway copy organised by store, locale and
console slot, with the text fields, graphics and an index:

  <app-root>/.listing-kit/upload/
    INDEX.md
    apple/<locale>/01 iPhone Dynamic Island (medium display)/01-home_iphone-medium.png
    apple/<locale>/text/name.txt ...
    apple/<locale>/graphics/header-16x9.png
    play/<locale>/01 Phone/01-home.png
    play/<locale>/graphics/icon.png  featureGraphic.png
    play/<locale>/text/title.txt ...

The fastlane tree stays the source. The folder is built in a temporary directory and
swapped in only when complete. Standard library only.

Usage: handoff.py <app-root> [--out <dir>] [--open]
Exit:  0 built, 1 nothing to hand over or a file could not be placed, 2 usage.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path, PureWindowsPath

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
import apple_assets
import imginfo
import listing
import specs
import handoff_output as output

OUT_REL = Path(".listing-kit/upload")


class Plan:
    def __init__(self):
        self.items = []
        self.problems = []

    def add(self, src, dest, place, content=None):
        self.items.append((src, dest, place, content))


def _check_inputs(root):
    """Reject links before discovery helpers can traverse them, including config links."""
    def check(path):
        if output.is_link(path):
            raise ValueError("symlink in listing: %s" % path)
        if path.exists() and not (path.is_dir() or path.is_file()):
            raise ValueError("not a regular listing file: %s" % path)

    def raise_error(error):
        raise error

    for name in ("fastlane", "store-assets", ".listing-kit", specs.OVERRIDE, ".listing-kit/asset-plan.json"):
        check(root / name)
    for name in ("fastlane/metadata", "fastlane/screenshots", "store-assets/apple", "store-assets/play"):
        base = root / name
        check(base)
        if base.exists():
            for directory, dirs, files in os.walk(base, onerror=raise_error):
                for entry in dirs + files:
                    check(Path(directory) / entry)


def _check_rules(data):
    def basename(value):
        if (not isinstance(value, str) or value in ("", ".", "..") or "/" in value
                or "\\" in value or "\0" in value or PureWindowsPath(value).drive):
            raise ValueError("invalid path component in store rules: %r" % value)

    for store in ("apple", "play"):
        for field in specs.fields(data, store):
            basename(field["stem"])
        for slot in specs.slots(data, store):
            basename(slot["id"])
            if slot.get("folder") is not None:
                basename(slot["folder"])
    for graphic in data["stores"]["play"]["graphics"]:
        basename(graphic["file"])


def _read(path, apple=False):
    try:
        with output.open_source(path) as source:
            raw = source.read()
    except FileNotFoundError:
        return None
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("%s: invalid UTF-8 (%s)" % (path, error))
    # Ruby String#strip removes ASCII whitespace and NUL at either end.
    return raw.strip(b" \t\r\n\v\f\0") if apple else raw


def _apple_text(plan, data, meta, locale, base):
    for field in specs.fields(data, "apple"):
        name = field["stem"] + ".txt"
        if field["scope"] == "app":
            text = _read(meta / name, apple=True)
            section = "Version" if name == "copyright.txt" else "App Information"
        else:
            text = _read(meta / locale / name, apple=True)
            if text is None and locale != "default":
                text = _read(meta / "default" / name, apple=True)
            section = locale
        if text:
            plan.add(None, base / "text" / name, "App Store Connect > %s > %s" % (section, field["label"]), text)


def _apple_slot(data, path, w, h):
    candidates = specs.apple_slots_for_size(data, w, h)
    if len(candidates) < 2:
        return candidates[0] if candidates else None
    hint = str(path).lower()
    preferred = None
    if (w, h) == (3840, 2160):
        preferred = "vision-pro" if "vision" in hint else "apple-tv"
    elif sorted((w, h)) == [2048, 2732]:
        legacy = any(word in hint for word in ("app_ipad_pro_129", "12.9", "2nd"))
        preferred = "ipad-12-9" if legacy else "ipad-13"
    return next((s for s in candidates if s["id"] == preferred), candidates[0])


def _play_accepts(slot, w, h):
    if min(w, h) <= 0:
        return False
    if "sizes" in slot and [w, h] not in slot["sizes"]:
        return False
    side = slot.get("side", {})
    if min(w, h) < side.get("min", 0) or max(w, h) > side.get("max", float("inf")):
        return False
    if max(w, h) > min(w, h) * slot.get("maxRatio", float("inf")):
        return False
    mw, mh = slot.get("minSize", [0, 0])
    ratios = slot.get("ratios", [slot["ratio"]] if "ratio" in slot else [])
    pairs = [tuple(map(int, ratio.split(":"))) for ratio in ratios]
    return w >= mw and h >= mh and (not pairs or any(w * b == h * a for a, b in pairs))


def _manual(plan, data, root, store, locale, groups, deferred=()):
    for slot_id, name in listing.manual_screenshots(root, store, locale):
        path = Path(name)
        slot = specs.slot(data, store, slot_id)
        if store == "play" and slot_id == "android-xr" and slot is None:
            slot = specs.slot(data, store, "xr")
        w, h = imginfo.image_info(path)[:2]
        if store == "apple":
            accepts = slot in specs.apple_slots_for_size(data, w, h)
        else:
            accepts = slot and _play_accepts(slot, w, h)
        if not accepts:
            plan.problems.append("%s: %sx%s does not fit %s slot %s" % (path, w, h, store, slot_id))
        elif not apple_assets.is_deferred(path, deferred):
            groups["", slot["id"]].append(path)


def _natural(path):
    return [int(part) if i % 2 else part.lower() for i, part in enumerate(re.split(r"([0-9]+)", str(path)))]


def _screenshots(plan, data, store, base, groups, place):
    number = 0
    for platform in ("", "iMessage"):
        for slot in specs.slots(data, store):
            paths = groups.get((platform, slot["id"]))
            if not paths:
                continue
            number += 1
            label = (platform + " " if platform else "") + slot["label"]
            safe = "".join("in" if c == '"' else "-" if c in '\\/:*?<>|' else c for c in label)
            folder = base / ("%02d %s" % (number, safe.strip(" .")))
            for i, path in enumerate(sorted(paths, key=_natural if store == "apple" else str), 1):
                plan.add(path, folder / ("%02d-%s" % (i, path.name)), place + label)


def _apple(root, data, plan):
    assets = root / "store-assets/apple"
    meta = root / "fastlane/metadata"
    try:
        targets = apple_assets.load_plan(root)
    except ValueError as error:
        raise ValueError("asset-plan.json: %s" % error)
    for directory in apple_assets.apple_locales(root, data, targets):
        locale = Path(directory).name
        base = Path("apple") / locale
        _apple_text(plan, data, meta, locale, base)
        groups = defaultdict(list)
        deferred = targets.get(locale, {}).get("deferredScreenshots", {})
        for platform, name in apple_assets.active_screenshots(root, locale, deferred):
            path = Path(name)
            w, h = imginfo.image_info(path)[:2]
            slot = _apple_slot(data, path, w, h)
            if platform == "appleTV" and slot and slot["id"] not in ("apple-tv", "vision-pro"):
                slot = None
            if slot:
                groups["iMessage" if platform == "iMessage" else "", slot["id"]].append(path)
            else:
                plan.problems.append("%s: %sx%s matches no App Store slot" % (path, w, h))
        headers = assets / locale
        _manual(plan, data, root, "apple", locale, groups, deferred)
        _screenshots(plan, data, "apple", base, groups, "App Store Connect > %s > Screenshots > " % locale)
        if headers.is_dir():
            for path in sorted(headers.iterdir()):
                if path.is_file():
                    plan.add(path, base / "graphics" / path.name, "App Store Connect > %s > Header Asset" % locale)


def _play(root, data, plan):
    android = root / "fastlane/metadata/android"
    assets = root / "store-assets/play"
    locales = {p.name for d in (android, assets) if d.is_dir() for p in d.iterdir()
               if p.is_dir() and not p.name.startswith(".")}
    for locale in sorted(locales):
        loc = android / locale
        base = Path("play") / locale
        place = "Play Console > Main store listing > %s > " % locale
        for field in specs.fields(data, "play"):
            name = field["stem"] + ".txt"
            raw = _read(loc / name)
            if raw is not None:
                plan.add(None, base / "text" / name, place + field["label"], raw)
        for path in sorted((loc / "changelogs").glob("*.txt")):
            plan.add(None, base / "text" / ("release-notes-" + path.name),
                     "Play Console > Release > Release notes > %s (%s)" % (locale, path.stem), _read(path))
        images = loc / "images"
        graphics = [Path(p) for p in listing.images(images)]
        for graphic in data["stores"]["play"]["graphics"]:
            matches = [p for p in graphics if p.stem.casefold() == graphic["file"].casefold()]
            if len(matches) > 1:
                plan.problems.append("duplicate %s: %s" % (graphic["label"], ", ".join(map(str, matches))))
            elif matches:
                path = matches[0]
                plan.add(path, base / "graphics" / path.name, place + graphic["label"])
        groups = defaultdict(list)
        for slot in specs.slots(data, "play"):
            if slot.get("folder"):
                groups["", slot["id"]].extend(map(Path, listing.images(images / slot["folder"])))
        _manual(plan, data, root, "play", locale, groups)
        _screenshots(plan, data, "play", base, groups, place + "Screenshots > ")


def inventory(root):
    root = Path(root)
    plan = Plan()
    data = None
    try:
        _check_inputs(root)
        data = specs.load(root)
        _check_rules(data)
        _apple(root, data, plan)
        _play(root, data, plan)
    except (OSError, ValueError) as error:
        plan.problems.append(str(error))
    seen = set()
    for _, dest, _, _ in plan.items:
        key = str(dest).casefold()
        if key in seen:
            plan.problems.append("two files map to %s" % dest)
        seen.add(key)
    return plan, data


def build(root, out=None):
    """Write the folder. Returns (out path, item count, problems)."""
    root = Path(root).resolve()
    destination = output.destination(root, out if out is not None else root / OUT_REL)
    with output.lock_parent(destination.parent):
        output.recover(destination)
        previous = output.owned_files(destination)
        plan, data = inventory(root)
        if not plan.items and not plan.problems:
            plan.problems.append("nothing to hand over from %s" % root)
        if not plan.problems:
            output.install(destination, previous, plan.items, data["verified"], root)
    return str(destination), len(plan.items), plan.problems


def open_folder(path):
    """Reveal a folder with the system's opener. Returns False when there is none."""
    try:
        if os.name == "nt":
            os.startfile(path)
            return True
        cmd = "open" if sys.platform == "darwin" else "xdg-open"
        if not shutil.which(cmd):
            return False
        streams = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if sys.platform == "darwin":
            return subprocess.call([cmd, path], **streams) == 0
        subprocess.Popen([cmd, path], stdin=subprocess.DEVNULL, start_new_session=True, **streams)
        return True
    except OSError:
        return False


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("root")
    parser.add_argument("--out")
    parser.add_argument("--open", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return error.code
    if not os.path.isdir(args.root) or args.out == "":
        parser.print_usage(sys.stderr)
        return 2
    try:
        path, count, problems = build(args.root, args.out)
    except (OSError, ValueError, specs.SpecsError) as e:
        sys.stderr.write("handoff: %s\n" % e)
        return 1
    if problems:
        for p in problems:
            sys.stderr.write("handoff: %s\n" % p)
        sys.stderr.write("handoff: nothing was written.\n")
        return 1
    print("Upload folder: %s (%d files; see INDEX.md)" % (path, count))
    if args.open and not open_folder(path):
        print("Could not open a file manager here; open the folder above yourself.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
