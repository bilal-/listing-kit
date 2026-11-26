#!/usr/bin/env python3
"""Where things are in a fastlane listing tree. Shared by validate-listing.sh,
apple_assets.py, and build-review.sh so all three see the same stores, locales, and images.

CLI:    listing.py {apple-locales|play-locales} <fastlane-dir>
Prints one locale directory per line (apple-locales: metadata/<locale> paths, some
of which may not exist yet when a locale only has screenshots).
"""
import os
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import specs
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


def localized_files(rules):
    return {f["stem"] + ".txt" for f in specs.fields(rules, "apple", "locale")} | {
        "apple_tv_privacy_policy.txt", "privacy_choices_url.txt",
    }


CONTACT_FILES = {"first_name.txt", "last_name.txt", "phone_number.txt", "email_address.txt"}
SPECIAL_FILES = {
    "review_information": CONTACT_FILES | {"demo_user.txt", "demo_password.txt", "notes.txt"},
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


def apple_locales(tree, rules):
    """Include known locales and directories containing localized deliver assets."""
    apple = rules["stores"]["apple"]
    meta, shots = tree["metadata"], tree["screenshots"]
    known = set(apple["locales"])
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
    return bool(apple_default(meta, rules)) or _has_files(meta, files) or any(
        _has_files(os.path.join(meta, folder), names) for folder, names in SPECIAL_FILES.items()
    )


def play_locales(metadata):
    return [os.path.join(metadata, n) for n in _subdirs(metadata)]


def images(d):
    """PNG/JPEG files directly in d (extension case-insensitive), sorted."""
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return []
    return [os.path.join(d, n) for n in names
            if not n.startswith(".") and os.path.isfile(os.path.join(d, n)) and is_image(n)]


if __name__ == "__main__":
    kind, fl = sys.argv[1], sys.argv[2]
    tree = Path(fl)
    if kind == "apple-locales":
        locales = apple_locales({"metadata": tree / "metadata", "screenshots": tree / "screenshots"},
                                specs.load(tree.parent))
    elif kind == "play-locales":
        locales = play_locales(tree / "metadata/android")
    else:
        sys.exit("expected apple-locales or play-locales")
    for loc in locales:
        print(loc)
