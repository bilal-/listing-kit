#!/usr/bin/env python3
"""Where things are in a fastlane listing tree. Shared by validate-listing.sh,
apple_assets.py, and build-review.sh so all three see the same stores, locales, and images.

CLI:    listing.py {apple-locales|play-locales} [<fastlane-dir>] --app-root <app-dir>
Prints one locale directory per line (apple-locales: metadata/<locale> paths, some
of which may not exist yet when a locale only has screenshots).
"""
import argparse
import os
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import specs
from secret_scan import demo_credential
import plan
from imginfo import is_image

# Recognized deliver app-level metadata files directly under fastlane/metadata/.
DELIVER_APP_FILES = {
    "primary_first_sub_category.txt",
    "primary_second_sub_category.txt",
    "secondary_first_sub_category.txt",
    "secondary_second_sub_category.txt",
    "app_store_rating_config.json",
    "age_rating_declaration.json",
    "apple_tv_privacy_policy.txt",
}


def paths(root):
    """Return the same store directories as the plan, rooted at the supplied app."""
    return {store: {key: Path(root) / value for key, value in tree.items()}
            for store, tree in plan.listing_trees(root).items()}


def check_metadata_links(root, trees):
    """Check links before any consumer reads or copies metadata."""
    roots = {(root / tree[key]).resolve() for tree in trees.values()
             for key in ("metadata", "screenshots", "storeAssets")}
    review = None
    if "apple" in trees:
        review = (root / trees["apple"]["metadata"] / "review_information").resolve()
    visited = set()

    def visit(path, in_review=False):
        if path.is_symlink():
            target = path.resolve()
            inside = [base for base in roots if base == target or base in target.parents]
            private = (target == review or review in target.parents or any(
                part.lower() == "review_information" for base in inside
                for part in target.relative_to(base).parts))
            if not inside or demo_credential(target) or (private and not in_review):
                raise ValueError(f"Unsafe listing link: {path}")
        if path.is_dir():
            directory = (path.resolve(), in_review)
            if directory not in visited:
                visited.add(directory)
                for child in path.iterdir():
                    visit(child, in_review or child.name.lower() == "review_information")

    for tree in trees.values():
        visit(root / tree["metadata"])


def localized_files(rules):
    return {f["stem"] + ".txt" for f in specs.fields(rules, "apple", "locale")} | {
        "apple_tv_privacy_policy.txt", "privacy_choices_url.txt",
    }


CONTACT_FILES = {"first_name.txt", "last_name.txt", "phone_number.txt", "email_address.txt"}
SPECIAL_FILES = {
    "trade_representative_contact_information": CONTACT_FILES | {
        "trade_name.txt", "address_line1.txt", "address_line2.txt", "address_line3.txt",
        "city_name.txt", "state.txt", "country.txt", "postal_code.txt",
    },
}


def _has_files(directory, names):
    return any(os.path.isfile(os.path.join(directory, name)) for name in names)


def _subdirs(d):
    try:
        return sorted(e for e in os.listdir(d)
                      if not e.startswith(".") and os.path.isdir(os.path.join(d, e)))
    except OSError:
        return []


def screenshot_folders(rules):
    return sorted({"iMessage"} | {s["folder"] for s in specs.slots(rules, "apple") if s.get("folder")})


def apple_screenshot_dirs(base, locale, rules):
    yield "", os.path.join(base, locale)
    for platform in screenshot_folders(rules):
        yield platform, os.path.join(base, platform, locale)
        yield platform, os.path.join(base, locale, platform)


def apple_locales(tree, rules, files_only=False):
    """Include known locales and directories containing localized deliver assets."""
    apple = rules["stores"]["apple"]
    meta, shots = tree["metadata"], tree["screenshots"]
    known = set() if files_only else set(apple["locales"])
    localized = localized_files(rules)
    names = {n for n in _subdirs(meta) if n not in apple.get("nonLocaleFolders", ())
             and (n in known or _has_files(os.path.join(meta, n), localized))}
    folders = screenshot_folders(rules)
    candidates = set(_subdirs(shots)).difference(folders)
    for platform in folders:
        candidates.update(_subdirs(os.path.join(shots, platform)))
    names.update(n for n in candidates if n in known or
                 any(images(directory) for _, directory in apple_screenshot_dirs(shots, n, rules)))
    return [os.path.join(meta, n) for n in sorted(names)]


def apple_default(meta, rules):
    """metadata/default (deliver's fallback values) if present, else None."""
    d = os.path.join(meta, "default")
    return d if _has_files(d, localized_files(rules)) else None


def has_apple_app_metadata(meta, rules):
    """True if fastlane/metadata holds recognized deliver files at app level or in its special folders."""
    files = DELIVER_APP_FILES | {f["stem"] + ".txt" for f in specs.fields(rules, "apple", "app")}
    review_files = [f["stem"] + ".txt" for f in specs.fields(rules, "apple", "review_information")]
    if _has_files(os.path.join(meta, "review_information"), review_files):
        return True
    return bool(apple_default(meta, rules)) or _has_files(meta, files) or any(
        _has_files(os.path.join(meta, folder), names) for folder, names in SPECIAL_FILES.items()
    )


def play_locales(metadata):
    return [os.path.join(metadata, n) for n in _subdirs(metadata)]


def play_asset_locales(tree, planned):
    return sorted({Path(path).name for path in play_locales(tree["metadata"])}
                  | set(_subdirs(tree["storeAssets"])) | set(planned))


def images(d):
    """PNG/JPEG files directly in d (extension case-insensitive), sorted."""
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return []
    return [os.path.join(d, n) for n in names
            if not n.startswith(".") and os.path.isfile(os.path.join(d, n)) and is_image(n)]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("apple-locales", "play-locales"))
    parser.add_argument("fastlane", nargs="?", type=Path, help="legacy fastlane directory")
    parser.add_argument("--app-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.app_root.resolve()
    if args.fastlane:
        trees = {"apple": {"metadata": args.fastlane / "metadata", "screenshots": args.fastlane / "screenshots"},
                 "play": {"metadata": args.fastlane / "metadata/android"}}
    else:
        trees = paths(root)
    if args.kind == "apple-locales":
        locales = apple_locales(trees["apple"], specs.load(root))
    else:
        locales = play_locales(trees["play"]["metadata"])
    for loc in locales:
        print(loc)
