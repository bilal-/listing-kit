#!/usr/bin/env python3
"""Read a listing plan. Its format is unstable until listing-kit 1.0.

Usage: plan.py {check [--for capture|publish]|manifest|outputs} <app-root>
"""

import argparse
from collections import Counter, defaultdict
import difflib
from functools import partial
import json
import os
from pathlib import Path
import io
import re
import sys
import unicodedata

if __package__:
    from . import json_input, layout, specs, template_values, user_templates
else:
    import json_input
    import layout
    import specs
    import template_values
    import user_templates


FORMAT = 2
# Inter from google/fonts at 0b58fb370093f9a9f4ff785d94405710b79de67c, licensed in assets/fonts/OFL.txt.
BUNDLED_FONTS = ["Inter"]
LISTING = Path(".listing-kit/listing.json")
RECORD = LISTING.with_name("outputs.json")
LOCALE = re.compile(r"[a-z]{2,3}(-[A-Za-z0-9]{2,8})*")


def targets(data, store=None, state="active"):
    """Select targets in plan order. Use state=None to include every state."""
    return [t for t in data["targets"]
            if (store is None or t["store"] == store)
            and (state is None or t["state"] == state)]


def screens_for(data, target_id):
    return [s for s in data["screens"] if target_id in s.get("only", [target_id])
            and target_id not in s.get("except", [])]


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


def _fold(value):
    return unicodedata.normalize("NFC", str(value)).casefold()


def _locale(item):
    return dict(id=item, apple=item, play=item) if isinstance(item, str) else item


def _target_locales(locales, target):
    selected = target.get("locales")
    return [loc for loc in locales if loc.get(target["store"]) and (selected is None or loc["id"] in selected)]


def apple_suffixes(data, rules):
    """Custom filename suffixes for fastlane slots that share image dimensions."""
    by_locale = {}
    locales = [_locale(item) for item in data["locales"]]
    for target in targets(data, "apple"):
        slot = specs.slot(rules, "apple", target["slot"])
        if (target.get("upload", slot["upload"]) != "fastlane" or "suffix" not in target
                or len(specs.apple_slots_for_size(rules, *target["size"])) < 2):
            continue
        for loc in _target_locales(locales, target):
            by_locale.setdefault(loc["apple"], {}).setdefault(slot["id"], []).append(target["suffix"])
    return by_locale


def _allocation(data, rules, members):
    counts = Counter()
    locales = [_locale(item) for item in data["locales"]]
    for target in members:
        store = target["store"]
        slot = specs.slot(rules, store, target["slot"])
        if slot is None:
            raise PlanError([("ERROR", "target.slot", "unknown screenshot slot")])
        upload = target.get("upload", slot["upload"])
        selected = _target_locales(locales, target)
        for screen in screens_for(data, target["id"]):
            for locale in selected:
                key = store, slot["id"], upload, locale["id"]
                counts[key] += 1
                yield target, screen, slot, upload, locale, selected[0], counts[key]


def output_name(data, target, screen, rules, locale_id=None):
    """With no locale, use the target's primary locale. Preview inactive targets in isolation."""
    problems = specs.check(rules)
    if problems:
        raise PlanError(problems)
    members = targets(data) if target["state"] == "active" else [target]
    for t, s, slot, _, loc, _, index in _allocation(data, rules, members):
        if t["id"] == target["id"] and s["id"] == screen["id"] and locale_id in (None, loc["id"]):
            return _filename(index, target, screen, slot)
    raise ValueError("no applicable screenshot for %s/%s" % (target["id"], screen["id"]))


def _style(base, *layers):
    result = dict(base)
    for layer in layers:
        for key, value in layer.items():
            result[key] = _style(result.get(key, {}), value) if isinstance(value, dict) else value
    return result


def _trees(data, app_root):
    trees = data.get("trees", {})
    if "trees" not in data:
        layout.project(app_root)
    result = {}
    for store in ("apple", "play"):
        config = trees.get(store, {})
        fastlane = Path(config["fastlaneDir"]) if "fastlaneDir" in config else layout.fastlane_dir(app_root, store)
        metadata = Path(config.get("metadata", fastlane / ("metadata" if store == "apple" else "metadata/android")))
        result[store] = dict(fastlaneDir=fastlane, metadata=metadata,
                             storeAssets=Path(trees.get("storeAssets", "store-assets")) / store,
                             screenshots=Path(config.get("screenshots", fastlane / "screenshots")) if store == "apple" else metadata)
    return result


