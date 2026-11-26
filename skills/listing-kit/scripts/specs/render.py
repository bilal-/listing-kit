#!/usr/bin/env python3
"""Regenerate just the marked store reference tables, or verify them with --check."""
import argparse
from pathlib import Path
import re
import sys

KIT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KIT / "scripts/lib"))
import specs


def table(columns, rows):
    def line(values):
        return "| " + " | ".join(str(v).replace("|", r"\|").replace("\n", " ") for v in values) + " |"
    return "\n".join([line(columns), line(["---"] * len(columns))] + [line(row) for row in rows])


def condition(rules, name):
    description = rules["conditions"][name].rstrip(".")
    return description[:1].lower() + description[1:]


def requirement(rule, rules):
    if rule["rule"] == "never":
        return "Optional"
    text = "Required"
    if rule["rule"] == "if":
        text += " if " + condition(rules, rule["condition"])
    if "from" in rule:
        text += " from " + rule["from"]
    if "unless" in rule:
        text += " unless " + condition(rules, rule["unless"])
    return text


def size(pair):
    return "×".join(map(str, pair))


def dimensions(slot):
    parts = list(map(size, slot.get("sizes", [])))
    if "side" in slot:
        side = slot["side"]
        parts.append("sides " + "–".join(str(side[k]) for k in ("min", "max") if k in side) + " px" +
                     (" minimum" if "max" not in side else ""))
    if "minSize" in slot:
        parts.append("minimum " + size(slot["minSize"]))
    if "maxRatio" in slot:
        parts.append("up to {}:1".format(slot["maxRatio"]))
    if "ratio" in slot:
        parts.append(slot["ratio"])
    parts.extend(slot.get("ratios", []))
    if slot.get("orientation") == "fixed":
        parts.append("fixed orientation")
    if "minPerSize" in slot:
        parts.append("at least {} per size".format(slot["minPerSize"]))
    return ", ".join(parts) or "—"


def encoding(rule):
    parts = ["/".join(f.upper() for f in rule.get("formats", []))]
    if "bitDepth" in rule:
        parts.append("{} bits/channel".format(rule["bitDepth"]))
    if "alpha" in rule:
        parts.append({True: "alpha allowed", False: "no alpha", "required": "alpha required"}[rule["alpha"]])
    if rule.get("grayscaleJpeg"):
        parts.append("grayscale JPEG accepted")
    if "maxBytes" in rule:
        parts.append("≤{:,} bytes".format(rule["maxBytes"]))
    return ", ".join(filter(None, parts)) or "—"


def screenshots(store, rules):
    shot = rules["stores"][store]["screenshots"]
    rows = []
    for s in shot["slots"]:
        notes = []
        if "promotion" in s:
            p = s["promotion"]
            bounds = "{}–{}".format(p["shortSideMin"], p["longSideMax"]) if "longSideMax" in p else "≥{}".format(p["shortSideMin"])
            notes.append('Promotion: {} at {} px, {}'.format(p["count"], bounds, " or ".join(p["ratios"])))
        if s["framing"] == "forbidden":
            notes.append("Framing forbidden")
        notes.append(s.get("folder") or s["upload"])
        rows.append((s["label"], requirement(s["required"], rules), "{}–{}".format(s["min"], s["max"]),
                     dimensions(s), encoding(dict(shot, **s)), ". ".join(notes)))
    result = table(("Display class", "Requirement", "Count per locale", "Accepted size or bounds", "Format", "Delivery and notes"), rows)
    if "minTotal" in shot:
        result += "\n\nAt least {} screenshots across all device types per locale.".format(shot["minTotal"])
    return result


def fields(store, rules):
    rows = []
    data = rules["stores"][store]
    for f in data["fields"]:
        limit = "{} {}".format(f["limit"], f["unit"]) if "limit" in f else f["unit"]
        if "min" in f:
            limit = "{}–{}".format(f["min"], limit)
        rows.append((f["label"], f["stem"], f["scope"], limit, requirement(f["required"], rules)))
    if "changelogs" in data:
        log = data["changelogs"]
        rows.append(("Release notes", "changelogs/<name>", "locale", "{} {}".format(log["limit"], log["unit"]),
                     "Allowed names: `{}`".format(log["names"])))
    return table(("Field", "File stem", "Scope", "Limit or unit", "Requirement"), rows)


def graphics(store, rules):
    return table(("Graphic", "File stem", "Size", "Format", "Requirement", "Upload"),
                 [(g["label"], g["file"], size(g["size"]), encoding(g), requirement(g["required"], rules), g["upload"])
                  for g in rules["stores"][store]["graphics"]])


SOURCES = {
    "apple": {"screenshots": ["appleScreenshots"], "fields": ["appleAppInfo", "appleVersionInfo"],
              "graphics": ["appleCreativeAssets"]},
    "play": {"screenshots": ["playPreviewAssets"], "fields": ["playListing", "playReleaseNotes"],
             "graphics": ["playPreviewAssets"]},
}


def render(document, store, rules):
    for name, generate in (("screenshots", screenshots), ("fields", fields), ("graphics", graphics)):
        begin, end = "<!-- rules:begin " + name + " -->", "<!-- rules:end " + name + " -->"
        if document.count(begin) != 1 or document.count(end) != 1:
            raise ValueError("expected one pair of " + name + " markers")
        sources = [rules["sources"][key] for key in SOURCES[store][name] if key in rules.get("sources", {})]
        attribution = "Verified " + rules["verified"]
        if sources:
            attribution += " · " + " · ".join("[Store reference {}]({})".format(i, url)
                                               for i, url in enumerate(sources, 1))
        content = generate(store, rules) + "\n\n" + attribution
        pattern = re.escape(begin) + r".*?" + re.escape(end)
        document, count = re.subn(pattern, lambda _: begin + "\n\n" + content + "\n\n" + end,
                                  document, flags=re.S)
        if count != 1:
            raise ValueError("unpaired " + name + " markers")
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--rules", type=Path, default=Path(specs.BUNDLED))
    parser.add_argument("--app-root", type=Path)
    parser.add_argument("--docs", type=Path, default=KIT / "references/stores")
    args = parser.parse_args()
    rules = specs.load(args.app_root, args.rules)
    stale = False
    for store, name in (("apple", "apple-app-store.md"), ("play", "google-play.md")):
        path = args.docs / name
        before = path.read_text(encoding="utf-8")
        after = render(before, store, rules)
        if after != before:
            if args.check:
                print(f"Out of date: {path}", file=sys.stderr)
                stale = True
            else:
                path.write_text(after, encoding="utf-8")
    return int(stale)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, specs.SpecsError) as exc:
        sys.exit(str(exc))
