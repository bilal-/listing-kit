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
import plan
import rules_check
import specs


def collect(root, as_of, ios_sdk, verbose=False, coverage_view=None):
    rules = specs.load(root)
    verified, age, stale = specs.staleness(rules, as_of)
    yield "NOTE", f"store rules verified on {verified}"
    if rules["_override"]:
        yield "NOTE", f"active store rules override: {rules['_override']}"
    if stale:
        yield "WARN", f"store rules are {age} days old; verify current requirements"
    req = detect.Requirements(root, rules, as_of, ios_sdk)
    req.verbose = verbose
    for error in req.errors:
        yield "FAIL", error
    trees = listing.paths(root)
    apple_tree, play_tree = trees["apple"], trees["play"]
    display = Path(os.environ.get("LK_REVIEW_DISPLAY_ROOT", root))

    def copy(store, directory, fallback=None):
        for row in fields.rows(store, directory, fallback, rules, req):
            row["path"] = display / Path(row["path"]).relative_to(root)
            if verbose or row["required"] or row["value"] is not None or row.get("error") or row["reason"].startswith("required from"):
                yield fields.check(row)

    modern = not coverage_view and (root / plan.LISTING).is_file()
    legacy_error = None
    try:
        coverage = apple_assets.load_coverage(root, rules, coverage_view)
    except (ValueError, OSError) as exc:
        if modern:
            yield "FAIL", f"{plan.LISTING.name}: {exc}"
        else:
            legacy_error = str(exc)
        coverage = {"apple": {}}
    targets = coverage["apple"]
    modern = modern or "play" in coverage
    req.apply_inferred(coverage.get("inferred", {}))
    legacy = (root / apple_assets.LEGACY).is_file()
    if modern and legacy:
        yield apple_assets.legacy_advisory(root, rules, targets)
    locales = list(map(Path, apple_assets.apple_locales(root, rules, targets, apple_tree)))
    apple = apple_assets.has_apple_listing(root, rules, locales, apple_tree) or (legacy and not modern)
    play = play_tree["metadata"].is_dir() or bool(coverage.get("play"))
    if apple:
        yield "NOTE", "== Apple App Store =="
        if not verbose:
            yield "NOTE", "  NOTE: Use --verbose for optional fields and platform evidence."
        fallback = listing.apple_default(apple_tree["metadata"], rules)
        if not locales and fallback:
            locales = [Path(fallback)]
        if not locales:
            yield "FAIL", f"no {apple_tree['metadata']}/<locale>/ directory"
        # Deliver can reuse the primary screenshots for a metadata-only localization.
        on_disk = {loc.name for loc in locales if any(Path(d).is_dir() for _, d in
                   listing.apple_screenshot_dirs(apple_tree["screenshots"], loc.name, rules))
                   or (apple_tree["storeAssets"] / loc.name / "screenshots").is_dir()}
        # Screenshots on disk are always checked, planned or not, as handoff packages them.
        planned_locales = apple_assets.planned_screenshot_locales(targets) if modern else set()
        capture_locales = on_disk | planned_locales
        for locale in locales:
            yield "NOTE", "  locale " + locale.name + ":"
            yield from copy("apple", locale, fallback)
            entry = targets.get(locale.name, {})
            if capture_locales and locale.name not in capture_locales:
                continue
            yield "NOTE", "  screenshots " + locale.name + ":"
            deferred = apple_assets.deferred_slots(rules, entry.get("deferredScreenshots", {}), modern)
            yield from rules_check.apple_shots(root, locale.name, rules, req, deferred, apple_tree,
                                              planned=modern, suffixes=entry.get("suffixes"))
        yield from copy("apple-app", apple_tree["metadata"])
        yield from copy("apple-review", apple_tree["metadata"] / "review_information")
        key = "id" if modern else "label"
        required = {s[key] for s in specs.slots(rules, "apple") if req.evaluate(s["required"])[0] == "required"}
        yield from apple_assets.validate(root, required, rules, req, apple_tree, targets, modern)
        if legacy_error:
            yield "FAIL", f"{apple_assets.LEGACY.name}: {legacy_error}"
        if not modern and not legacy:
            yield "WARN", "no asset-plan.json: store minimums checked; requested extra sets/headers cannot be confirmed"

    play_locales = list(map(Path, listing.play_locales(play_tree["metadata"])))
    if play:
        yield "NOTE", "== Google Play =="
        if not verbose:
            yield "NOTE", "  NOTE: Use --verbose for optional fields and platform evidence."
        if not play_locales:
            if play_tree["metadata"].is_dir():
                yield "FAIL", f"{play_tree['metadata']} has no locale folders"
            else:
                yield "WARN", f"planned Play metadata directory is missing: {play_tree['metadata']}"
        for locale in play_locales:
            yield "NOTE", "  locale " + locale.name + ":"
            yield from copy("play", locale)
            directory = locale / "images"
            entry = coverage.get("play", {}).get(locale.name, {})
            yield from rules_check.play_shots(root, locale.name, rules, req, play_tree,
                                              entry.get("screenshots", {}) if modern else None)
            for graphic in rules["stores"]["play"]["graphics"]:
                yield from rules_check.play_graphic(directory, graphic, req)
    # A planned Play locale can be absent from the metadata tree altogether.
    existing = {p.name for p in play_locales}
    for code, entry in coverage.get("play", {}).items():
        if code not in existing:
            yield from rules_check.play_shots(root, code, rules, req, play_tree,
                                              entry.get("screenshots", {}), coverage_only=True)
    if not apple and not play:
        yield "FAIL", f"no App Store or Google Play listing was found under {display} — nothing to validate"
    if verbose:
        yield from req.evidence()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--as-of")
    parser.add_argument("--ios-sdk")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--coverage-view", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.as_of and not specs._date(args.as_of):
        parser.error("--as-of expects YYYY-MM-DD")
    if args.ios_sdk and not re.fullmatch(r"[0-9]+\.[0-9]+", args.ios_sdk):
        parser.error("--ios-sdk expects X.Y")
    try:
        for level, message in collect(args.root, specs.parse_date(args.as_of) if args.as_of else None, args.ios_sdk, args.verbose, args.coverage_view):
            print(level, message, sep="\t")
    except specs.SpecsError as exc:
        sys.exit(f"store rules: {exc}")