def _repo_root(app_root):
    for folder in (app_root, *app_root.parents):
        marker = folder / ".git"
        if marker.is_file() or marker.is_dir():
            return folder
    return None


def _inside(base, candidate):
    """Resolve existing symlinks, including those in a path that doesn't yet exist."""
    resolved = candidate.resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError("symlink or path leaves the selected root")
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

    return not any(specs.play_size_errors(slot, w, h))


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
        self.files = {str(p): (self.app_root / p, self.app_root / p) for p in (LISTING, specs.OVERRIDE)}
        self.captures = {}
        self.tree_errors = []
        self.rules = rules
        self.problems = []
        self.locales = {}
        self.target_ids = set()
        self.screen_ids = set()
        self.checked_templates = {}
        self.template_deadline = None
        self.template_bytes = 0
        self.input_roots = {}
        self.mode = "raw"
        tree = dict(metadata=self.tree_path, fastlaneDir=self.tree_path)
        self.trees = dict(apple=dict(tree, screenshots=self.tree_path), play=tree, storeAssets=self.tree_path)
        self.nonempty = partial(self.expect, specs._string, "expected a non-empty string")
        self.filename_id = partial(self.expect, specs.identifier, "expected a portable id matching " + specs.ID.pattern)
        self.locale_id = partial(self.expect, specs.component, "expected a portable locale id")
        self.size = partial(self.expect, specs._size, "expected two positive integers")
        self.flow = partial(self.file_ref, flow=True)
        font = partial(self.file_ref, font=True)
        self.font_roles = dict(headline=[font], detail=[font])
        colour = partial(self.expect, template_values.colour, "expected #RRGGBB or #RRGGBBAA")
        self.palette = dict(background=self.background, ink=colour, detail=colour)
        def measure(limit):
            return partial(self.expect, lambda v: template_values.measurement(v, limit), "expected number in [0, %d]" % limit)
        self.style = dict(mode=("raw", "framed"), template=self.template, fit=("contain", "cover", "bleed"), palette=self.palette,
                          bezel=dict(color=colour, shadow=colour, width=measure(10), radius=measure(50), bleed=bool), fonts=self.fonts, logo=self.file_ref)
        self.capture = dict(deviceType=self.nonempty, display=self.nonempty, orientation=("portrait", "landscape"),
                            nativeSize=self.size, runtime=self.nonempty, appId=self.nonempty)

    def template(self, value, path):
        try:
            if isinstance(value, str) and value in self.checked_templates:
                return
            if isinstance(value, str) and value.startswith("user:") and self.template_deadline is None:
                self.template_deadline = user_templates.new_deadline()
            available = user_templates.MAX_PLAN_TEMPLATE_BYTES - self.template_bytes
            template = user_templates.resolve(self.app_root, value, self.template_deadline, available)
            if template:
                self.template_bytes += template.size
                for ref in template.digests:
                    if ref.startswith("bundled:"):
                        source = user_templates.KIT / "assets" / ref[len("bundled:"):]
                    else:
                        source = self.app_root / ref
                    self.files[ref] = source, source
            self.checked_templates[value] = template
        except user_templates.TemplateTimeout:
            raise
        except ValueError as exc:
            location = str(LISTING)
            try:
                source = (self.app_root / LISTING).read_text(encoding="utf-8")
                location += f":{json_input.field_line(source, path)}"
            except (ValueError, OSError):
                pass  # In-memory plan and spec defaults need not have a source line.
            for message in str(exc).splitlines():
                self.error(path, f"{location}: {message}")

    def background(self, value, path):
        if not isinstance(value, list) or not value:
            self.error(path, "expected non-empty array of colours")
        else:
            self.visit(value, path, [self.palette["ink"]])

    def error(self, path, message):
        self.problems.append(("ERROR", path or "$", message))

    def expect(self, test, message, value, path):
        if not test(value):
            self.error(path, message)

    def visit(self, value, path, field):
        if isinstance(field, list):
            if not isinstance(value, list):
                self.error(path, "expected an array")
                return
            for i, item in enumerate(value):
                self.visit(item, "%s[%d]" % (path, i), field[0])
        elif isinstance(field, dict):
            self.obj(value, path, field)
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

    def obj(self, value, path, fields, required=()):
        if not isinstance(value, dict):
            self.error(path, "expected an object")
            return False
        for key in sorted(value.keys() - fields.keys()):
            self.error(path or "$", "unknown key" + _suggest(key, fields))
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
            value = {"id": value}
        elif self.obj(value, path, dict(id=self.nonempty, ios=self.nonempty,
                                        android=self.nonempty, demoEntry=self.file_ref)):
            if ("id" in value) == ("ios" in value or "android" in value):
                self.error(path, "supply a shared id or platform ids (ios, android)")
        else:
            return
        self.ids = {store: value.get(platform, value.get("id")) for store, platform in (("apple", "ios"), ("play", "android"))}
        self.demo = value.get("demoEntry")

    def warn(self, path, message):
        self.problems.append(("WARN", path, message))

    def file_ref(self, value, path, font=False, flow=False):
        if not isinstance(value, str):
            self.error(path, "expected a path string")
            return
        try:
            if font and value.startswith("bundled:"):
                name = value[len("bundled:"):]
                if name not in BUNDLED_FONTS:
                    self.error(path, f"unknown bundled font {name!r}")
                    return
                base = Path(__file__).resolve().parents[2] / "assets/fonts"
                source = resolved = base / (name + ".ttf")
                if self.purpose != "capture" and not resolved.is_file():
                    self.error(path, f"missing bundled font {name!r}")
                    return
            else:
                base, relative = (self.repo_root, value[5:]) if value.startswith("repo:") else (self.app_root, value)
                if base is None:
                    raise ValueError("repo: requires a .git ancestor")
                parts = Path(relative).parts
                if not parts or not all(specs.component(part) for part in parts):
                    raise ValueError("expected a relative path without parent components")
                source = base.joinpath(*parts)
                resolved = _inside(base, source)
        except (ValueError, OSError, RuntimeError) as exc:
            self.error(path, "invalid file reference: %s" % exc)
            return
        self.input_roots[resolved] = base
        self.files[value] = source, resolved
        if flow and self.app_root / ".listing-kit/flows" not in resolved.parents:
            self.warn(path, "flow is outside .listing-kit/flows")
        if self.purpose != "capture" and not resolved.is_file():
            self.warn(path, "missing input file: " + value)

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
            entry = _locale(item)
            if not self.obj(entry, child, dict(id=self.locale_id, apple=self.store_code, play=self.store_code), ("id",)):
                continue
            if entry.get("apple") is None and entry.get("play") is None:
                self.error(child, "expected at least one store code")
            for key in seen:
                code = entry.get(key)
                if isinstance(code, str):
                    code = _fold(code)
                    if code in seen[key]:
                        self.error(child + "." + key, "duplicate locale " + key)
                    seen[key].add(code)
            if isinstance(entry.get("id"), str):
                self.locales[entry["id"]] = entry

    def locale_list(self, value, path):
        self.visit(value, path, [self.locale_id])
        if isinstance(value, list):
            names = [_fold(name) for name in value if isinstance(name, str)]
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
            if locale not in self.locales:
                self.error(path, "unknown locale key" + _suggest(locale, self.locales))
                continue
            self.visit(copy, _key(path, locale), str)

    def fonts(self, value, path):
        if not isinstance(value, dict):
            self.error(path, "expected an object of font profiles")
            return
        for name, profile in value.items():
            if name != "default" and name not in self.locales:
                self.error(path, "unknown locale key")
                continue
            self.obj(profile, _key(path, name), self.font_roles)

    def identifier(self, value, path, seen):
        if not specs.identifier(value):
            self.error(path, "expected an id matching " + specs.ID.pattern)
        elif value in seen:
            self.error(path, "duplicate id %r" % value)
        else:
            seen.add(value)

    def target(self, t, path):
        if not self.obj(t, path,
                        dict(id=str, store=("apple", "play"), slot=self.nonempty, size=[int],
                        state=("active", "deferred", "retired"), reason=str,
                        suffix=self.filename_id, upload=("fastlane", "console"),
                        locales=self.locale_list, style=self.style, template=self.template, capture=self.capture, captureLocales=("primary", "all"),
                        status=self.nonempty, draft=bool), ("id", "store", "slot", "size", "state")):
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
            if not specs._size(size):
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
            if target not in ("apple", "play") and target not in self.target_ids:
                self.error(path, "unknown target key" + _suggest(target, self.target_ids))
                continue
            self.flow(flow, _key(path, target))

    def row(self, value, path):
        self.obj(value, path, dict(label=self.localized, text=self.localized), ("label", "text"))

    def panel(self, value, path):
        self.obj(value, path, dict(headline=self.localized, rows=[self.row]), ("headline", "rows"))

    def screen(self, s, path):
        if not self.obj(s, path, dict(id=str, flow=self.flow, flows=self.flows,
                        panel=self.panel, style=self.style, template=self.template, route=str, state=str, caption=self.localized,
                        detail=self.localized, altText=self.localized, draft=bool,
                        only=[self.target_ref], **{"except": [self.target_ref]}), ("id",)):
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
        self.obj(value, path,
                 dict(template=self.template, headline=self.localized, detail=self.localized,
                 altText=self.localized, draft=bool, status=self.nonempty, palette=self.palette,
                 logo=self.file_ref, **({"from": self.file_ref} if is_icon else {})), ("from",) if is_icon else ("headline",))

    def store_graphics(self, value, path):
        rules = self.rules["stores"][path.split(".")[-1]]["graphics"]
        self.obj(value, path, {g["id"]: self.graphic for g in rules})

    def tree_path(self, value, path):
        try:
            if not isinstance(value, str) or not Path(value).parts:
                raise ValueError("expected a relative directory")
            resolved = _destination(self.app_root, Path(value))
            if resolved.exists() and not resolved.is_dir():
                self.tree_errors.append(("ERROR", path, "expected directory: " + value))
        except (ValueError, OSError, RuntimeError) as exc:
            self.error(path, "invalid tree: %s" % exc)

    def platforms(self, value, path):
        if not isinstance(value, dict):
            self.error(path, "expected an object")
            return
        for name, flag in value.items():
            if name not in self.rules.get("conditions", {}):
                self.error(path, "unknown condition key")
                continue
            self.visit(flag, _key(path, name), bool)

    def console(self, value, path):
        def nullable_string(v, p):
            if v is not None:
                self.visit(v, p, str)
        self.obj(value, path, dict(playCategory=nullable_string, contactEmail=nullable_string,
                 playPrivacyUrl=nullable_string))

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
            if not self.ids[store]:
                self.error("app." + platform, "required for active target " + target["id"])
            slot = specs.slot(self.rules, store, target["slot"])
            applicable = screens_for(data, target["id"])
            locales = _target_locales(self.locales.values(), target)
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
        active = {(t["store"], t["slot"]) for t in targets(data) if _target_locales(self.locales.values(), t)}
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

    def render_fields(self, item, path, loc, style, rule, has_capture=False):
        primary = next(iter(self.locales))
        missing = []
        def copy(obj, prefix):
            strings = {}
            for key in ("caption", "detail", "altText", "headline", "label", "text"):
                if key in obj:
                    value, fallback = text(obj[key], loc, [primary])
                    strings[key] = dict(value=value, fallback=fallback)
                    if fallback:
                        default = primary if primary in obj[key] else "empty text"
                        diagnostic = ("WARN", f"{prefix}.{key}.{loc}", "missing translation; using " + default)
                        if diagnostic not in self.problems:
                            self.problems.append(diagnostic)
                        missing.append(key)
            return strings
        strings = copy(item, path)
        if "panel" in item:
            panel = item["panel"]
            strings["panel"] = dict(copy(panel, path + ".panel"), rows=[
                copy(row, f"{path}.panel.rows[{i}]") for i, row in enumerate(panel["rows"])])
        if style.get("template") is not None:
            self.template(style["template"], path + ".template")
            template = self.checked_templates.get(style["template"])
            if template and "/raw.png" in template.virtual and not has_capture:
                if "panel" in item or (style["mode"] != "raw" and rule["id"] != "icon"):
                    self.error(path + ".template", f'{style["template"]} uses /raw.png but this output has no capture')
        profiles = style.get("fonts", {})
        roles = {**profiles.get("default", {}), **profiles.get(loc, {})}
        style = dict(style, logo=self.resolved(style.get("logo")), fonts={
            role: [self.resolved(ref) for ref in roles.get(role, [])] for role in ("headline", "detail")})
        return dict(text=strings, textFallback=bool(missing), style=style, styleMode=style["mode"],
                    template=style["template"], label=rule["label"])

    def resolved(self, ref):
        if ref is None:
            return None
        return Path(os.path.relpath(self.files[ref][1], self.app_root)).as_posix()

    def output_records(self, data, trees):
        paths = {s["id"]: f"screens[{i}]" for i, s in enumerate(data["screens"])}
        base = dict(mode="raw", template=None, fit=None, palette={}, bezel={})
        suffixes = apple_suffixes(data, self.rules)
        for t, s, slot, upload, locale, primary, index in _allocation(data, self.rules, targets(data)):
            store, loc, tid, sid = t["store"], locale["id"], t["id"], s["id"]
            code, tree = locale[store], trees[store]
            if upload == "console":
                folder = tree["storeAssets"] / code / "screenshots" / slot["id"]
            elif store == "play":
                folder = tree["screenshots"] / code / "images" / slot["folder"]
            else:
                folder = tree["screenshots"] / code / slot.get("folder", "")
            output = (folder / _filename(index, t, s, slot)).as_posix()
            if store == "apple" and upload == "fastlane":
                relative = str(Path(output).relative_to(tree["screenshots"]))
                selected = specs.apple_slot_for_file(self.rules, *t["size"], relative, suffixes.get(code))
                if selected is None:
                    self.error(f"{tid}/{sid}", f"Apple upload path cannot distinguish {slot['id']} from another slot")
                elif selected["id"] != slot["id"]:
                    self.error(f"{tid}/{sid}", f"Apple upload path selects {selected['id']} instead of {slot['id']}")
            capture = locale if t.get("captureLocales") == "all" else primary
            flow = self.resolved(flow_for(s, t))
            raw = raw_path(t, s, capture["id"]) if flow else None
            if flow and raw not in self.captures:
                settings = dict.fromkeys(self.capture)
                settings.update(slot.get("capture", {}), appId=self.ids[store])
                settings.update(t.get("capture", {}))
                if settings["orientation"] is None:
                    width, height = t["size"]
                    settings["orientation"] = "landscape" if width > height else "portrait"
                self.captures[raw] = dict(targetId=tid, store=store, screenId=sid, localeId=capture["id"],
                                          deviceLocale=capture[store], flowPath=flow, demoEntry=self.resolved(self.demo),
                                          rawPath=raw, **settings)
            style = _style(dict(base, template=slot.get("defaultTemplate")), data.get("style", {}))
            for item in (t, s):
                style = _style(style, item.get("style", {}))
                if "template" in item:
                    style["template"] = item["template"]
            if locale is primary and "style" in s and style["mode"] != "raw" and slot["framing"] == "forbidden":
                self.error(paths[sid] + ".style.mode", "%s requires raw style" % slot["id"])
            yield dict(kind="screenshot", targetId=tid, screenId=sid, store=store, slotId=slot["id"], index=index,
                       localeId=loc, storeCode=code, captureLocaleId=capture["id"] if flow else None, size=t["size"],
                       rawPath=raw, flowPath=flow, outputPath=output, upload=upload, draft=t.get("draft", False) or s.get("draft", False),
                       **self.render_fields(s, paths[sid], loc, style, slot, has_capture=bool(raw) and "panel" not in s))
        global_style = data.get("style", {})
        graphic_base = _style(dict(base, mode="graphic"),
                              {k: global_style[k] for k in ("palette", "logo", "fonts") if k in global_style})
        for store, entries in data.get("graphics", {}).items():
            rules = {g["id"]: g for g in self.rules["stores"][store]["graphics"]}
            for name, graphic in entries.items():
                rule = rules[name]
                style = _style(graphic_base, {k: graphic[k] for k in ("palette", "logo", "template") if k in graphic})
                for locale in _target_locales(self.locales.values(), {"store": store}):
                    code, loc = locale[store], locale["id"]
                    tree = trees[store]
                    folder = tree["storeAssets"] / code if rule["upload"] == "console" else tree["metadata"] / code
                    if store == "play" and rule["upload"] != "console":
                        folder /= "images"
                    yield dict(kind="graphic", targetId=None, screenId=None, slotId=name, index=None, size=rule["size"],
                               store=store, storeCode=code, localeId=loc, rawPath=None, flowPath=None, draft=graphic.get("draft", False),
                               outputPath=(folder / (rule["file"] + ".png")).as_posix(), upload=rule["upload"],
                               **{"from": self.resolved(graphic.get("from"))},
                               **self.render_fields(graphic, f"graphics.{store}.{name}", loc, style, rule))

    def destinations(self, data):
        trees = _trees(data, self.app_root)
        rows = list(self.output_records(data, trees))
        planned = [(j["rawPath"], j["targetId"] + "/" + j["screenId"]) for j in self.captures.values()]
        for r in rows:
            owner = r["targetId"] + "/" + r["screenId"] if r["targetId"] else f"graphics.{r['store']}.{r['slotId']}"
            planned.append((r["outputPath"], owner))
        stale = self.recorded(trees, [self.app_root / path for path, _ in planned])
        files, children = defaultdict(list), defaultdict(list)
        def register(path, name, owner=None):
            keys = {Path(_fold(path)), Path(_fold(path.resolve()))}
            parents = {parent for key in keys for parent in key.parents}
            if owner:
                overlaps = [claim for k in sorted(keys) for claim in files[k] + children[k]]
                overlaps.extend(claim for p in sorted(parents) for claim in files.get(p, ()))
                for other, label in dict.fromkeys(overlaps):
                    if other and name == label:
                        self.error(owner, f"{other} and {owner} both claim {name}")
                    else:
                        source = other + " output" if other else "input"
                        self.error(owner, f"{name} conflicts with {source} {label}")
            for key in keys:
                files[key].append((owner, name))
            for parent in parents:
                children[parent].append((owner, name))
        for ref, (path, _) in self.files.items():
            register(path, ref)
        for name, owner in planned:
            leaf = self.app_root / name
            try:
                _destination(self.app_root, Path(name))
                for relative in Path(name).parents:
                    parent = self.app_root / relative
                    if (parent.exists() or parent.is_symlink()) and not parent.is_dir():
                        self.error(owner, f"{name} requires directory {relative}")
                if leaf.is_symlink() or (leaf.exists() and not leaf.is_file()):
                    kind = "symlink" if leaf.is_symlink() else "non-regular file"
                    self.error(owner, f"{name} must be a regular file, found {kind}")
                register(leaf, name, owner)
            except (OSError, RuntimeError, ValueError) as exc:
                self.error(owner, f"invalid output {name}: {exc}")
        for path in stale:
            (self.error if self.purpose == "publish" else self.warn)(path, "stale output")
        self.result = dict(manifest=1, app=self.ids,
                           trees={s: {k: p.as_posix() for k, p in tree.items()} for s, tree in trees.items()},
                           captures=list(self.captures.values()), outputs=rows, stale=stale)

    def recorded(self, trees, planned):
        """outputs.json records the app-relative POSIX paths successfully written by compose,
        e.g. {"format": 1, "files": ["fastlane/screenshots/en-US/01_home.png"]}.
        Only existing files beneath current metadata, screenshot and store asset roots count.
        Duplicate entries are harmless. No inventory means no ownership. This reader never deletes.
        """
        stale = set()
        try:
            record = _destination(self.app_root, RECORD)
            if not record.exists():
                return []
            if not record.is_file():
                raise ValueError("expected a regular file")
            self.files[str(RECORD)] = self.app_root / RECORD, record
            with record.open(encoding="utf-8") as stream:
                inventory = json_input.read(stream)
            if not isinstance(inventory, dict):
                raise ValueError("expected an object")
            if type(inventory.get("format")) is not int or inventory["format"] != 1:
                self.error(f"{RECORD.as_posix()}.format", "expected inventory format 1")
                return []
            names = inventory.get("files")
            if not isinstance(names, list):
                self.error(f"{RECORD.as_posix()}.files", "expected an array")
                return []
            current = {_fold(p.parent.resolve() / p.name) for p in planned}
            roots = [self.app_root / p for tree in trees.values() for k, p in tree.items() if k != "fastlaneDir"]
            for i, name in enumerate(names):
                if not isinstance(name, str) or not all(specs.component(p) for p in name.split("/")):
                    self.error(f"{RECORD.as_posix()}.files[{i}]", "expected an app-relative file path")
                    continue
                path = self.app_root / name
                if not any(root in path.parents for root in roots) or _fold(path.parent.resolve() / path.name) in current:
                    continue
                parents = path.resolve().parents
                if self.app_root in parents and any(root.resolve() in parents for root in roots) and path.is_file():
                    stale.add(name)
        except (ValueError, OSError, RuntimeError) as exc:
            self.error(RECORD.as_posix(), str(exc))
        return sorted(stale)

    def plan(self, data):
        if isinstance(data, dict) and isinstance(data.get("style"), dict):
            self.mode = data["style"].get("mode", "raw")
        if self.obj(data, "",
                    dict(format=int, app=self.app, locales=self.locales_field, trees=self.trees,
                    platforms=self.platforms, approved=dict(metadata=bool, screens=bool), style=self.style,
                    targets=[self.target], screens=[self.screen], graphics=dict(apple=self.store_graphics, play=self.store_graphics),
                    console=self.console, notes=dict), ("format", "app", "locales", "targets", "screens")):
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


