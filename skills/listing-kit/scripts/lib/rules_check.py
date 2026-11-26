#!/usr/bin/env python3
"""Check one screenshot locale or Play graphic. Output LEVEL<TAB>message rows."""
import argparse
from collections import Counter
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import apple_assets
import detect
import imginfo
import listing
import specs


def inspected(paths):
    for path, (info, status) in zip(paths, imginfo.validate_many(paths)):
        path = Path(path)
        notes = []
        if path.suffix != path.suffix.lower():
            notes.append(("FAIL", f"{path.name}: rename with a lower-case extension (fastlane won't upload it)"))
        if status == "unavailable":
            notes.append(("IM_UNAVAILABLE", ""))
        elif status.startswith("could not decode:"):
            notes.append(("WARN", f"{path.name}: {status}"))
        elif status != "ok":
            reason = status[5:] if status.startswith("bad: ") else "image failed full decode"
            notes.append(("FAIL", f"{path.name}: {reason}"))
        yield path, info, status, notes


def missing(level, reason, message):
    if level != "optional":
        yield ("FAIL" if level == "required" else "WARN", message + (" — " + reason if reason else ""))


def count_rows(slot, count, requirements, store):
    label = slot["label"]
    level, reason = requirements.evaluate(slot["required"])
    if count > slot["max"]:
        yield "FAIL", f'{label}: {count} screenshots ({store} max is {slot["max"]} per display class)'
    if count < slot["min"]:
        msg = f'no {label} screenshots' if not count else f'{label} screenshots: {count}'
        yield from missing(level, reason, msg + f' (need ≥{slot["min"]})')
    if count and slot["framing"] == "forbidden":
        yield "NOTE", f"{label}: framing forbidden; check that the screenshots are unframed"


def byte_limit(path, rule):
    if "maxBytes" in rule and imginfo.image_bytes(path) > rule["maxBytes"]:
        yield "FAIL", f'{path.name}: exceeds {rule["maxBytes"]} bytes'


def apple_shots(directory, console, rules, requirements):
    counts = Counter()
    base = rules["stores"]["apple"]["screenshots"]
    paths = apple_assets.screenshot_paths(directory, rules, console)
    for path, (w, h, depth, color), status, notes in inspected(paths):
        yield from notes
        if status.startswith("bad: "):
            continue
        slot = specs.apple_slot_for_file(rules, w, h, str(path))
        if not slot:
            yield "FAIL", f"{path.name}: {w}x{h} is not an App Store screenshot size"
            continue
        if status != "bad":
            counts[slot["id"]] += 1
        formats = slot.get("formats", base.get("formats"))
        if formats and not imginfo.format_allowed(path, formats):
            yield "FAIL", f"{path.name}: format outside accepted screenshot formats"
        if slot.get("alpha", base.get("alpha")) is False and color != 2:
            yield "FAIL", f"{path.name}: must be RGB no-alpha (colortype={color})"
        if "bitDepth" in slot and depth != slot["bitDepth"]:
            yield "FAIL", f'{path.name}: expected bit depth {slot["bitDepth"]}'
        yield from byte_limit(path, slot)
    for slot in base["slots"]:
        count = counts[slot["id"]]
        yield from count_rows(slot, count, requirements, "App Store")
        if count and count <= slot["max"]:
            yield "PASS", f'{slot["label"]} screenshots present ({count})'


def promoted(rule, w, h):
    return (min(w, h) >= rule["shortSideMin"] and max(w, h) <= rule.get("longSideMax", float("inf"))
            and specs.ratio_matches(w, h, rule["ratios"]))


