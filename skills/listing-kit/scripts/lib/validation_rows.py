"""Collect a complete validation transcript using one snapshot of the effective rules."""
import argparse
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apple_assets
import detect
import fields
import listing
import rules_check
import specs


def collect(root, as_of, ios_sdk):
    rules = specs.load(root)
    verified, age, stale = specs.staleness(rules, as_of)
    yield "NOTE", f"store rules verified on {verified}"
    if rules["_override"]:
        yield "NOTE", f"active store rules override: {rules['_override']}"
    if stale:
        yield "WARN", f"store rules are {age} days old; verify current requirements"
    req = detect.Requirements(root, rules, as_of, ios_sdk)
    fl = root / "fastlane"
    display = Path(os.environ.get("LK_REVIEW_DISPLAY_ROOT", root))

    def copy(store, directory, fallback=None):
        for row in fields.rows(store, directory, fallback, rules, req):
            row["path"] = display / Path(row["path"]).relative_to(root)
            yield fields.check(row)

    apple = apple_assets.has_apple_listing(root, rules)
    play = (fl / "metadata/android").is_dir()
    if apple:
        yield "NOTE", "== Apple App Store =="
        locales = list(map(Path, apple_assets.apple_locales(root, rules)))
        fallback = listing.apple_default(fl, rules)
        if not locales and fallback:
            locales = [Path(fallback)]
        if not locales:
            yield "FAIL", "no fastlane/metadata/<locale>/ directory"
        # Deliver can reuse the primary screenshots for a metadata-only localization.
        has_capture = any((fl / "screenshots" / loc.name).is_dir() or
                          (root / "store-assets/apple" / loc.name / "screenshots").is_dir() for loc in locales)
        for locale in locales:
            yield "NOTE", "  locale " + locale.name + ":"
            yield from copy("apple", locale, fallback)
            if has_capture and not ((fl / "screenshots" / locale.name).is_dir() or
                                    (root / "store-assets/apple" / locale.name / "screenshots").is_dir()):
                continue
            yield "NOTE", "  screenshots " + locale.name + ":"
            yield from rules_check.apple_shots(fl / "screenshots" / locale.name,
                                               root / "store-assets/apple" / locale.name / "screenshots", rules, req)
        yield from copy("apple-app", fl / "metadata")
        required = {s["label"] for s in specs.slots(rules, "apple") if req.evaluate(s["required"])[0] == "required"}
        yield from apple_assets.validate(root, required, rules, req)
        if not (root / ".listing-kit/asset-plan.json").is_file():
            yield "WARN", "no asset-plan.json: store minimums checked; requested extra sets/headers cannot be confirmed"

    if play:
        yield "NOTE", "== Google Play =="
        locales = list(map(Path, listing.play_locales(fl)))
        if not locales:
            yield "FAIL", "fastlane/metadata/android has no locale folders"
        for locale in locales:
            yield "NOTE", "  locale " + locale.name + ":"
            yield from copy("play", locale)
            directory = locale / "images"
            yield from rules_check.play_shots(directory, root / "store-assets/play" / locale.name / "screenshots", rules, req)
            for graphic in rules["stores"]["play"]["graphics"]:
                yield from rules_check.play_graphic(directory, graphic, req)
    if not apple and not play:
        yield "FAIL", f"no App Store or Google Play listing was found under {display} — nothing to validate"
    yield from req.evidence()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--as-of")
    parser.add_argument("--ios-sdk")
    args = parser.parse_args()
    if args.as_of and not specs._date(args.as_of):
        parser.error("--as-of expects YYYY-MM-DD")
    if args.ios_sdk and not re.fullmatch(r"[0-9]+\.[0-9]+", args.ios_sdk):
        parser.error("--ios-sdk expects X.Y")
    try:
        for level, message in collect(args.root, specs.parse_date(args.as_of) if args.as_of else None, args.ios_sdk):
            print(level, message, sep="\t")
    except specs.SpecsError as exc:
        sys.exit(f"store rules: {exc}")