def _inspect(data, rules, app_root, purpose=None, strict=True, capture_filter=None, repo_root=None):
    if purpose not in (None, "capture", "publish"):
        raise ValueError("expected capture or publish")
    checker = _Checker(rules, app_root, purpose)
    if repo_root is not None:
        checker.repo_root = repo_root
    checker.problems.extend(specs.check(rules))
    if not checker.problems:
        try:
            json_input.validate(data)
            checker.plan(data)
            if purpose == "capture":
                for job in checker.captures.values():
                    if capture_filter is not None and not capture_filter(job):
                        continue
                    flow = job["flowPath"]
                    if not (checker.app_root / flow).is_file():
                        checker.error(f"{job['targetId']}/{job['screenId']}", f"missing input file: {flow}")
            checker.problems.extend(checker.tree_errors)
        except (OSError, ValueError, RuntimeError) as exc:
            checker.error("$", str(exc))
    if strict and any(level == "ERROR" for level, _, _ in checker.problems):
        raise PlanError(checker.problems)
    return checker


def check(data, specs_data, app_root, purpose=None):
    """Check a plan against effective rules and the supplied filesystem."""
    return _inspect(data, specs_data, app_root, purpose, strict=False).problems


def manifest(data, rules, app_root, repo_root=None):
    """Return every planned screenshot and graphic, and stale app-relative paths."""
    return _inspect(data, rules, app_root, repo_root=repo_root).result


