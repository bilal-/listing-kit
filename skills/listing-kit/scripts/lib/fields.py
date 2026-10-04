#!/usr/bin/env python3
"""Store copy fields (limits, units, required flags), shared by validate-listing.sh
and build-review.sh so the two never disagree. Source: references/stores/*.md.

CLI:    fields.py {apple|play} <locale-dir> [<fallback-dir>]
Prints one "LEVEL<TAB>message" line per field, LEVEL in PASS / WARN / FAIL. A field
missing from the locale is read from <fallback-dir> (fastlane's metadata/default/).
"""
import os
import sys
from urllib.parse import urlparse

# (file stem, display label, limit or None, unit, required)
# unit: "chars" = Unicode code points, "bytes" = UTF-8 bytes, "url" = http(s) URL.
FIELDS = {
    "apple": [
        ("name", "Name", 30, "chars", True),
        ("subtitle", "Subtitle", 30, "chars", False),
        ("promotional_text", "Promotional text", 170, "chars", False),
        ("keywords", "Keywords", 100, "bytes", False),
        ("description", "Description", 4000, "chars", True),
        ("support_url", "Support URL", None, "url", True),
        ("marketing_url", "Marketing URL", None, "url", False),
        ("privacy_url", "Privacy URL", None, "url", True),
    ],
    "play": [
        ("title", "Title", 30, "chars", True),
        ("short_description", "Short description", 80, "chars", True),
        ("full_description", "Full description", 4000, "chars", True),
    ],
}


class NotUTF8(Exception):
    pass


def read(path):
    """File text with trailing whitespace stripped (how fastlane measures), or None.
    Raises NotUTF8 for undecodable files (the stores require UTF-8)."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().rstrip()
    except UnicodeDecodeError as e:
        raise NotUTF8(path) from e
    except OSError:
        return None


def is_url(value):
    if len(value.split()) != 1:
        return False
    u = urlparse(value)
    return u.scheme in ("http", "https") and bool(u.hostname)


def measure(text, unit):
    return len(text.encode("utf-8")) if unit == "bytes" else len(text)


def rows(store, locale_dir, fallback_dir=None):
    out = []
    for stem, label, limit, unit, required in FIELDS[store]:
        path, error, value = os.path.join(locale_dir, stem + ".txt"), None, None
        candidates = [path] + ([os.path.join(fallback_dir, stem + ".txt")] if fallback_dir else [])
        for cand in candidates:
            if os.path.isfile(cand):
                path = cand
                try:
                    value = read(cand)
                except NotUTF8:
                    error = "not valid UTF-8"
                break
        out.append(dict(stem=stem, label=label, path=path, value=value, limit=limit, unit=unit,
                        required=required, error=error,
                        count=None if value is None else measure(value, unit)))
    return out


def check(r):
    """(level, message) for one field row."""
    stem, value = r["stem"], r["value"]
    if r.get("error"):
        return "FAIL", f"{stem}: {r['error']} ({r['path']})"
    if value is None:
        if r["required"]:
            return "FAIL", f"{stem}: REQUIRED file missing ({r['path']})"
        return "WARN", f"{stem}: optional, absent"
    if not value:
        return ("FAIL" if r["required"] else "WARN"), f"{stem}: file is empty ({r['path']})"
    if r["unit"] == "url":
        if is_url(value):
            return "PASS", f"{stem}: {value}"
        return "FAIL", f"{stem}: not a single http(s) URL: {value[:60]!r}"
    if r["count"] > r["limit"]:
        return "FAIL", f"{stem}: {r['count']}/{r['limit']} {r['unit']} OVER LIMIT"
    return "PASS", f"{stem}: {r['count']}/{r['limit']} {r['unit']}"


if __name__ == "__main__":
    for r in rows(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None):
        print("\t".join(check(r)))
