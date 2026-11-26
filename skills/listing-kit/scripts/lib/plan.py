#!/usr/bin/env python3
"""Read and check .listing-kit/listing.json or list its planned screenshot outputs.

Usage: plan.py {check|outputs} <app-root>
"""

import difflib
from fractions import Fraction
import json
from pathlib import Path
import re
import sys

if __package__:
    from . import specs
else:
    import specs


FORMAT = 1
LISTING = Path(".listing-kit/listing.json")
ID = re.compile(r"[a-z0-9][a-z0-9-]*")


def targets(data, store=None, state="active"):
    """Select targets in plan order. Use state=None to include every state."""
    return [t for t in data["targets"]
            if (store is None or t["store"] == store)
            and (state is None or t["state"] == state)]


def _applies(screen, target_id):
    if "only" in screen:
        return target_id in screen["only"]
    return target_id not in screen.get("except", [])


def screens_for(data, target_id):
    return [s for s in data["screens"] if _applies(s, target_id)]


def raw_path(target, screen):
    return ".listing-kit/raw/{}/{}.png".format(target["id"], screen["id"])


def text(value, locale, locales):
    """Resolve optional localized copy, preserving explicitly empty translations."""
    if not value:
        return ""
    return value.get(locale, value.get(locales[0], ""))


def flow_for(screen, target):
    if "panel" in screen:
        return None
    return screen.get("flows", {}).get(target["id"], screen["flow"])


def _filename(index, target, screen, slot):
    stem = "{:02d}_{}".format(index, screen["id"])
    if target["store"] == "apple":
        stem += "_" + (target.get("suffix") or slot["suffix"])
    return stem + ".png"


def output_name(data, target, screen):
    """Name within the locale directory, numbered among this target's screens."""
    rules = data.rules if isinstance(data, _LoadedPlan) else specs.load()
    slot = specs.slot(rules, target["store"], target["slot"])
    for index, item in enumerate(screens_for(data, target["id"]), 1):
        if item["id"] == screen["id"]:
            return _filename(index, target, screen, slot)
    raise ValueError("screen %s does not apply to %s" % (screen["id"], target["id"]))


def _output_dir(target, locale, slot):
    if target.get("upload", slot["upload"]) == "console":
        return Path("store-assets", target["store"], locale, "screenshots", slot["id"])
    if target["store"] == "play":
        return Path("fastlane/metadata/android", locale, "images", slot["folder"])
    return Path("fastlane/screenshots", locale, slot.get("folder", ""))


def _outputs(data):
    for target in targets(data):
        slot = specs.slot(data.rules, target["store"], target["slot"])
        for index, screen in enumerate(screens_for(data, target["id"]), 1):
            name = _filename(index, target, screen, slot)
            for locale in target.get("locales", data["locales"]):
                path = _output_dir(target, locale, slot) / name
                yield target["id"], screen["id"], raw_path(target, screen), path.as_posix()


def _size_accepted(rules, store, slot, size):
    w, h = size
    if store == "apple":
        return slot in specs.apple_slots_for_size(rules, w, h)

    side = slot.get("side", {})
    if min(size) < side.get("min", 0) or max(size) > side.get("max", float("inf")):
        return False
    if any(n < limit for n, limit in zip(size, slot.get("minSize", []))):
        return False
    if "maxRatio" in slot and Fraction(max(size), min(size)) > Fraction(str(slot["maxRatio"])):
        return False
    ratios = [slot["ratio"]] if "ratio" in slot else slot.get("ratios", [])
    for ratio in ratios:
        rw, rh = map(int, ratio.split(":"))
        if w * rh == h * rw:
            return True
    return not ratios


def _safe_component(value):
    return (isinstance(value, str) and bool(value.strip()) and value not in (".", "..")
            and "/" not in value and "\\" not in value and value.isprintable())


def _key(path, name):
    return path + "." + name if path else name