def coverage(data, rules, outputs, publish_store=None, *, disk_apple=(), text_locales=()):
    """Expected screenshots, headers and deferrals per store locale for a validated plan."""
    result = {"apple": {}, "play": {}, "inferred": specs.conditions_from_plan(data, rules=rules)}
    suffixes = apple_suffixes(data, rules)
    locales = [_locale(item) for item in data["locales"]]
    for target in targets(data, publish_store):
        if publish_store and target.get("status") == "held":
            continue
        store = target["store"]
        slot = specs.slot(rules, store, target["slot"])
        codes = [loc[store] for loc in _target_locales(locales, target)]
        key = slot["id"]
        count = len(screens_for(data, target["id"]))
        for code in codes:
            entry = result[store].setdefault(code, {})
            if store == "apple" and code in suffixes:
                entry["suffixes"] = suffixes[code]
            counts = entry.setdefault("screenshots", {})
            counts[key] = counts.get(key, 0) + count
    if publish_store == "apple":
        mapped = {loc.get("apple") for loc in locales}
        held = {loc["apple"] for target in targets(data, "apple", state=None)
                if target.get("status") == "held" for loc in _target_locales(locales, target)}
        # Localized text can reuse another locale's screenshots.
        for code in set(text_locales) & (mapped - held):
            result["apple"].setdefault(code, {})
    for row in outputs:
        if row["kind"] == "graphic":
            store = row["store"]
            code = row["storeCode"]
            if publish_store and (publish_store != store or code not in result[store]):
                continue
            entry = result[store].setdefault(code, {})
            field = "headers" if store == "apple" else "graphics"
            entry.setdefault(field, []).append(Path(row["outputPath"]).name)
    if publish_store == "play":
        return result
    for target in targets(data, "apple", "deferred"):
        key = target["slot"]
        for loc in _target_locales(locales, target):
            code = loc["apple"]
            if publish_store and code not in result["apple"]:
                continue
            if code not in result["apple"] and code not in disk_apple:
                continue
            entry = result["apple"].setdefault(code, {})
            if key in entry.get("screenshots", {}):
                # Another target still supplies this display in the same locale.
                entry.setdefault("deferredTargets", {})[target["id"]] = target["reason"]
            else:
                reasons = entry.setdefault("deferredScreenshots", {})
                if key in reasons:
                    reasons[key] += " / " + target["reason"]
                else:
                    reasons[key] = target["reason"]
    return result


