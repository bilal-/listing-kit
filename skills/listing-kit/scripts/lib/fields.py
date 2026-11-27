#!/usr/bin/env python3
"""Store copy fields (limits, units, required flags), shared by validate-listing.sh
and build-review.sh so the two never disagree. Source: specs/stores.json.

CLI:    fields.py {apple|play|apple-app|apple-review} <metadata-dir> [<fallback-dir>] --app-root <app-dir>
Prints one "LEVEL<TAB>message" line per field, LEVEL in PASS / WARN / FAIL. A field
missing from the locale is read from <fallback-dir> (fastlane's metadata/default/).
"""
import argparse
import os
import re
from pathlib import Path
import sys
import unicodedata
from urllib.parse import urlparse

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import detect
import specs


class InvalidFieldText(ValueError):
    pass


def read(path, strip=True):
    """File text with trailing whitespace stripped (how fastlane measures), or None.
    Raises InvalidFieldText for malformed store copy."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
            if "\0" in text:
                raise InvalidFieldText("contains NUL")
            return text.strip() if strip else text
    except UnicodeDecodeError as e:
        raise InvalidFieldText("not valid UTF-8") from e
    except OSError:
        return None


def is_url(value, youtube=False):
    if len(value.split()) != 1 or (youtube and "\\" in value):
        return False
    try:
        u = urlparse(value)
        if youtube and (u.scheme != "https" or "@" in u.netloc):
            return False
        # urllib validates malformed and out-of-range ports when accessed.
        u.port
    except ValueError:
        return False
    host = u.hostname or ""
    if youtube:
        return host in ("youtube.com", "youtu.be") or host.endswith(".youtube.com")
    return u.scheme in ("http", "https") and bool(host)


def measure(text, unit):
    return len(text.encode("utf-8")) if unit == "bytes" else len(text)


def _fields(rules, store, directory):
    scope = {"apple-app": "app", "apple-review": "review_information"}.get(store, "locale")
    for field in specs.fields(rules, "play" if store == "play" else "apple", scope):
        if field["unit"] != "credential":
            yield field
    if store == "play" and "changelogs" in rules["stores"]["play"]:
        logs = rules["stores"]["play"]["changelogs"]
        for path in sorted((Path(directory) / "changelogs").glob("*.txt")):
            yield dict(stem="changelogs/" + path.stem, label="Release notes (" + path.stem + ")",
                       limit=logs["limit"], unit=logs["unit"], required={"rule": "never"},
                       error=None if re.fullmatch(logs["names"], path.stem) else "invalid changelog name")


def rows(store, locale_dir, fallback_dir, rules, requirements):
    out = []
    for field in _fields(rules, store, locale_dir):
        stem, unit = field["stem"], field["unit"]
        level, reason = requirements.evaluate(field["required"])
        path = os.path.join(locale_dir, stem + ".txt")
        value, error = None, field.get("error")
        candidates = [path] + ([os.path.join(fallback_dir, stem + ".txt")] if fallback_dir else [])
        for cand in candidates:
            if os.path.isfile(cand):
                path = cand
                try:
                    value = read(cand, strip=store != "play")
                except InvalidFieldText as exc:
                    error = str(exc)
                break
        out.append(dict(stem=stem, label=field["label"], path=path, value=value,
                        limit=field.get("limit"), unit=unit, required=level == "required",
                        reason=reason, error=error, minimum=field.get("min", 0),
                        choices=rules.get(field.get("values")), store=store,
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
        return "WARN", f"{stem}: " + (r["reason"] or "optional, absent")
    if not value.strip():
        return ("FAIL" if r["required"] else "WARN"), f"{stem}: file is empty ({r['path']})"
    if r["unit"] == "email":
        if not re.fullmatch(r"[^@.\s]+(?:\.[^@.\s]+)*@[^@.\s]+(?:\.[^@.\s]+)+", value):
            return "FAIL", f"{stem}: invalid email address"
    if r["unit"] == "phone":
        number = "".join(" " if c == "\t" or unicodedata.category(c) == "Zs" else c for c in value)
        if not re.fullmatch(r"\+?(?:[0-9]|\([0-9]+\))(?:[ ./-]*(?:[0-9]|\([0-9]+\)))*"
                            r"(?: *(?:x|ext\.?) *[0-9]+)?", number, re.I):
            return "WARN", f"{stem}: unrecognised phone format, confirm it in App Store Connect"
    if r["unit"] == "YouTube URL":
        if is_url(value.strip(), youtube=True):
            return "PASS", f"{stem}: HTTPS YouTube URL"
        return "FAIL", f"{stem}: expected an HTTPS YouTube URL"
    if r["unit"] == "url":
        if is_url(value):
            return "PASS", f"{stem}: {value}"
        return "FAIL", f"{stem}: not a single http(s) URL: {value[:60]!r}"
    if r.get("choices") is not None and value not in r["choices"]:
        return "FAIL", f"{stem}: unrecognized value {value!r}"
    if r["count"] < r.get("minimum", 0):
        return "FAIL", f"{stem}: {r['count']} {r['unit']}, under the {r['minimum']}-{r['unit']} minimum"
    if r["limit"] is None:
        return "PASS", f"{stem}: set"
    if r["count"] > r["limit"]:
        fix = ""
        if r["store"] == "play" and value.endswith(("\r", "\n")):
            fix = " (supply counts the trailing newline; remove the trailing newline and recheck)"
        return "FAIL", f"{stem}: {r['count']}/{r['limit']} {r['unit']} OVER LIMIT{fix}"
    return "PASS", f"{stem}: {r['count']}/{r['limit']} {r['unit']}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store", choices=("apple", "apple-app", "apple-review", "play"))
    parser.add_argument("metadata")
    parser.add_argument("fallback", nargs="?")
    parser.add_argument("--app-root", type=Path, required=True)
    args = parser.parse_args()
    rules = specs.load(args.app_root)
    requirements = detect.Requirements(args.app_root, rules)
    for r in rows(args.store, args.metadata, args.fallback, rules, requirements):
        print("\t".join(check(r)))
