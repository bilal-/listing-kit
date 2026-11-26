#!/usr/bin/env python3
"""Store rules for the listing plan checker and its consumers.

Reads skills/listing-kit/specs/stores.json and, when an app root is given, merges
<app-root>/.listing-kit/specs.override.json over it. Standard library only.

CLI:  specs.py verified [<app-root>]            -> the date the rules were checked
      specs.py graphic-size <store> <id> [<app-root>]       -> WIDTHxHEIGHT
      specs.py slot <store> <width> <height> [<app-root>]   -> slot id, or "-"
      specs.py slots <store> [<app-root>]       -> id<TAB>label<TAB>lifecycle per slot
"""
import datetime
from fractions import Fraction
import os
from pathlib import Path
import re
import sys

if __package__:
    from . import json_input
else:
    if __name__ == "__main__":
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import json_input

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLED = os.path.normpath(os.path.join(HERE, "..", "..", "specs", "stores.json"))
OVERRIDE = os.path.join(".listing-kit", "specs.override.json")
STALE_DAYS = 120
WARN_DAYS = 90


class SpecsError(Exception):
    pass


ID = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
_RESERVED = re.compile(r"(con|prn|aux|nul|com[1-9]|lpt[1-9])", re.I)


def component(value):
    """One portable path component, including fastlane's mixed-case folders."""
    return (isinstance(value, str) and bool(value.strip()) and value.isprintable()
            and not re.search(r'[<>:"/\\|?*]', value) and not value.endswith((" ", "."))
            and len(value.encode("utf-8")) <= 255 and not _RESERVED.fullmatch(value.split(".")[0]))


def identifier(value):
    return isinstance(value, str) and bool(ID.fullmatch(value)) and component(value)


def _string(v):
    return isinstance(v, str) and bool(v.strip())


def _count(v):
    return type(v) is int and v >= 0


def _positive(v):
    return _count(v) and v > 0


def _size(v):
    return isinstance(v, list) and len(v) == 2 and all(_positive(n) for n in v)


def _list_of(test):
    return lambda v: isinstance(v, list) and all(test(x) for x in v)


def _range(v):
    return (isinstance(v, dict) and bool(v) and set(v) <= {"min", "max"} and all(_positive(n) for n in v.values())
            and v.get("min", 1) <= v.get("max", float("inf")))


def _ratio(v):
    return isinstance(v, str) and bool(re.fullmatch(r"[1-9][0-9]{0,8}:[1-9][0-9]{0,8}", v))