def outputs(data, rules, app_root):
    """Four-column TSV view of the validated manifest records."""
    return _tsv_rows(manifest(data, rules, app_root)["outputs"])


def input_files(data, rules, app_root):
    """Return resolved input paths for scanning, including the plan and optional override."""
    return sorted({resolved for _, resolved in _inspect(data, rules, app_root).files.values()})


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


def read_listing(root):
    from secret_scan import secret_content

    path = _destination(root, LISTING)
    raw = path.read_bytes()
    if secret_content(path, raw):
        raise ValueError("POTENTIAL SECRET in .listing-kit/listing.json")
    return json_input.read(io.StringIO(raw.decode("utf-8")))


def _read(app_root, purpose=None, capture_filter=None):
    try:
        root = Path(app_root).resolve()
        if not (root / LISTING).exists():
            layout.project(root)
        data = read_listing(root)
        rules = specs.load(root)
    except FileNotFoundError:
        raise
    except (OSError, ValueError, RuntimeError, specs.SpecsError) as exc:
        raise PlanError([("ERROR", str(LISTING), str(exc))]) from exc
    return data, _inspect(data, rules, root, purpose, capture_filter=capture_filter)


def load(app_root):
    """Return the validated plan. Raise FileNotFoundError or PlanError on failure."""
    return _read(app_root)[0]


