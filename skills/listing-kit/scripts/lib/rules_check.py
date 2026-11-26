#!/usr/bin/env python3
"""Check one screenshot locale or Play graphic. Output LEVEL<TAB>message rows."""
import argparse
from collections import Counter
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import apple_assets
import screenshots
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


PRIMARY = {"supportsIphone": "iphone", "supportsIpad": "ipad", "supportsAndroidPhone": "phone"}


def count_rows(slot, count, requirements, store, family_count=0):
    label = slot["label"]
    rule = slot["required"]
    level, reason = requirements.evaluate(rule)
    if count > slot["max"]:
        yield "FAIL", f'{label}: {count} screenshots ({store} max is {slot["max"]} per display class)'
    if count < slot["min"]:
        msg = (f'no {label} screenshots' if not count else f'{label} screenshots: {count}') + f' (need ≥{slot["min"]})'
        condition = rule.get("condition")
        if level == "upcoming" and "from" not in rule and requirements.values.get(condition) is None:
            if condition in PRIMARY:
                severity = "WARN" if family_count else "FAIL"
                first = condition not in requirements.reported_unknown
                if first:
                    requirements.reported_unknown.add(condition)
                    msg += f" — set {condition} in the platforms key in .listing-kit/listing.json"
                    if condition in detect.ENV_FLAGS:
                        msg += " or set " + detect.ENV_FLAGS[condition]
                if first or severity == "FAIL":
                    yield severity, msg
            elif requirements.verbose:
                yield "NOTE", msg + " — " + reason
        else:
            yield from missing(level, reason, msg)
    if count and slot["framing"] == "forbidden":
        yield "NOTE", f"{label}: framing forbidden; check that the screenshots are unframed"


def byte_limit(path, rule):
    if "maxBytes" in rule and imginfo.image_bytes(path) > rule["maxBytes"]:
        yield "FAIL", f'{path.name}: exceeds {rule["maxBytes"]} bytes'


def apple_count_rows(slot, counts, requirements, deferred):
    if deferred:
        level, _ = requirements.evaluate(slot["required"])
        if level == "optional" or level == "upcoming" and "from" in slot["required"]:
            return
    family = PRIMARY.get(slot["required"].get("condition"))
    family_count = sum(n for key, n in counts.items() if family and key.startswith(family + "-"))
    yield from count_rows(slot, counts.get(slot["id"], 0), requirements, "App Store", family_count)


def apple_shots(root, locale, rules, requirements, deferred=(), tree=None, planned=False, suffixes=None):
    counts = Counter()
    message_counts = Counter()
    base = rules["stores"]["apple"]["screenshots"]
    selected = []
    for shot in screenshots.active(root, "apple", locale, rules, deferred, tree=tree, suffixes=suffixes):
        if shot.manual and shot.error:
            yield "FAIL", shot.error
        else:
            selected.append(shot)
    for shot, (path, (w, h, depth, color), status, notes) in zip(selected, inspected([s.path for s in selected])):
        yield from notes
        if status.startswith("bad: "):
            continue
        if shot.error:
            yield "FAIL", shot.error
            continue
        slot = shot.slot
        if status != "bad":
            group = message_counts if shot.platform == "iMessage" else counts
            group[slot["id"]] += 1
        formats = slot.get("formats", base.get("formats"))
        if formats and not imginfo.format_allowed(path, formats):
            yield "FAIL", f"{path.name}: format outside accepted screenshot formats"
        if slot.get("alpha", base.get("alpha")) is False and color != 2:
            yield "FAIL", f"{path.name}: must be RGB no-alpha (colortype={color})"
        if "bitDepth" in slot and depth != slot["bitDepth"]:
            yield "FAIL", f'{path.name}: expected bit depth {slot["bitDepth"]}'
        yield from byte_limit(path, slot)
    primary_total = sum(n for key, n in counts.items() if key.startswith(("iphone-", "ipad-")))
    if primary_total < base["minTotal"]:
        yield "FAIL", f'screenshots: {primary_total} across primary device families (need ≥{base["minTotal"]})'
    for slot in base["slots"]:
        message_count = message_counts[slot["id"]]
        if message_count > slot["max"]:
            yield "FAIL", f'iMessage {slot["label"]}: {message_count} screenshots (max {slot["max"]})'
        elif message_count:
            yield "PASS", f'iMessage {slot["label"]} screenshots present ({message_count})'
        count = counts[slot["id"]]
        yield from apple_count_rows(slot, counts, requirements, planned and slot["id"] in deferred)
        if count and count <= slot["max"]:
            yield "PASS", f'{slot["label"]} screenshots present ({count})'