def play_shots(directory, console, rules, requirements):
    shots = rules["stores"]["play"]["screenshots"]
    total = 0
    for slot in shots["slots"]:
        paths = listing.images(directory / slot["folder"]) if slot.get("folder") else []
        paths += listing.images(console / slot["id"])
        total += len(paths)
        count = len(paths)
        label = slot["label"]
        yield from count_rows(slot, count, requirements, "Play")
        promotion = slot.get("promotion")
        eligible = 0
        sizes = Counter()
        for path, (w, h, depth, color), status, notes in inspected(paths):
            yield from notes
            if status.startswith("bad: "):
                continue
            sizes[(w, h)] += 1
            for error in specs.play_size_errors(slot, w, h):
                yield "FAIL", f"{path.name}: {error}"
            if slot.get("formats") and not imginfo.format_allowed(path, slot["formats"]):
                yield "FAIL", f'{path.name}: expected {" or ".join(slot["formats"])}'
            if depth != slot.get("bitDepth", depth) or (slot.get("alpha") is False and color != 2):
                yield "FAIL", f'{path.name}: must be {3 * slot.get("bitDepth", depth)}-bit no-alpha (depth={depth} colortype={color})'
            yield from byte_limit(path, slot)
            if promotion and promoted(promotion, w, h):
                eligible += 1
        if count:
            yield "NOTE", f"{label} screenshots: {count}"
            if "minPerSize" in slot:
                for size in slot["sizes"]:
                    if sizes[tuple(size)] < slot["minPerSize"]:
                        yield "FAIL", f'{label}: need {slot["minPerSize"]} at {size[0]}x{size[1]}'
            if promotion and eligible < promotion["count"]:
                yield "WARN", (f'{label}: only {eligible} screenshot(s) at ≥{promotion["shortSideMin"]}px; '
                               f'need {promotion["count"]} at {" or ".join(promotion["ratios"])} for promotion eligibility')
    minimum = shots["minTotal"]
    if total < minimum:
        yield "FAIL", f"screenshots: {total} across device types (need ≥{minimum})"
    else:
        yield "PASS", f"screenshots across device types: {total} (≥{minimum})"


def play_graphic(directory, graphic, requirements):
    stem, label = graphic["file"], graphic["label"]
    level, reason = requirements.evaluate(graphic["required"])
    if (directory / stem).is_dir():
        yield "FAIL", f"images/{stem}/ is not uploaded by fastlane supply; move the file to images/{stem}.png"
    paths = [p for p in listing.images(directory) if Path(p).stem == stem]
    if not paths:
        yield from missing(level, reason, f"{label} MISSING: images/{stem}")
    if len(paths) > 1:
        yield "FAIL", f'duplicate {stem} candidates: {", ".join(map(str, paths))}'
    for path, (w, h, depth, color), status, notes in inspected(paths):
        yield from notes
        if status.startswith("bad: "):
            continue
        expected = "{}x{}".format(*graphic["size"])
        formats = graphic["formats"]
        valid_format = imginfo.format_allowed(path, formats)
        if not valid_format:
            yield "FAIL", f'{label} must be a {" or ".join(f.upper() for f in formats)} ({path.name})'
        alpha = graphic.get("alpha")
        colors = {2, 6} if alpha else {2}
        if alpha == "required":
            colors = {6}
        if graphic.get("grayscaleJpeg") and imginfo.image_format(path) == "jpeg":
            colors.add(0)
        if [w, h] != graphic["size"] or color not in colors or depth != graphic.get("bitDepth", depth):
            yield "FAIL", f"{label} must be {expected} with the specified depth and channels (got {w}x{h} depth={depth} ct={color})"
        elif len(paths) == 1 and valid_format and status in ("ok", "unavailable"):
            yield "PASS", f"{label} {expected}"
        yield from byte_limit(path, graphic)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store", choices=("apple", "play"))
    parser.add_argument("locale")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--graphic")
    args = parser.parse_args()
    rules = specs.load(args.root)
    requirements = detect.Requirements(args.root, rules)
    directory = args.root / "fastlane"
    console = args.root / "store-assets" / args.store / args.locale / "screenshots"
    if args.store == "apple":
        rows = apple_shots(directory / "screenshots" / args.locale, console, rules, requirements)
    else:
        images = directory / "metadata" / "android" / args.locale / "images"
        if args.graphic:
            graphic = next(g for g in rules["stores"]["play"]["graphics"] if g["id"] == args.graphic)
            rows = play_graphic(images, graphic, requirements)
        else:
            rows = play_shots(images, console, rules, requirements)
    for level, message in rows:
        print(level, message, sep="\t")