def _suggest(name, choices):
    nearest = difflib.get_close_matches(name, choices, n=1, cutoff=0)
    return " (did you mean %r?)" % nearest[0] if nearest else ""


class _Checker:
    """Field declarations describe JSON types. Methods check relationships and store rules."""

    def __init__(self, rules):
        self.rules = rules
        self.problems = []
        self.locales = set()
        self.target_ids = set()
        self.screen_ids = set()
        self.mode = "raw"

    def error(self, path, message):
        self.problems.append(("ERROR", path or "$", message))

    def visit(self, value, path, field):
        if isinstance(field, list):
            if not isinstance(value, list):
                self.error(path, "expected an array")
                return
            for i, item in enumerate(value):
                self.visit(item, "%s[%d]" % (path, i), field[0])
        elif isinstance(field, tuple):
            if value not in field:
                self.error(path, "expected one of " + ", ".join(field))
        elif isinstance(field, type):
            # JSON booleans are not integers.
            if not isinstance(value, field) or (field is int and isinstance(value, bool)):
                name = {str: "a string", int: "an integer", bool: "a boolean", dict: "an object"}
                self.error(path, "expected " + name[field])
        else:
            field(value, path)

    def obj(self, value, path, required=(), **fields):
        if not isinstance(value, dict):
            self.error(path, "expected an object")
            return False
        for key in sorted(value.keys() - fields.keys()):
            self.error(_key(path, key), "unknown key %r" % key + _suggest(key, fields))
        # Declaration order establishes locales and target ids before checking references.
        for key, field in fields.items():
            child = _key(path, key)
            if key in value:
                self.visit(value[key], child, field)
            elif key in required:
                self.error(child, "required key is missing")
        return True

    def app(self, value, path):
        if isinstance(value, str):
            self.nonempty(value, path)
        elif self.obj(value, path, id=self.nonempty, ios=self.nonempty,
                      android=self.nonempty, demoEntry=self.nonempty):
            if ("id" in value) == ("ios" in value or "android" in value):
                self.error(path, "supply a shared id or platform ids (ios, android)")

    def nonempty(self, value, path):
        if not isinstance(value, str) or not value.strip():
            self.error(path, "expected a non-empty string")

    def component(self, value, path):
        if not _safe_component(value):
            self.error(path, "expected a safe path component")

    def locale_list(self, value, path):
        self.visit(value, path, [self.component])
        if isinstance(value, list):
            names = [v for v in value if isinstance(v, str)]
            if not value or len(names) != len(set(names)):
                self.error(path, "expected a non-empty list of distinct locales")
            if path == "locales":
                self.locales.update(names)
            else:
                for i, locale in enumerate(value):
                    if isinstance(locale, str) and locale not in self.locales:
                        self.error("%s[%d]" % (path, i), "unknown locale %r" % locale)

    def localized(self, value, path):
        if not isinstance(value, dict):
            self.error(path, "expected an object keyed by locale")
            return
        for locale, copy in value.items():
            child = _key(path, locale)
            if locale not in self.locales:
                self.error(child, "unknown locale %r" % locale + _suggest(locale, self.locales))
            self.visit(copy, child, str)

    def fonts(self, value, path):
        if not isinstance(value, dict):
            self.error(path, "expected an object of font profiles")
            return
        for name, profile in value.items():
            self.obj(profile, _key(path, name), headline=[self.nonempty], detail=[self.nonempty])

    def palette(self, value, path):
        self.obj(value, path, background=[str], ink=str, detail=str)

    def bezel(self, value, path):
        self.obj(value, path, color=str, bleed=bool)

    def style(self, value, path):
        self.obj(value, path, mode=("raw", "framed"), template=self.nonempty, fit=self.nonempty,
                 palette=self.palette, bezel=self.bezel, fonts=self.fonts, logo=self.nonempty)

    def capture(self, value, path):
        self.obj(value, path, deviceType=self.nonempty, display=self.nonempty,
                 orientation=("portrait", "landscape"))

    def identifier(self, value, path, seen):
        if not isinstance(value, str) or not ID.fullmatch(value):
            self.error(path, "expected an id matching " + ID.pattern)
        elif value in seen:
            self.error(path, "duplicate id %r" % value)
        else:
            seen.add(value)

    def target(self, t, path):
        if not self.obj(t, path, ("id", "store", "slot", "size", "state"),
                        id=str, store=("apple", "play"), slot=self.nonempty, size=[int],
                        state=("active", "deferred", "retired"), reason=str,
                        suffix=self.component, upload=("fastlane", "console"),
                        locales=self.locale_list, style=self.style, capture=self.capture):
            return
        if "id" in t:
            self.identifier(t["id"], path + ".id", self.target_ids)
        if t.get("state") == "deferred":
            reason = t.get("reason")
            if not isinstance(reason, str) or not reason.strip() or reason.splitlines() != [reason]:
                self.error(path + ".reason", "deferred targets need a non-empty, single-line reason")

        store = t.get("store")
        if store not in ("apple", "play") or not isinstance(t.get("slot"), str):
            return
        slot = specs.slot(self.rules, store, t["slot"])
        if slot is None:
            self.error(path + ".slot", "unknown %s slot %r" % (store, t["slot"]))
            return

        size = t.get("size")
        if isinstance(size, list):
            if len(size) != 2 or not all(type(n) is int and n > 0 for n in size):
                self.error(path + ".size", "expected two positive integer dimensions")
            elif not _size_accepted(self.rules, store, slot, size):
                self.error(path + ".size", f"{size[0]}x{size[1]} is not accepted by {slot['id']}")
        style = t.get("style", {})
        if isinstance(style, dict) and slot.get("framing") == "forbidden":
            if style.get("mode", self.mode) != "raw":
                self.error(path + ".style.mode", "%s requires raw style" % slot["id"])
        if store == "apple" and "suffix" not in t and not _safe_component(slot.get("suffix")):
            self.error(path + ".suffix", "supply a filename suffix for this slot")
        if store == "play" and t.get("upload", slot["upload"]) == "fastlane" and not slot.get("folder"):
            self.error(path + ".upload", "this slot has no fastlane folder; use console")

    def target_ref(self, value, path):
        if not isinstance(value, str):
            self.error(path, "expected a target id string")
        elif value not in self.target_ids:
            self.error(path, "unknown target id %r" % value + _suggest(value, self.target_ids))

    def flows(self, value, path):
        if not isinstance(value, dict):
            self.error(path, "expected an object keyed by target id")
            return
        for target, flow in value.items():
            child = _key(path, target)
            self.target_ref(target, child)
            self.nonempty(flow, child)

    def row(self, value, path):
        self.obj(value, path, ("label", "text"), label=self.localized, text=self.localized)

    def panel(self, value, path):
        self.obj(value, path, ("headline", "rows"), headline=self.localized, rows=[self.row])

    def screen(self, s, path):
        if not self.obj(s, path, ("id",), id=str, flow=self.nonempty, flows=self.flows,
                        panel=self.panel, route=str, state=str, caption=self.localized,
                        detail=self.localized, altText=self.localized, draft=bool,
                        only=[self.target_ref], **{"except": [self.target_ref]}):
            return
        if "id" in s:
            self.identifier(s["id"], path + ".id", self.screen_ids)
        if ("flow" in s) == ("panel" in s):
            self.error(path, "a screen must have exactly one of flow or panel")
        if "flows" in s and "panel" in s:
            self.error(path + ".flows", "only capture screens can override a flow")
        if "only" in s and "except" in s:
            self.error(path, "only and except cannot both be set")

    def feature(self, value, path):
        self.obj(value, path, ("headline",), template=self.nonempty, headline=self.localized,
                 detail=self.localized, altText=self.localized, draft=bool)

    def header(self, value, path):
        self.obj(value, path, ("canvas", "headline"), canvas=("16x9", "21x9"),
                 headline=self.localized, detail=self.localized, altText=self.localized, draft=bool)

    def icon(self, value, path):
        self.obj(value, path, ("from",), **{"from": self.nonempty, "draft": bool})

    def graphics(self, value, path):
        self.obj(value, path, playFeature=self.feature, appleHeaders=[self.header], playIcon=self.icon)

    def console(self, value, path):
        def nullable_string(v, p):
            if v is not None:
                self.visit(v, p, str)
        self.obj(value, path, playCategory=nullable_string, contactEmail=nullable_string,
                 playPrivacyUrl=nullable_string)

    def panel_counts(self, data):
        screens = data.get("screens")
        if not isinstance(screens, list) or not isinstance(data.get("targets"), list):
            return
        for i, target in enumerate(data["targets"]):
            if not isinstance(target, dict) or target.get("state") != "active":
                continue
            applicable = [s for s in screens if isinstance(s, dict)
                          and all(isinstance(s.get(k, []), list) for k in ("only", "except"))
                          and _applies(s, target.get("id"))]
            panels = sum("panel" in s for s in applicable)
            if not panels:
                continue
            path = "targets[%d]" % i
            if len(applicable) <= 2:
                self.error(path, "panels require at least three applicable screens")
            elif 2 * panels >= len(applicable):
                self.error(path, "panels must be fewer than half of the applicable screens")
            if "panel" in applicable[0]:
                self.problems.append(("WARN", path, "the first applicable screen is a panel"))

    def plan(self, data):
        if isinstance(data, dict) and isinstance(data.get("style"), dict):
            self.mode = data["style"].get("mode", "raw")
        if self.obj(data, "", ("schema", "format", "app", "locales", "targets", "screens"),
                    schema=int, format=int, app=self.app, locales=self.locale_list, style=self.style,
                    targets=[self.target], screens=[self.screen], graphics=self.graphics,
                    console=self.console, notes=dict):
            if type(data.get("schema")) is int and data["schema"] != 0:
                self.error("schema", "expected schema 0")
            if type(data.get("format")) is int and data["format"] > FORMAT:
                self.error("format", "newer plan format; update listing-kit")
            self.panel_counts(data)


