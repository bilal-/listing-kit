#!/usr/bin/env python3
"""Read a listing plan. Its format is unstable until listing-kit 1.0.

Usage: plan.py {check [--for capture|publish]|manifest|outputs} <app-root>
"""

import argparse
from collections import Counter
import difflib
from fractions import Fraction
import json
from pathlib import Path
import re
import sys

if __package__:
    from . import json_input, specs
else:
    import json_input
    import specs


FORMAT = 2
# Inter from google/fonts at 0b58fb370093f9a9f4ff785d94405710b79de67c, licensed in assets/fonts/OFL.txt.
BUNDLED_FONTS = ["Inter"]
LISTING = Path(".listing-kit/listing.json")
LOCALE = re.compile(r"[a-z]{2,3}(-[A-Za-z0-9]{2,8})*")


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


def raw_path(target, screen, locale_id):
    for kind, item in (("target", target), ("screen", screen)):
        if not specs.identifier(item["id"]):
            raise PlanError([("ERROR", kind + ".id", "invalid capture path component")])
    if not specs.component(locale_id):
        raise PlanError([("ERROR", "locale.id", "invalid capture path component")])
    return f".listing-kit/raw/{target['id']}/{locale_id}/{screen['id']}.png"


def text(value, locale, locales):
    """Return (copy, fallback used). An explicit empty translation is complete."""
    if locale in value:
        return value[locale], False
    primary = locales[0]
    primary_id = primary["id"] if isinstance(primary, dict) else primary
    return value.get(primary_id, ""), True


def flow_for(screen, target):
    if "panel" in screen:
        return None
    flows = screen.get("flows", {})
    return flows.get(target["id"], flows.get(target["store"], screen["flow"]))


def _filename(index, target, screen, slot):
    if not specs.identifier(screen["id"]):
        raise PlanError([("ERROR", "screen.id", "invalid screenshot path component")])
    stem = "{:02d}_{}".format(index, screen["id"])
    if target["store"] == "apple" or "suffix" in target:
        suffix = target.get("suffix", slot.get("suffix"))
        if not specs.identifier(suffix):
            raise PlanError([("ERROR", "suffix", "invalid screenshot filename suffix")])
        stem += "_" + suffix
    return stem + ".png"


def output_name(data, target, screen, rules):
    """Name within the locale directory, numbered among this target's screens."""
    problems = specs.check(rules)
    if problems:
        raise PlanError(problems)
    slot = specs.slot(rules, target["store"], target["slot"])
    if slot is None:
        raise PlanError([("ERROR", "target.slot", "unknown screenshot slot")])
    for index, item in enumerate(screens_for(data, target["id"]), 1):
        if item["id"] == screen["id"]:
            return _filename(index, target, screen, slot)
    raise ValueError("screen %s does not apply to %s" % (screen["id"], target["id"]))


def _trees(data):
    configured = data.get("trees", {})
    apple = configured.get("apple", {})
    play = configured.get("play", {})
    ios = Path(apple.get("fastlaneDir", "fastlane"))
    android = Path(play.get("fastlaneDir", "fastlane"))
    return {"apple": {"fastlaneDir": ios, "screenshots": Path(apple.get("screenshots", ios / "screenshots")),
                      "metadata": Path(apple.get("metadata", ios / "metadata"))},
            "play": {"fastlaneDir": android, "metadata": Path(play.get("metadata", android / "metadata/android"))},
            "storeAssets": Path(configured.get("storeAssets", "store-assets"))}


def _output_dir(trees, target, code, slot):
    if target.get("upload", slot["upload"]) == "console":
        return trees["storeAssets"] / target["store"] / code / "screenshots" / slot["id"]
    if target["store"] == "play":
        return trees["play"]["metadata"] / code / "images" / slot["folder"]
    return trees["apple"]["screenshots"] / code / slot.get("folder", "")


def _repo_root(app_root):
    for folder in (app_root, *app_root.parents):
        marker = folder / ".git"
        if marker.is_file() or marker.is_dir():
            return folder
    return None


