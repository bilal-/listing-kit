#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SPECS="$SCRIPTS/lib/specs.py"
py() { python3 - "$@"; }

it "the bundled rules file is valid JSON with a verification date and sources"
assert_file "$SKILL_DIR/specs/stores.json"
if json_valid "$SKILL_DIR/specs/stores.json"; then pass "valid JSON"; else fail "invalid stores.json"; fi
assert_contains "$(python3 "$SPECS" verified)" "20"

it "every size in the old Apple size table maps to a slot with the same label"
OUT="$(cd "$SCRIPTS/lib" && py <<'PY'
import specs, os
d = specs.load()
bad = []
for line in open("apple-screenshot-sizes.tsv", encoding="utf-8"):
    if not line.strip() or line.startswith("#"): continue
    dims, label = line.rstrip("\n").split("\t")
    w, h = (int(x) for x in dims.split("x"))
    s = specs.apple_slot_for_size(d, w, h)
    ok = s and (s["label"] == label or label in s.get("legacyLabels", []))
    if not ok: bad.append("%s %s -> %s" % (dims, label, s and s["label"]))
print("BAD: " + "; ".join(bad) if bad else "ALL MAPPED")
PY
)"
assert_eq "ALL MAPPED" "$OUT"

it "Duo outer and inner are separate slots, and sizes work in either orientation"
assert_eq "iphone-duo-outer" "$(python3 "$SPECS" slot apple 1398 2034)"
assert_eq "iphone-duo-inner" "$(python3 "$SPECS" slot apple 2853 2007)"
assert_eq "iphone-di-medium" "$(python3 "$SPECS" slot apple 2622 1206)"
assert_eq "-" "$(python3 "$SPECS" slot apple 1000 1000)"

it "watch and legacy sizes are known, so existing trees with them are not rejected"
assert_eq "watch" "$(python3 "$SPECS" slot apple 410 502)"
assert_eq "ipad-9-7" "$(python3 "$SPECS" slot apple 1536 2048)"
assert_eq "ipad-11" "$(python3 "$SPECS" slot apple 1512 2316)"

it "slot ids are unique and every slot has the fields consumers read"
OUT="$(cd "$SCRIPTS/lib" && py <<'PY'
import specs
d = specs.load(); bad = []
for store in d["stores"]:
    ids = [s["id"] for s in specs.slots(d, store)]
    if len(ids) != len(set(ids)): bad.append(store + " duplicate ids")
    for s in specs.slots(d, store):
        for k in ("label", "min", "max", "required", "framing", "lifecycle", "upload"):
            if k not in s: bad.append("%s/%s lacks %s" % (store, s["id"], k))
        if s["required"].get("rule") == "if" and s["required"]["condition"] not in d["conditions"]:
            bad.append("%s/%s uses an undeclared condition" % (store, s["id"]))
    for f in specs.fields(d, store):
        if f["required"].get("rule") == "if" and f["required"]["condition"] not in d["conditions"]:
            bad.append("%s/%s uses an undeclared condition" % (store, f["stem"]))
print("; ".join(bad) or "OK")
PY
)"
assert_eq "OK" "$OUT"

it "a dated requirement warns before its date, fails from it, and respects its exception"
OUT="$(cd "$SCRIPTS/lib" && py <<'PY'
import specs, datetime
d = specs.load(); r = specs.slot(d, "apple", "iphone-duo-outer")["required"]
D = datetime.date
c = {"supportsIphone": True, "iosSdkBelow:27.1": False}
print(specs.requirement(r, c, D(2026, 11, 26))[0],
      specs.requirement(r, c, D(2027, 3, 31))[0],
      specs.requirement(r, c, D(2027, 4, 1))[0],
      specs.requirement(r, dict(c, **{"iosSdkBelow:27.1": True}), D(2027, 4, 1))[0],
      specs.requirement(r, {"supportsIphone": True}, D(2027, 4, 1))[0],
      specs.requirement(r, {"supportsIphone": False}, D(2027, 4, 1))[0])
PY
)"
assert_eq "optional upcoming required optional upcoming optional" "$OUT"

it "an override in the app repo adds a slot and changes a limit without touching the kit"
T="$(mktemp -d)"; [ -d "$T" ] || { fail "mktemp failed"; summary; exit 1; }
mkdir -p "$T/.listing-kit"
cat > "$T/.listing-kit/specs.override.json" <<'JSON'
{"stores": {"apple": {"screenshots": {"slots": [
  {"id": "iphone-made-up", "label": "iPhone Made Up", "sizes": [[1111, 2222]], "min": 1, "max": 10,
   "required": {"rule": "never"}, "framing": "allowed", "lifecycle": "active", "upload": "console"}]},
  "fields": [{"stem": "subtitle", "limit": 31}]}}}
JSON
assert_eq "iphone-made-up" "$(python3 "$SPECS" slot apple 1111 2222 "$T")"
assert_eq "-" "$(python3 "$SPECS" slot apple 1111 2222)" "the kit's own rules are unchanged"
OUT="$(cd "$SCRIPTS/lib" && python3 -c "
import specs,sys
d=specs.load(sys.argv[1]); f=[x for x in specs.fields(d,'apple') if x['stem']=='subtitle'][0]
print(f['limit'], f['label'], bool(d['_override']), len(specs.slots(d,'apple'))>18)" "$T")"
assert_eq "31 Subtitle True True" "$OUT"

it "a malformed override is an error, not silently ignored"
printf '%s' '{"stores": ' > "$T/.listing-kit/specs.override.json"
python3 "$SPECS" slot apple 1206 2622 "$T" >/dev/null 2>&1; assert_eq 1 "$?" "exit 1"
rm -rf "$T"

it "rules older than 120 days are reported as stale"
OUT="$(cd "$SCRIPTS/lib" && python3 -c "
import specs,datetime
d=specs.load(); v=specs.parse_date(d['verified'])
print(specs.staleness(d, v+datetime.timedelta(days=120))[2], specs.staleness(d, v+datetime.timedelta(days=121))[2])")"
assert_eq "False True" "$OUT"

it "effective rules and conditional requirements reject invalid overrides"
if PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$SCRIPTS/lib" python3 "$ROOT/tests/unit/specs_review.py"; then
  pass
else
  fail "store rule regressions"
fi

it "legacy sizes are directional: Apple's without-status-bar landscape sizes are not swaps"
assert_eq "iphone-home-4" "$(python3 "$SPECS" slot apple 1136 600)"
assert_eq "-" "$(python3 "$SPECS" slot apple 600 1136)" "600x1136 is not an Apple size"
assert_eq "ipad-9-7" "$(python3 "$SPECS" slot apple 2048 1496)"
assert_eq "-" "$(python3 "$SPECS" slot apple 1496 2048)"

it "Apple locale codes are the ones fastlane deliver accepts"
OUT="$(cd "$SCRIPTS/lib" && python3 -c "
import specs; l=specs.load()['stores']['apple']['locales']
print('ta-IN' in l, 'ta' in l, 'zh-Hans' in l, 'en-US' in l, len(l))")"
assert_eq "True False True True 50" "$OUT"

it "a shared size is resolved by path the way deliver does it"
OUT="$(cd "$SCRIPTS/lib" && python3 -c "
import specs; d=specs.load(); f=specs.apple_slot_for_file
print(f(d,3840,2160,'screenshots/en-US/01_home.png')['id'], f(d,3840,2160,'screenshots/en-US/01_vision.png')['id'], f(d,2064,2752,'x.png')['id'])")"
assert_eq "apple-tv vision-pro ipad-13" "$OUT"

summary