def listing_trees(app_root):
    """Resolve app-relative input directories for a planned or manual listing."""
    root = Path(app_root).resolve()
    try:
        data = read_listing(root)
    except FileNotFoundError:
        data = {}
    except ValueError as exc:
        raise PlanError([("ERROR", str(LISTING), str(exc))]) from exc
    if not isinstance(data, dict):
        raise PlanError([("ERROR", str(LISTING), "expected an object")])
    if "trees" in data:
        checker = _Checker({}, root, None)
        checker.visit(data["trees"], "trees", checker.trees)
        if checker.problems or checker.tree_errors:
            raise PlanError(checker.problems + checker.tree_errors)
    return _trees(data, root)


def has_listing_directory(root, trees):
    """Check the actual listing destinations, including ones beneath .listing-kit."""
    return any((root / path).is_dir() for tree in trees.values() for path in tree.values())


def listing_roots(root, trees=None):
    """Minimal non-overlapping roots for private-file filtering and secret scans."""
    roots = {Path(".listing-kit")}
    for tree in (listing_trees(root) if trees is None else trees).values():
        roots.update((tree["fastlaneDir"], tree["metadata"], tree["screenshots"], tree["storeAssets"].parent))
    directories = sorted(p for p in roots if roots.isdisjoint(p.parents))
    base = Path(root).resolve()
    for directory in directories:
        _inside(base, base / directory)
    return directories


def compose_inputs(app_root):
    """Keep the validated templates and authorised file roots with their manifest."""
    _, checker = _read(app_root)
    return checker.result, checker.checked_templates, checker.input_roots


def load_manifest(app_root, purpose=None, capture_filter=None):
    """Read the checked manifest. capture_filter limits which flow files must exist."""
    return _read(app_root, purpose, capture_filter)[1].result


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
        print(json.dumps(checker.result))
    else:
        rows = checker.problems if args.command == "check" else _tsv_rows(checker.result["outputs"])
        for row in rows:
            _print(_line(row), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
