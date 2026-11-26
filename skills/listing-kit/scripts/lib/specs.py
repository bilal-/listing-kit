#!/usr/bin/env python3
"""Store rules as data: the one place sizes, limits, required rules and dates live.

Reads skills/listing-kit/specs/stores.json and, when an app root is given, merges
<app-root>/.listing-kit/specs.override.json over it. Standard library only.

CLI:  specs.py verified [<app-root>]            -> the date the rules were checked
      specs.py slot <store> <width> <height> [<app-root>]   -> slot id, or "-"
      specs.py slots <store> [<app-root>]       -> id<TAB>label<TAB>lifecycle per slot
"""
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLED = os.path.normpath(os.path.join(HERE, "..", "..", "specs", "stores.json"))
OVERRIDE = os.path.join(".listing-kit", "specs.override.json")
STALE_DAYS = 120
WARN_DAYS = 90


class SpecsError(Exception):
    pass


def _merge_list(base, extra, where):
    """Merge lists of objects by "id" (or "stem"); an override entry replaces or adds."""
    key = "id" if any("id" in x for x in base + extra if isinstance(x, dict)) else "stem"
    out = {x[key]: x for x in base}
    for x in extra:
        if not isinstance(x, dict) or key not in x:
            raise SpecsError("override %s: every entry needs %r" % (where, key))
        out[x[key]] = dict(out.get(x[key], {}), **x)
    return list(out.values())


def _merge(base, extra, where="override"):
    out = dict(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v, where + "." + k)
        elif isinstance(v, list) and isinstance(out.get(k), list) and v and isinstance(v[0], dict):
            out[k] = _merge_list(out[k], v, where + "." + k)
        else:
            out[k] = v
    return out


def load(app_root=None, path=None):
    """The rules, with the app's override merged in. Sets "_override" when one is active."""
    try:
        with open(path or BUNDLED, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise SpecsError("cannot read store rules: %s" % e)
    data["_override"] = None
    if app_root:
        opath = os.path.join(app_root, OVERRIDE)
        if os.path.isfile(opath):
            try:
                with open(opath, encoding="utf-8") as f:
                    extra = json.load(f)
            except (OSError, ValueError) as e:
                raise SpecsError("cannot read %s: %s" % (opath, e))
            if not isinstance(extra, dict):
                raise SpecsError("%s must be a JSON object" % opath)
            data = _merge(data, extra)
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
    """Every Apple slot accepting this size in either orientation (2048x2732 has two)."""
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


def slot_by_label(data, store, label):
    """Slots matching a console label, including labels used by older plan files."""
    return [s for s in slots(data, store) if s["label"] == label or label in s.get("legacyLabels", [])]


def fields(data, store, scope=None):
    return [f for f in data["stores"][store]["fields"] if scope is None or f.get("scope") == scope]


def parse_date(text):
    return datetime.date(*(int(x) for x in text.split("-")))


def requirement(rule, conditions, as_of=None):
    """(level, reason) for a "required" rule: level is "required", "upcoming" or "optional".

    conditions maps a condition name to True, False or None (unknown). An unknown
    condition never produces "required": it produces "upcoming" with the reason.
    """
    as_of = as_of or datetime.date.today()
    kind = (rule or {}).get("rule", "never")
    if kind == "never":
        return "optional", ""
    if kind == "if":
        name = rule["condition"]
        value = conditions.get(name)
        if value is False:
            return "optional", ""
        if value is None:
            return "upcoming", "cannot tell whether %r applies; say so with a flag" % name
    unless = rule.get("unless")
    if unless:
        value = conditions.get(unless)
        if value is True:
            return "optional", ""
        if value is None and "from" in rule:
            return "upcoming", "required from %s unless %s; that could not be determined" % (rule["from"], unless)
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


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] == ["verified"]:
            print(load(a[1] if len(a) > 1 else None)["verified"])
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
