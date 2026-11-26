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

from fields import FIELDS
from imginfo import is_image

# deliver folders under metadata/ that are not locales.
DELIVER_META_DIRS = {"default", "review_information", "trade_representative_contact_information"}
NOT_LOCALES = {"android"} | DELIVER_META_DIRS

# Recognized deliver app-level metadata files directly under fastlane/metadata/.
DELIVER_APP_FILES = {
    "copyright.txt",
    "primary_category.txt",
    "secondary_category.txt",
    "primary_first_sub_category.txt",
    "primary_second_sub_category.txt",
    "secondary_first_sub_category.txt",
    "secondary_second_sub_category.txt",
    "app_store_rating_config.json",
    "age_rating_declaration.json",
    "apple_tv_privacy_policy.txt",
}


# App Store Connect localization identifiers used by deliver.
APPLE_LOCALES = set("""
    ar-SA ca cs da de-DE el en-AU en-CA en-GB en-US es-ES es-MX fi fr-CA fr-FR
    he hi hr hu id it ja ko ms nl-NL no pl pt-BR pt-PT ro ru sk sv th tr uk vi
    zh-Hans zh-Hant
""".split())
LOCALIZED_FILES = {row[0] + ".txt" for row in FIELDS["apple"]} | {
    "apple_tv_privacy_policy.txt", "privacy_choices_url.txt",
}
CONTACT_FILES = {"first_name.txt", "last_name.txt", "phone_number.txt", "email_address.txt"}
SPECIAL_FILES = {
    "default": LOCALIZED_FILES,
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


def apple_locales(fl):
    """Include known locales and directories containing localized deliver assets."""
    meta = os.path.join(fl, "metadata")
    shots = os.path.join(fl, "screenshots")
    names = {n for n in _subdirs(meta) if n not in NOT_LOCALES
             and (n in APPLE_LOCALES or _has_files(os.path.join(meta, n), LOCALIZED_FILES))}
    names.update(n for n in _subdirs(shots) if n in APPLE_LOCALES or images(os.path.join(shots, n)))
    return [os.path.join(meta, n) for n in sorted(names)]


def apple_default(fl):
    """metadata/default (deliver's fallback values) if present, else None."""
    d = os.path.join(fl, "metadata", "default")
    return d if _has_files(d, LOCALIZED_FILES) else None


def has_apple_app_metadata(fl):
    """True if fastlane/metadata holds recognized deliver files at app level or in its special folders."""
    meta = os.path.join(fl, "metadata")
    return _has_files(meta, DELIVER_APP_FILES) or any(
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