def _date(v):
    try:
        return (_string(v) and bool(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", v))
                and bool(datetime.date.fromisoformat(v)))
    except ValueError:
        return False


def _required(v):
    return (isinstance(v, dict) and set(v) <= {"rule", "condition", "unless", "note", "from"}
            and v.get("rule") in ("always", "never", "if")
            and (v["rule"] != "if" or _string(v.get("condition")))
            and all(_string(v[k]) for k in ("condition", "unless", "note") if k in v)
            and ("from" not in v or _date(v["from"])))


def _capture(v):
    return (isinstance(v, dict) and set(v) <= {"deviceType", "display", "nativeSize"}
            and all(_string(v[k]) for k in ("deviceType", "display") if k in v)
            and ("nativeSize" not in v or _size(v["nativeSize"])))


def _promotion(v):
    return (isinstance(v, dict) and _positive(v.get("count")) and _positive(v.get("shortSideMin"))
            and _list_of(_ratio)(v.get("ratios")) and ("note" not in v or _string(v["note"]))
            and ("longSideMax" not in v or _positive(v["longSideMax"]))
            and set(v) <= {"count", "shortSideMin", "longSideMax", "ratios", "note"})


_UPLOAD = ("fastlane", "console")
_SLOT_FIELDS = {
    "id": identifier, "folder": lambda v: v is None or component(v), "suffix": identifier,
    "label": _string, "legacyLabels": _list_of(_string), "required": _required,
    "framing": ("allowed", "forbidden").__contains__, "upload": _UPLOAD.__contains__,
    "lifecycle": ("active", "console-only", "legacy").__contains__, "note": _string,
    "min": _count, "max": _positive, "side": _range, "sizes": _list_of(_size),
    "ratio": _ratio, "ratios": _list_of(_ratio), "minPerSize": _positive, "minSize": _size, "defaultSize": _size,
    "maxRatio": lambda v: type(v) in (float, int) and v >= 1,
    "orientation": ("fixed", "either").__contains__, "capture": _capture,
    "formats": _list_of(_string), "alpha": lambda v: type(v) is bool, "bitDepth": _positive,
    "maxBytes": _positive, "recommendedMin": _count, "promotion": _promotion,
    "defaultTemplate": _string, "taglineMaxShare": lambda v: type(v) in (float, int) and 0 <= v <= 1,
}


def _fields_ok(value, path, required, fields, problems):
    if not isinstance(value, dict):
        problems.append(("ERROR", path, "expected an object"))
        return False
    for key in sorted(value.keys() - fields.keys()):
        problems.append(("ERROR", path + "." + key, "unknown rule field"))
    for key in required:
        if key not in value:
            problems.append(("ERROR", path + "." + key, "missing required rule"))
    for key, test in fields.items():
        if key in value and not test(value[key]):
            problems.append(("ERROR", path + "." + key, "invalid rule value"))
    return True


def _entries(rows, path, key, required, fields, problems):
    seen = set()
    entries = []
    for i, row in enumerate(rows):
        entry = "%s[%d]" % (path, i)
        if _fields_ok(row, entry, required, fields, problems):
            name = row.get(key)
            if isinstance(name, str):
                if name.casefold() in seen:
                    problems.append(("ERROR", entry + "." + key, "duplicate rule identifier"))
                seen.add(name.casefold())
            entries.append((row, entry))
    return entries


def check(data):
    """Return problems with the effective store rules before any consumer uses them."""
    try:
        json_input.validate(data)
    except ValueError as exc:
        return [("ERROR", "$", str(exc))]
    problems = []
    strings = _list_of(_string)
    def string_map(value):
        return isinstance(value, dict) and all(_string(v) for v in value.values())

    if not _fields_ok(data, "$", ("schema", "verified", "stores"), {
        "schema": lambda v: type(v) is int and v == 1, "verified": _date,
        "stores": lambda v: isinstance(v, dict), "sources": string_map, "conditions": string_map,
        "appleCategories": strings, "unverified": strings, "_override": lambda v: v is None or _string(v),
    }, problems):
        return problems
    stores = data.get("stores")
    if not isinstance(stores, dict):
        return problems
    for name in stores.keys() - {"apple", "play"}:
        problems.append(("ERROR", "stores." + name, "unknown store"))
    for store in ("apple", "play"):
        path = "stores." + store
        st = stores.get(store)
        array = lambda v: isinstance(v, list)
        obj = lambda v: isinstance(v, dict)
        required_sections = ("screenshots", "fields", "graphics") + (("locales",) if store == "apple" else ())
        if not _fields_ok(st, path, required_sections, {
            "label": _string, "screenshots": obj, "fields": array, "graphics": array,
            "nonLocaleFolders": _list_of(component), "locales": strings,
            "changelogs": obj, "taglineDiscouraged": strings,
        }, problems):
            continue
        if "changelogs" in st:
            _fields_ok(st["changelogs"], path + ".changelogs", ("limit", "unit", "names"),
                       {"limit": _count, "unit": _string, "names": _string}, problems)
        if array(st.get("fields")):
            _entries(st["fields"], path + ".fields", "stem", ("stem", "label", "scope", "unit", "required"), {
                "stem": component, "label": _string, "unit": _string, "scope": _string, "min": _count,
                "limit": _count, "required": _required, "note": _string, "values": _string,
            }, problems)
        if array(st.get("graphics")):
            _entries(st["graphics"], path + ".graphics", "id", ("id", "label", "size", "formats", "file", "upload", "required"), {
                "id": component, "file": component, "size": _size, "label": _string, "formats": strings, "grayscaleJpeg": lambda v: type(v) is bool,
                "required": _required, "upload": _UPLOAD.__contains__, "bitDepth": _positive,
                "maxBytes": _positive, "note": _string, "alpha": lambda v: type(v) is bool or v == "required",
            }, problems)
        path += ".screenshots"
        shots = st.get("screenshots")
        if not _fields_ok(shots, path, ("slots", "minTotal"), {
            "slots": array, "minTotal": _count, "formats": strings, "note": _string,
            "alpha": lambda v: type(v) is bool,
        }, problems) or not array(shots.get("slots")):
            continue
        required = ("id", "label", "min", "max", "required", "framing", "lifecycle", "upload")
        for row, entry in _entries(shots["slots"], path + ".slots", "id", required, _SLOT_FIELDS, problems):
            if _count(row.get("min")) and _count(row.get("max")) and row["min"] > row["max"]:
                problems.append(("ERROR", entry + ".min", "minimum exceeds maximum"))
            if store == "apple" and not row.get("sizes"):
                problems.append(("ERROR", entry + ".sizes", "expected accepted sizes"))
            if store == "apple" and "folder" in row and row["folder"] is None:
                problems.append(("ERROR", entry + ".folder", "expected a folder name"))
            if "ratio" in row and "ratios" in row:
                problems.append(("ERROR", entry + ".ratios", "ratio and ratios cannot both be set"))
            if row.get("sizes") == []:
                problems.append(("ERROR", entry + ".sizes", "expected at least one size"))
            if "minPerSize" in row and not row.get("sizes"):
                problems.append(("ERROR", entry + ".minPerSize", "requires exact sizes"))
            if store == "play" and row.get("upload") == "fastlane" and not row.get("folder"):
                problems.append(("ERROR", entry + ".folder", "fastlane requires a folder"))
        conditions = data.get("conditions", {})
        if isinstance(conditions, dict):
            for section, rows in (("fields", st.get("fields")), ("graphics", st.get("graphics")),
                                  ("screenshots.slots", shots["slots"])):
                for i, row in enumerate(rows if isinstance(rows, list) else []):
                    rule = row.get("required") if isinstance(row, dict) else None
                    if isinstance(rule, dict):
                        for key in ("condition", "unless"):
                            name = rule.get(key)
                            if isinstance(name, str) and name not in conditions:
                                problems.append(("ERROR", f"stores.{store}.{section}[{i}].required.{key}",
                                                 f"unknown condition {name!r}"))
    return problems


def _ensure_valid(data):
    problems = check(data)
    if problems:
        raise SpecsError("\n".join("%s: %s" % (path, msg) for _, path, msg in problems))


def _merge_list(base, extra, where):
    """Merge lists of objects by "id" (or "stem"); an override entry replaces or adds."""
    key = "stem" if where.endswith(".fields") else "id"
    out = {x[key]: x for x in base}
    seen = set()
    for i, x in enumerate(extra):
        entry = "%s[%d]" % (where, i)
        if not isinstance(x, dict) or not isinstance(x.get(key), str):
            raise SpecsError("%s.%s: expected a string" % (entry, key))
        name = x[key]
        if name in seen:
            raise SpecsError("%s.%s: duplicate %r" % (entry, key, name))
        seen.add(name)
        out[name] = _merge(out.get(name, {}), x, entry)
    return list(out.values())


def _merge(base, extra, where="override"):
    out = dict(base)
    for k, v in extra.items():
        if v is None:
            out.pop(k, None)
        elif k == "required" and isinstance(v, dict):
            out[k] = _merge({}, v)
        elif isinstance(v, dict):
            out[k] = _merge(out[k] if isinstance(out.get(k), dict) else {}, v, where + "." + k)
        elif isinstance(v, list) and isinstance(out.get(k), list) and k in ("slots", "fields", "graphics"):
            out[k] = _merge_list(out[k], v, where + "." + k)
        else:
            out[k] = v
    return out


def load(app_root=None, path=None):
    """The rules, with the app's override merged in. Sets "_override" when one is active."""
    try:
        with open(path or BUNDLED, encoding="utf-8") as f:
            data = json_input.read(f)
    except (OSError, ValueError) as e:
        raise SpecsError("cannot read store rules: %s" % e)
    _ensure_valid(data)
    data["_override"] = None
    if app_root:
        opath = os.path.join(app_root, OVERRIDE)
        if os.path.isfile(opath):
            try:
                with open(opath, encoding="utf-8") as f:
                    extra = json_input.read(f)
            except (OSError, ValueError) as e:
                raise SpecsError("cannot read %s: %s" % (opath, e))
            if not isinstance(extra, dict):
                raise SpecsError("%s must be a JSON object" % opath)
            data = _merge(data, extra)
            try:
                _ensure_valid(data)
            except SpecsError as e:
                raise SpecsError(f"{opath}: {e}") from e
            data["_override"] = opath
    return data


def slots(data, store):
    return data["stores"][store]["screenshots"]["slots"]


def slot(data, store, slot_id):
    for s in slots(data, store):
        if s["id"] == slot_id:
            return s
    return None


def _norm(w, h):
    return (min(w, h), max(w, h))


def apple_slots_for_size(data, w, h):
    """Every Apple slot accepting the dimensions in the supplied orientation."""
    want = _norm(w, h)
    out = []
    for s in slots(data, "apple"):
        for sw, sh in s.get("sizes", []):
            if (_norm(sw, sh) == want) if s.get("orientation") != "fixed" else ((sw, sh) == (w, h)):
                out.append(s)
                break
    return out


def apple_slot_for_size(data, w, h):
    """The slot a size belongs to; the first listed wins when several accept it."""
    found = apple_slots_for_size(data, w, h)
    return found[0] if found else None


def apple_slot_for_file(data, w, h, path=""):
    """The slot for a screenshot file, resolving shared sizes the way fastlane deliver does
    (deliver/lib/deliver/app_screenshot.rb, 2.242.0):     3840x2160 uses the vision marker outside an appleTV directory.
    An explicit 12.9-inch suffix selects the legacy slot for shared iPad sizes.
    """
    found = apple_slots_for_size(data, w, h)
    if len(found) < 2:
        return found[0] if found else None
    low = path.lower()
    ids = {s["id"]: s for s in found}
    if "vision-pro" in ids and "vision" in low and "appletv" not in low.split("/")[:-1]:
        return ids["vision-pro"]
    if "ipad-12-9" in ids:
        stem = os.path.splitext(os.path.basename(low))[0]
        # Existing handoff files use the dotted display size. Plan suffixes are identifiers.
        suffix = ids["ipad-12-9"].get("suffix", "ipad-12-9")
        if re.search(r"(?:^|[-_ ])(?:" + re.escape(suffix) + r"|ipad-12\.9)(?:_framed)?$", stem):
            return ids["ipad-12-9"]
    return found[0]


def ratio_matches(w, h, ratios):
    return any(w * int(r.split(":")[1]) == h * int(r.split(":")[0]) for r in ratios)


def play_size_errors(slot, w, h):
    """Dimension checks shared by planned and captured screenshots."""
    side = slot.get("side", {})
    if min(w, h) < side.get("min", 0) or max(w, h) > side.get("max", float("inf")):
        yield "side outside {}–{} ({}x{})".format(side.get("min", 0), side.get("max", "∞"), w, h)
    if "minSize" in slot and any(n < low for n, low in zip((w, h), slot["minSize"])):
        yield "below {}x{} minimum".format(*slot["minSize"])
    if "sizes" in slot and [w, h] not in slot["sizes"]:
        yield "size {}x{} is outside the accepted sizes".format(w, h)
    if "maxRatio" in slot and max(w, h) > min(w, h) * Fraction(str(slot["maxRatio"])):
        yield "aspect {}/{} exceeds {}:1".format(max(w, h), min(w, h), slot["maxRatio"])
    ratios = [slot["ratio"]] if "ratio" in slot else slot.get("ratios", [])
    if ratios and not ratio_matches(w, h, ratios):
        yield "aspect must be " + " or ".join(ratios)


def slot_by_label(data, store, label):
    """Slots matching a console label, including labels used by older plan files."""
    return [s for s in slots(data, store) if s["label"] == label or label in s.get("legacyLabels", [])]


def fields(data, store, scope=None):
    return [f for f in data["stores"][store]["fields"] if scope is None or f.get("scope") == scope]


def parse_date(text):
    return datetime.date(*(int(x) for x in text.split("-")))


def conditions_from_plan(plan, detected=None, rules=None):
    """Infer capabilities from selected slots. Detection and explicit flags refine those facts."""
    rules = load() if rules is None else rules
    facts = {}
    for target in plan.get("targets", []):
        if target["state"] == "retired":
            continue
        store, name = target["store"], target["slot"]
        selected = slot(rules, store, name)
        if selected and selected["required"].get("rule") == "if":
            facts[selected["required"]["condition"]] = True
        if store == "apple" and name.startswith("iphone-"):
            facts["supportsIphone"] = True
        if store == "apple" and name.startswith("ipad-"):
            facts["supportsIpad"] = True
    facts.update(detected or {})
    for name, flag in plan.get("platforms", {}).items():
        if name not in rules.get("conditions", {}):
            raise SpecsError(f"unknown condition {name!r}")
        if type(flag) is not bool:
            raise SpecsError(f"expected a boolean for {name!r}")
        facts[name] = flag
    return facts


def requirement(rule, conditions, as_of=None, used=None):
    """(level, reason) for a "required" rule: level is "required", "upcoming" or "optional".

    conditions maps a condition name to True, False or None (unknown). An unknown
    condition never produces "required": it produces "upcoming" with the reason.
    """
    as_of = as_of or datetime.date.today()
    if rule is None or rule == {}:
        return "optional", ""
    if not _required(rule):
        raise SpecsError("invalid requirement: expected a known rule, condition names and a valid date")
    if not isinstance(conditions, dict):
        raise SpecsError("expected a mapping of condition names to flags")
    if "from" in rule and (parse_date(rule["from"]) - as_of).days > WARN_DAYS:
        return "optional", ""
    unknown = None
    kind = rule["rule"]
    if kind == "never":
        return "optional", ""
    if kind == "if":
        name = rule["condition"]
        if used is not None:
            used.add(name)
        value = conditions.get(name)
        if value is False:
            return "optional", ""
        if value is None:
            unknown = "cannot tell whether %r applies" % name
    unless = rule.get("unless")
    if unless:
        if used is not None:
            used.add(unless)
        value = conditions.get(unless)
        if value is True:
            return "optional", ""
        if value is None:
            unknown = unknown or "cannot tell whether exemption %r applies" % unless
    if unknown:
        if "from" in rule:
            unknown += " (requirement from " + rule["from"] + ")"
            if unless and unless.startswith("iosSdkBelow:") and conditions.get(unless) is None:
                unknown += "; pass --ios-sdk X.Y"
        return "upcoming", unknown
    if "from" in rule:
        start = parse_date(rule["from"])
        if as_of < start:
            days = (start - as_of).days
            return ("upcoming", "required from %s (%d days)" % (rule["from"], days)) if days <= WARN_DAYS else ("optional", "")
        return "required", "required since %s" % rule["from"]
    return "required", ""


def staleness(data, as_of=None):
    """(verified date text, age in days, True when older than STALE_DAYS)."""
    as_of = as_of or datetime.date.today()
    age = (as_of - parse_date(data["verified"])).days
    return data["verified"], age, age > STALE_DAYS


def image_output(rule, output):
    """ImageMagick encoder, channel depth and alpha policy for a generated asset."""
    formats = rule.get("formats")
    if not formats:
        raise SpecsError("an output format is required to generate an image")
    extension = Path(output).suffix.lower().lstrip(".")
    extension = "jpeg" if extension == "jpg" else extension
    fmt = extension if extension in formats else formats[0]
    depth = rule.get("bitDepth", 8)
    alpha = bool(rule.get("alpha"))
    if fmt == "png" and depth in (8, 16):
        encoder = "PNG" + str(depth * (4 if alpha else 3))
    elif fmt == "jpeg" and rule.get("alpha") != "required":
        encoder = "JPEG"
        alpha = False
    else:
        raise SpecsError(f"unsupported output format, depth or alpha for {fmt}")
    return encoder, str(depth), "on" if alpha else "off"


def promotion_crop(width, height, ratios):
    # Retain the largest rectangle matching one of the accepted orientations.
    candidates = []
    for ratio in ratios:
        reduced = Fraction(*map(int, ratio.split(":")))
        x, y = reduced.numerator, reduced.denominator
        scale = min(width // x, height // y)
        if scale:
            candidates.append((scale * x, scale * y))
    if not candidates:
        raise SpecsError("capture is too small for the promotion ratios")
    return max(candidates, key=lambda size: size[0] * size[1])


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] == ["verified"]:
            print(load(a[1] if len(a) > 1 else None)["verified"])
        elif a[:1] == ["play-crop"] and len(a) == 4:
            phone = slot(load("."), "play", "phone")
            w, h = promotion_crop(int(a[1]), int(a[2]), phone["promotion"]["ratios"])
            print("\t".join((f"{w}x{h}", *image_output(phone, a[3]))))
        elif a[:1] == ["feature-graphic"] and len(a) == 2:
            graphic = next(g for g in load(".")["stores"]["play"]["graphics"] if g["id"] == "featureGraphic")
            print("\t".join(("{}x{}".format(*graphic["size"]), *image_output(graphic, a[1]))))
        elif a[:1] == ["graphic-size"] and len(a) in (3, 4):
            store = load(a[3] if len(a) == 4 else None)["stores"].get(a[1], {})
            graphic = next((g for g in store.get("graphics", []) if g["id"] == a[2]), None)
            if graphic is None:
                raise SpecsError("unknown graphic: " + a[2])
            print("{}x{}".format(*graphic["size"]))
        elif a[:1] == ["slot"] and len(a) >= 4:
            d = load(a[4] if len(a) > 4 else None)
            s = apple_slot_for_size(d, int(a[2]), int(a[3])) if a[1] == "apple" else None
            print(s["id"] if s else "-")
        elif a[:1] == ["slots"] and len(a) >= 2:
            for s in slots(load(a[2] if len(a) > 2 else None), a[1]):
                print("\t".join((s["id"], s["label"], s["lifecycle"])))
        else:
            sys.stderr.write(__doc__)
            sys.exit(2)
    except SpecsError as e:
        sys.stderr.write("specs: %s\n" % e)
        sys.exit(1)