def check(data, specs_data):
    """Return (ERROR or WARN, JSON path, message) tuples without changing the plan."""
    checker = _Checker(specs_data)
    checker.plan(data)
    return checker.problems


class PlanError(ValueError):
    def __init__(self, problems):
        self.problems = problems
        super().__init__("\n".join(_line(p) for p in problems))


def _line(fields):
    # Keep arbitrary JSON keys and parser/IO diagnostics within a single TSV row.
    return "\t".join(s.replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n")
                     for s in fields)


class _LoadedPlan(dict):
    """Carry the effective store rules without adding private keys to the user's JSON."""

    def __init__(self, data, rules):
        super().__init__(data)
        self.rules = rules


def _read(app_root):
    try:
        with (Path(app_root) / LISTING).open(encoding="utf-8") as f:
            data = json.load(f)
        rules = specs.load(app_root)
    except FileNotFoundError:
        raise
    except (OSError, ValueError, specs.SpecsError) as exc:
        raise PlanError([("ERROR", str(LISTING), str(exc))]) from exc
    problems = check(data, rules)
    if any(level == "ERROR" for level, _, _ in problems):
        raise PlanError(problems)
    return _LoadedPlan(data, rules), problems


def load(app_root):
    """Return a validated plan. Raise FileNotFoundError or PlanError on failure."""
    return _read(app_root)[0]


def main(args):
    if len(args) != 2 or args[0] not in ("check", "outputs"):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        data, problems = _read(args[1])
    except FileNotFoundError:
        print(_line(("ERROR", str(LISTING), "file not found")), file=sys.stderr)
        return 2
    except PlanError as exc:
        print(exc, file=sys.stdout if args[0] == "check" else sys.stderr)
        return 1
    rows = problems if args[0] == "check" else _outputs(data)
    for row in rows:
        print(_line(row))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