def _inside(base, candidate):
    """Resolve existing symlinks, including those in a path that doesn't yet exist."""
    resolved = candidate.resolve()
    resolved.relative_to(base)
    if resolved == base:
        raise ValueError("expected a path below %s" % base)
    return resolved


def _destination(root, path):
    parent = root
    for part in path.parts:
        if not specs.component(part):
            raise ValueError("invalid destination component %r" % part)
        parent = _inside(root, parent / part)
    return parent


def _size_accepted(rules, store, slot, size):
    w, h = size
    if store == "apple":
        return slot in specs.apple_slots_for_size(rules, w, h)

    if "sizes" in slot and list(size) not in slot["sizes"]:
        return False
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


def _key(path, name):
    return path + "." + name if path else name


def _suggest(name, choices):
    nearest = difflib.get_close_matches(name, choices, n=1, cutoff=0)
    return " (did you mean %r?)" % nearest[0] if nearest else ""


class _Checker:
    """Field declarations describe JSON types. Methods check relationships and store rules."""

    def __init__(self, rules, app_root, purpose):
        self.app_root = Path(app_root).resolve()
        self.repo_root = _repo_root(self.app_root)
        self.purpose = purpose
        self.inputs = {self.app_root / LISTING, self.app_root / specs.OVERRIDE}
        self.sources = {}
        self.stale = []
        self.rules = rules
        self.problems = []
        self.rows = []
        self.locales = {}
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
                      android=self.nonempty, demoEntry=self.file_ref):
            if ("id" in value) == ("ios" in value or "android" in value):
                self.error(path, "supply a shared id or platform ids (ios, android)")

    def nonempty(self, value, path):
        if not isinstance(value, str) or not value.strip():
            self.error(path, "expected a non-empty string")

    def filename_id(self, value, path):
        if not specs.identifier(value):
            self.error(path, "expected a portable id matching " + specs.ID.pattern)

    def warn(self, path, message):
        self.problems.append(("WARN", path, message))

    def file_ref(self, value, path, font=False, flow=False):
        if not isinstance(value, str):
            self.error(path, "expected a path string")
            return
        if font and value.startswith("bundled:"):
            name = value[len("bundled:"):]
            if name not in BUNDLED_FONTS:
                self.error(path, f"unknown bundled font {name!r}")
            else:
                bundled = Path(__file__).resolve().parents[2] / "assets/fonts" / (name + ".ttf")
                self.inputs.add(bundled)
                if not bundled.is_file():
                    self.error(path, f"missing bundled font {name!r}")
            return
        base, relative = self.app_root, value
        try:
            if value.startswith("repo:"):
                base, relative = self.repo_root, value[len("repo:"):]
                if base is None:
                    raise ValueError("repo: requires a .git ancestor")
            parts = Path(relative).parts
            if not parts or not all(specs.component(part) for part in parts):
                raise ValueError("expected a relative path without parent components")
            resolved = _inside(base, base.joinpath(*parts))
        except (ValueError, OSError, RuntimeError) as exc:
            self.error(path, "invalid file reference: %s" % exc)
            return
        self.inputs.add(resolved)
        if path.endswith(".from"):
            self.sources[path] = resolved
        if flow and self.app_root / ".listing-kit/flows" not in resolved.parents:
            self.warn(path, "flow is outside .listing-kit/flows")
        if not resolved.is_file():
            report = self.error if self.purpose == "capture" else self.warn
            report(path, "missing input file: " + value)

    def flow(self, value, path):
        self.file_ref(value, path, flow=True)

    def font(self, value, path):
        self.file_ref(value, path, font=True)

    def store_code(self, value, path):
        if value is None:
            return
        if not specs.component(value) or not LOCALE.fullmatch(value):
            self.error(path, "expected a portable locale code")
        elif path.endswith(".apple") and value not in self.rules["stores"]["apple"]["locales"]:
            self.error(path, f"unknown Apple locale {value!r}")

    def locales_field(self, value, path):
        if not isinstance(value, list) or not value:
            self.error(path, "expected a non-empty list of distinct locales")
            return
        seen = {k: set() for k in ("id", "apple", "play")}
        for i, item in enumerate(value):
            child = f"{path}[{i}]"
            entry = dict(id=item, apple=item, play=item) if isinstance(item, str) else item
            if not self.obj(entry, child, ("id",), id=self.locale_id, apple=self.store_code, play=self.store_code):
                continue
            if entry.get("apple") is None and entry.get("play") is None:
                self.error(child, "expected at least one store code")
            for key in seen:
                code = entry.get(key)
                if isinstance(code, str):
                    if code.casefold() in seen[key]:
                        self.error(child + "." + key, "duplicate locale " + key)
                    seen[key].add(code.casefold())
            if isinstance(entry.get("id"), str):
                self.locales[entry["id"]] = {k: v for k, v in entry.items() if v is not None}

    def locale_id(self, value, path):
        if not specs.component(value):
            self.error(path, "expected a portable locale id")

    def locale_list(self, value, path):
        self.visit(value, path, [self.locale_id])
        if isinstance(value, list):
            names = [name for name in value if isinstance(name, str)]
            if not value or len(names) != len(set(names)):
                self.error(path, "expected a non-empty list of distinct locales")
            for i, name in enumerate(value):
                if isinstance(name, str) and name not in self.locales:
                    self.error(f"{path}[{i}]", f"unknown locale {name!r}")

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
            if name != "default" and name not in self.locales:
                self.error(_key(path, name), f"unknown locale {name!r}")
            self.obj(profile, _key(path, name), headline=[self.font], detail=[self.font])

    def palette(self, value, path):
        self.obj(value, path, background=[str], ink=str, detail=str)

    def bezel(self, value, path):
        self.obj(value, path, color=str, bleed=bool)

    def style(self, value, path):
        self.obj(value, path, mode=("raw", "framed"), template=self.nonempty, fit=self.nonempty,
                 palette=self.palette, bezel=self.bezel, fonts=self.fonts, logo=self.file_ref)

    def capture(self, value, path):
        self.obj(value, path, deviceType=self.nonempty, display=self.nonempty,
                 orientation=("portrait", "landscape"), nativeSize=self.size,
                 runtime=self.nonempty, appId=self.nonempty)

    def size(self, value, path):
        if not specs._size(value):
            self.error(path, "expected two positive integers")

    def identifier(self, value, path, seen):
        if not specs.identifier(value):
            self.error(path, "expected an id matching " + specs.ID.pattern)
        elif value in seen:
            self.error(path, "duplicate id %r" % value)
        else:
            seen.add(value)

    def target(self, t, path):
        if not self.obj(t, path, ("id", "store", "slot", "size", "state"),
                        id=str, store=("apple", "play"), slot=self.nonempty, size=[int],
                        state=("active", "deferred", "retired"), reason=str,
                        suffix=self.filename_id, upload=("fastlane", "console"),
                        locales=self.locale_list, style=self.style, capture=self.capture, captureLocales=("primary", "all"),
                        status=self.nonempty, draft=bool):
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
        if store == "apple" and "suffix" not in t and not specs.identifier(slot.get("suffix")):
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
            if target not in ("apple", "play"):
                self.target_ref(target, child)
            self.flow(flow, child)

    def row(self, value, path):
        self.obj(value, path, ("label", "text"), label=self.localized, text=self.localized)

    def panel(self, value, path):
        self.obj(value, path, ("headline", "rows"), headline=self.localized, rows=[self.row])

    def screen(self, s, path):
        if not self.obj(s, path, ("id",), id=str, flow=self.flow, flows=self.flows,
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

    def graphic(self, value, path):
        is_icon = path == "graphics.play.icon"
        self.obj(value, path, ("from",) if is_icon else ("headline",),
                 template=self.nonempty, headline=self.localized, detail=self.localized,
                 altText=self.localized, draft=bool, status=self.nonempty, palette=self.palette,
                 logo=self.file_ref, **({"from": self.file_ref} if is_icon else {}))

    def store_graphics(self, value, path):
        store = path.split(".")[-1]
        rules = self.rules["stores"][store]["graphics"]
        self.obj(value, path, **{g["id"]: self.graphic for g in rules})

    def graphics(self, value, path):
        self.obj(value, path, apple=self.store_graphics, play=self.store_graphics)

    def tree_path(self, value, path):
        try:
            if not isinstance(value, str) or not Path(value).parts:
                raise ValueError("expected a relative directory")
            resolved = _destination(self.app_root, Path(value))
            if resolved.exists() and not resolved.is_dir():
                raise ValueError("expected a directory")
        except (ValueError, OSError, RuntimeError) as exc:
            self.error(path, "invalid tree: %s" % exc)

    def trees(self, value, path):
        def store(obj, key):
            fields = {"fastlaneDir": self.tree_path, "metadata": self.tree_path}
            if key == "trees.apple":
                fields["screenshots"] = self.tree_path
            self.obj(obj, key, **fields)
        self.obj(value, path, apple=store, play=store, storeAssets=self.tree_path)

    def platforms(self, value, path):
        if not isinstance(value, dict):
            self.error(path, "expected an object")
            return
        for name, flag in value.items():
            if name not in self.rules.get("conditions", {}):
                self.error(_key(path, name), f"unknown condition {name!r}")
            self.visit(flag, _key(path, name), bool)

    def approved(self, value, path):
        self.obj(value, path, metadata=bool, screens=bool)

    def console(self, value, path):
        def nullable_string(v, p):
            if v is not None:
                self.visit(v, p, str)
        self.obj(value, path, playCategory=nullable_string, contactEmail=nullable_string,
                 playPrivacyUrl=nullable_string)

    def target_locales(self, target):
        return [self.locales[name] for name in target.get("locales", self.locales)
                if target["store"] in self.locales[name]]

    def active_targets(self, data):
        groups = {}
        totals = Counter()
        used = set()
        for i, target in enumerate(data["targets"]):
            if target["state"] != "active":
                continue
            path = f"targets[{i}]"
            store = target["store"]
            platform = "ios" if store == "apple" else "android"
            app = data["app"]
            if isinstance(app, dict) and "id" not in app and platform not in app:
                self.error("app." + platform, "required for active target " + target["id"])
            slot = specs.slot(self.rules, store, target["slot"])
            applicable = screens_for(data, target["id"])
            locales = self.target_locales(target)
            if not applicable or not locales:
                self.warn(path, "active target produces no screenshots")
            if locales:
                used.update(s["id"] for s in applicable)
            count = len(applicable)
            for locale in locales:
                if not data["screens"]:
                    continue
                key = (store, slot["id"], locale["id"], target.get("upload", slot["upload"]))
                _, sizes = groups.setdefault(key, (path, Counter()))
                sizes[tuple(target["size"])] += count
                if store == "play":
                    totals[locale["id"]] += count
            panels = sum("panel" in s for s in applicable)
            if panels and locales:
                if slot["framing"] == "forbidden":
                    self.error(path, "panels are forbidden on slot " + slot["id"])
                if count <= 2:
                    self.error(path, "panels require at least three applicable screens")
                elif 2 * panels >= count:
                    self.error(path, "panels must be fewer than half of the applicable screens")
                if "panel" in applicable[0]:
                    self.warn(path, "the first applicable screen is a panel")

        for (store, slot_id, locale, _), (path, sizes) in groups.items():
            slot = specs.slot(self.rules, store, slot_id)
            count = sum(sizes.values())
            if not slot["min"] <= count <= slot["max"]:
                self.error(path, "%s requires %d to %d screens for %s; found %d" %
                           (slot_id, slot["min"], slot["max"], locale, count))
            if count and "minPerSize" in slot:
                need = slot["minPerSize"]
                for w, h in slot["sizes"]:
                    n = sizes[(w, h)]
                    if n < need:
                        self.error(path, f"{slot_id} requires {need} screens at {w}x{h} for {locale}; found {n}")
        minimum = self.rules["stores"]["play"]["screenshots"]["minTotal"]
        for locale, count in totals.items():
            if count < minimum:
                self.error("targets", "Play requires at least %d screenshots for %s; found %d" %
                           (minimum, locale, count))
        if data["targets"] and not targets(data):
            self.warn("$", "no active targets")
        elif not data["targets"] or not data["screens"]:
            self.warn("$", "nothing planned yet")
        for i, screen in enumerate(data["screens"]):
            if screen["id"] not in used:
                self.warn(f"screens[{i}]", "screen applies to no active target")

    def requirements(self, data):
        active = {(t["store"], t["slot"]) for t in targets(data) if self.target_locales(t)}
        facts = specs.conditions_from_plan(data, rules=self.rules)
        for store in ("apple", "play"):
            for slot in specs.slots(self.rules, store):
                if (store, slot["id"]) in active:
                    continue
                required, why = specs.requirement(slot["required"], facts)
                if required == "required":
                    self.warn("targets", f"missing required {store} slot {slot['id']}")
                elif required == "upcoming" and slot["required"].get("condition") in facts:
                    self.warn("targets", f"{slot['id']}: {why}")

    def fallback(self, item, path, locale):
        missing = False
        primary = next(iter(self.locales))
        for field in ("caption", "detail", "altText", "headline", "label", "text"):
            if field in item and text(item[field], locale, [primary])[1]:
                message = f"missing translation; using {primary}" if primary in item[field] else "missing translation; using empty text"
                diagnostic = ("WARN", f"{path}.{field}.{locale}", message)
                if diagnostic not in self.problems:
                    self.problems.append(diagnostic)
                missing = True
        if "panel" in item:
            missing |= self.fallback(item["panel"], path + ".panel", locale)
        for i, row in enumerate(item.get("rows", [])):
            missing |= self.fallback(row, f"{path}.rows[{i}]", locale)
        return missing

    def output_records(self, data, trees):
        screen_paths = {s["id"]: f"screens[{i}]" for i, s in enumerate(data["screens"])}
        for target in targets(data):
            store = target["store"]
            slot = specs.slot(self.rules, store, target["slot"])
            style = {**data.get("style", {}), **target.get("style", {})}
            locales = self.target_locales(target)
            for index, screen in enumerate(screens_for(data, target["id"]), 1):
                name = _filename(index, target, screen, slot)
                for locale in locales:
                    code, loc = locale[store], locale["id"]
                    capture = loc if target.get("captureLocales") == "all" else locales[0]["id"]
                    output = _output_dir(trees, target, code, slot) / name
                    upload = target.get("upload", slot["upload"])
                    if store == "apple" and upload == "fastlane":
                        matches = specs.apple_slots_for_size(self.rules, *target["size"])
                        if any(candidate["id"] == "vision-pro" for candidate in matches):
                            selected = specs.apple_slot_for_file(self.rules, *target["size"], output.as_posix())
                            if selected["id"] != slot["id"]:
                                self.error(f"{target['id']}/{screen['id']}",
                                           f"Apple upload path selects {selected['id']} instead of {slot['id']}")
                    flow = flow_for(screen, target)
                    yield dict(kind="screenshot", store=store, localeId=loc, storeCode=code,
                               targetId=target["id"], slotId=slot["id"], screenId=screen["id"],
                               index=index, size=target["size"], styleMode=style.get("mode", "raw"),
                               template=style.get("template", slot.get("defaultTemplate")),
                               flowPath=flow, rawPath=raw_path(target, screen, capture) if flow else None,
                               outputPath=output.as_posix(), upload=upload,
                               draft=target.get("draft", False) or screen.get("draft", False),
                               textFallback=self.fallback(screen, screen_paths[screen["id"]], loc))
        for store, graphics in data.get("graphics", {}).items():
            rules = {g["id"]: g for g in self.rules["stores"][store]["graphics"]}
            for name, graphic in graphics.items():
                rule = rules[name]
                for loc, locale in self.locales.items():
                    if store not in locale:
                        continue
                    code = locale[store]
                    if rule["upload"] == "console":
                        folder = trees["storeAssets"] / store / code
                    elif store == "apple":
                        folder = trees[store]["metadata"] / code
                    else:
                        folder = trees[store]["metadata"] / code / "images"
                    yield dict(kind="graphic", store=store, localeId=loc, storeCode=code,
                               targetId=None, slotId=name, screenId=None, index=None, size=rule["size"],
                               styleMode="graphic", template=graphic.get("template"), flowPath=None,
                               rawPath=None, outputPath=(folder / (rule["file"] + ".png")).as_posix(),
                               upload=rule["upload"], draft=graphic.get("draft", False),
                               textFallback=self.fallback(graphic, f"graphics.{store}.{name}", loc))

    def destinations(self, data):
        trees = _trees(data)
        owners, raw_seen, planned = {}, set(), set()

        def claim(path, owner):
            try:
                resolved = _destination(self.app_root, Path(path))
            except (OSError, RuntimeError, ValueError) as exc:
                self.error(owner, "invalid output %s: %s" % (path, exc))
                return
            keys = {str(self.app_root / path).casefold(), str(resolved).casefold()}
            for key in sorted(keys):
                if key in owners:
                    self.error(owner, "%s and %s both claim %s" % (owners[key], owner, path))
                    return
            for key in keys:
                owners[key] = owner
            return resolved

        for row in self.output_records(data, trees):
            owner = (f"{row['targetId']}/{row['screenId']}" if row["kind"] == "screenshot"
                     else f"graphics.{row['store']}.{row['slotId']}")
            raw = row["rawPath"]
            if raw and raw not in raw_seen:
                claim(raw, owner)
                raw_seen.add(raw)
            dest = claim(row["outputPath"], owner)
            if dest:
                output = Path(row["outputPath"])
                planned.add((self.app_root / output.parent).resolve() / output.name)
            self.rows.append(row)
        # Compare sources after claiming all outputs, including aliases through symlinks.
        for path, resolved in self.sources.items():
            if str(resolved).casefold() in owners:
                self.error(path, "source is a planned output: " + str(resolved.relative_to(self.app_root)))
        if not any(level == "ERROR" for level, _, _ in self.problems):
            for relative in _existing_outputs(self.app_root, trees):
                if (self.app_root / relative.parent).resolve() / relative.name not in planned:
                    self.stale.append(relative.as_posix())
            self.stale = sorted(set(self.stale))
            report = self.error if self.purpose == "publish" else self.warn
            for path in self.stale:
                report(path, "stale output")

    def plan(self, data):
        if isinstance(data, dict) and isinstance(data.get("style"), dict):
            self.mode = data["style"].get("mode", "raw")
        if self.obj(data, "", ("format", "app", "locales", "targets", "screens"),
                    format=int, app=self.app, locales=self.locales_field, trees=self.trees,
                    platforms=self.platforms, approved=self.approved, style=self.style,
                    targets=[self.target], screens=[self.screen], graphics=self.graphics,
                    console=self.console, notes=dict):
            if type(data.get("format")) is int and data["format"] != FORMAT:
                self.error("format", "newer plan format; update listing-kit" if data["format"] > FORMAT
                           else f"expected plan format {FORMAT}")
        if any(level == "ERROR" for level, _, _ in self.problems):
            return
        self.active_targets(data)
        self.requirements(data)
        self.destinations(data)
        if self.purpose == "publish":
            for group in ("targets", "screens"):
                for i, item in enumerate(data[group]):
                    if item.get("draft"):
                        self.error(f"{group}[{i}].draft", "draft cannot be published")
            for store, entries in data.get("graphics", {}).items():
                for name, graphic in entries.items():
                    if graphic.get("draft"):
                        self.error(f"graphics.{store}.{name}.draft", "draft cannot be published")


def _existing_outputs(root, trees):
    """Visit managed output directories, including locales and targets removed from the plan."""
    def children(folder):
        directory = _inside(root, root / folder)
        if directory.is_dir():
            for child in sorted(directory.iterdir()):
                yield folder / child.name

    def files(folder, ancestors=()):
        resolved = _inside(root, root / folder)
        if resolved in ancestors:
            raise ValueError(f"output directory symlink cycle: {folder}")
        for path in children(folder):
            entry = _inside(root, root / path)
            if entry.is_dir():
                yield from files(path, ancestors + (resolved,))
            else:
                yield path

    def locale_dirs(folder):
        for loc in children(folder):
            if LOCALE.fullmatch(loc.name) and _inside(root, root / loc).is_dir():
                yield loc

    for loc in locale_dirs(trees["apple"]["screenshots"]):
        yield from files(loc)
    for loc in locale_dirs(trees["play"]["metadata"]):
        yield from files(loc / "images")
    for store in ("apple", "play"):
        for loc in locale_dirs(trees["storeAssets"] / store):
            yield from files(loc)
    # Apple metadata shares its locale directory with unrelated text fields.
    for loc in locale_dirs(trees["apple"]["metadata"]):
        for path in children(loc):
            if path.suffix.lower() in (".png", ".jpg", ".jpeg") and _inside(root, root / path).is_file():
                yield path


def _inspect(data, rules, app_root, purpose=None):
    if purpose not in (None, "capture", "publish"):
        raise ValueError("expected capture or publish")
    checker = _Checker(rules, app_root, purpose)
    checker.problems.extend(specs.check(rules))
    if not checker.problems:
        try:
            json_input.validate(data)
            checker.plan(data)
        except (OSError, ValueError, RuntimeError) as exc:
            checker.error("$", str(exc))
    return checker


def check(data, specs_data, app_root, purpose=None):
    """Check a plan against effective rules and the supplied filesystem."""
    return _inspect(data, specs_data, app_root, purpose).problems


def _validated(data, rules, app_root, purpose=None):
    checker = _inspect(data, rules, app_root, purpose)
    if any(level == "ERROR" for level, _, _ in checker.problems):
        raise PlanError(checker.problems)
    return checker


def _manifest(checker):
    return {"outputs": checker.rows, "stale": checker.stale}


def manifest(data, rules, app_root):
    """Return every planned screenshot and graphic, and stale app-relative paths."""
    return _manifest(_validated(data, rules, app_root))


def outputs(data, rules, app_root):
    """Four-column TSV view of the validated manifest records."""
    return _tsv_rows(manifest(data, rules, app_root)["outputs"])


def input_files(data, rules, app_root):
    """Return resolved input paths for scanning, including the plan and optional override."""
    return sorted(_validated(data, rules, app_root).inputs)


def _tsv_rows(records):
    for row in records:
        yield (row["targetId"] or row["store"], row["screenId"] or row["slotId"],
               row["rawPath"] or "", row["outputPath"])


class PlanError(ValueError):
    def __init__(self, problems):
        self.problems = problems
        super().__init__("\n".join(_line(p) for p in problems))


def _line(fields):
    return "\t".join(json_input.diagnostic(s) for s in fields)


def _print(message, stream):
    encoding = stream.encoding or "utf-8"
    print(str(message).encode(encoding, "backslashreplace").decode(encoding), file=stream)


def _read(app_root, purpose=None):
    try:
        root = Path(app_root).resolve()
        with _destination(root, LISTING).open(encoding="utf-8") as f:
            data = json_input.read(f)
        rules = specs.load(root)
    except FileNotFoundError:
        raise
    except (OSError, ValueError, RuntimeError, specs.SpecsError) as exc:
        raise PlanError([("ERROR", str(LISTING), str(exc))]) from exc
    return data, _validated(data, rules, root, purpose)


def load(app_root):
    """Return the validated plan. Raise FileNotFoundError or PlanError on failure."""
    return _read(app_root)[0]


def main(args):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "manifest", "outputs"):
        sub = commands.add_parser(name)
        sub.add_argument("app_root")
        if name == "check":
            sub.add_argument("--for", dest="purpose", choices=("capture", "publish"))
    args = parser.parse_args(args)
    try:
        _, checker = _read(args.app_root, getattr(args, "purpose", None))
    except FileNotFoundError:
        print(_line(("ERROR", str(LISTING), "file not found")), file=sys.stderr)
        return 2
    except PlanError as exc:
        _print(exc, sys.stdout if args.command == "check" else sys.stderr)
        return 1
    if args.command == "manifest":
        print(json.dumps(_manifest(checker)))
    else:
        rows = checker.problems if args.command == "check" else _tsv_rows(checker.rows)
        for row in rows:
            _print(_line(row), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