def promoted(rule, w, h):
    return (min(w, h) >= rule["shortSideMin"] and max(w, h) <= rule.get("longSideMax", float("inf"))
            and specs.ratio_matches(w, h, rule["ratios"]))


def play_coverage(locale, expected, counts):
    for slot, wanted in expected.items():
        if wanted == 0:
            yield "WARN", f"planned Play {locale}/{slot}: nothing planned yet"
            continue
        actual = counts.get(slot, 0)
        level = "PASS" if wanted == actual else "WARN"
        yield level, f"planned Play {locale}/{slot}: {actual} of {wanted} screenshots"


def play_shots(root, locale, rules, requirements, tree=None, expected=None, coverage_only=False):
    shots = rules["stores"]["play"]["screenshots"]
    groups = {}
    for shot in screenshots.active(root, "play", locale, rules, tree=tree):
        if shot.error:
            yield "FAIL", shot.error
        else:
            groups.setdefault(shot.slot["id"], []).append(shot.path)
    valid = Counter()
    total = 0
    for slot in shots["slots"]:
        paths = groups.get(slot["id"], [])
        count = len(paths)
        label = slot["label"]
        if expected is None:
            yield from count_rows(slot, count, requirements, "Play", count)
        promotion = slot.get("promotion")
        eligible = 0
        sizes = Counter()
        for path, (w, h, depth, color), status, notes in inspected(paths):
            yield from notes
            if status.startswith("bad: "):
                continue
            errors = [("FAIL", f"{path.name}: {error}") for error in specs.play_size_errors(slot, w, h)]
            if slot.get("formats") and not imginfo.format_allowed(path, slot["formats"]):
                errors.append(("FAIL", f'{path.name}: expected {" or ".join(slot["formats"])}'))
            if depth != slot.get("bitDepth", depth) or (slot.get("alpha") is False and color != 2):
                errors.append(("FAIL", f'{path.name}: must be {3 * slot.get("bitDepth", depth)}-bit no-alpha (depth={depth} colortype={color})'))
            errors.extend(byte_limit(path, slot))
            yield from errors
            if not errors and not any(level == "FAIL" for level, _ in notes):
                valid[slot["id"]] += 1
            elif expected is not None:
                continue
            sizes[(w, h)] += 1
            if promotion and promoted(promotion, w, h):
                eligible += 1
        if coverage_only:
            continue
        if expected is not None:
            count = valid[slot["id"]]
            yield from count_rows(slot, count, requirements, "Play", count)
        total += count
        if count:
            yield "NOTE", f"{label} screenshots: {count}"
            if "minPerSize" in slot:
                for size in slot["sizes"]:
                    if sizes[tuple(size)] < slot["minPerSize"]:
                        yield "FAIL", f'{label}: need {slot["minPerSize"]} at {size[0]}x{size[1]}'
            if promotion and eligible < promotion["count"]:
                yield "WARN", (f'{label}: only {eligible} screenshot(s) at ≥{promotion["shortSideMin"]}px; '
                               f'need {promotion["count"]} at {" or ".join(promotion["ratios"])} for promotion eligibility')
    if expected:
        yield from play_coverage(locale, expected, valid)
    if coverage_only:
        return
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
        if level == "upcoming" and "from" not in graphic["required"] and not requirements.verbose:
            return
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
    tree = listing.paths(args.root)[args.store]
    if args.store == "apple":
        coverage = apple_assets.load_coverage(args.root, rules)
        requirements.apply_inferred(coverage.get("inferred", {}))
        deferred = coverage["apple"].get(args.locale, {}).get("deferredScreenshots", {})
        rows = apple_shots(args.root, args.locale, rules, requirements, apple_assets.deferred_slots(rules, deferred, "play" in coverage),
                           tree, planned="play" in coverage, suffixes=coverage["apple"].get(args.locale, {}).get("suffixes"))
    else:
        images = tree["metadata"] / args.locale / "images"
        if args.graphic:
            graphic = next(g for g in rules["stores"]["play"]["graphics"] if g["id"] == args.graphic)
            rows = play_graphic(images, graphic, requirements)
        else:
            expected = apple_assets.load_coverage(args.root, rules).get("play", {}).get(args.locale, {})
            rows = play_shots(args.root, args.locale, rules, requirements, tree, expected.get("screenshots"))
    for level, message in rows:
        print(level, message, sep="\t")
