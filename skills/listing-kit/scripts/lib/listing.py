#!/usr/bin/env python3
"""Where things are in a fastlane listing tree. Shared by validate-listing.sh,
apple_assets.py, and build-review.sh so all three see the same stores, locales, and images.

CLI:    listing.py {apple-locales|play-locales} <fastlane-dir>
Prints one locale directory per line (apple-locales: metadata/<locale> paths, some
of which may not exist yet when a locale only has screenshots).
"""
import os
import sys

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import specs
from imginfo import is_image

# deliver folders under metadata/ that are not locales.
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


def apple_locales(fl, rules=None):
    """Include known locales and directories containing localized deliver assets."""
    rules = rules if rules is not None else specs.load(os.path.dirname(fl))
    apple = rules["stores"]["apple"]
    meta = os.path.join(fl, "metadata")
    shots = os.path.join(fl, "screenshots")
    names = {n for n in _subdirs(meta) if n not in apple["nonLocaleFolders"]
             and (n in apple["locales"] or _has_files(os.path.join(meta, n), localized_files(rules)))}
    names.update(n for n in _subdirs(shots) if n in apple["locales"] or images(os.path.join(shots, n)))
    return [os.path.join(meta, n) for n in sorted(names)]


def apple_default(fl, rules=None):
    """metadata/default (deliver's fallback values) if present, else None."""
    rules = rules if rules is not None else specs.load(os.path.dirname(fl))
    d = os.path.join(fl, "metadata", "default")
    return d if _has_files(d, localized_files(rules)) else None


def has_apple_app_metadata(fl, rules=None):
    """True if fastlane/metadata holds recognized deliver files at app level or in its special folders."""
    meta = os.path.join(fl, "metadata")
    rules = rules if rules is not None else specs.load(os.path.dirname(fl))
    files = DELIVER_APP_FILES | {f["stem"] + ".txt" for f in specs.fields(rules, "apple", "app")}
    return bool(apple_default(fl, rules)) or _has_files(meta, files) or any(
        _has_files(os.path.join(meta, folder), names) for folder, names in SPECIAL_FILES.items()
    )


def play_locales(fl):
    a = os.path.join(fl, "metadata", "android")
    return [os.path.join(a, n) for n in _subdirs(a)]


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
    for loc in {"apple-locales": apple_locales, "play-locales": play_locales}[kind](fl):
        print(loc)
