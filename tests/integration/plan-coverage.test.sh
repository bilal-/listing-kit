#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir app
lk="$SKILL_DIR/bin/listing-kit"
cp -R "$ROOT/examples/expo-recipe-box/fastlane" "$ROOT/examples/expo-recipe-box/app.json" "$app/"
mkdir -p "$app/.listing-kit"
git init -q "$app"
printf '.listing-kit/local.json\n' > "$app/.gitignore"
printf '{}\n' > "$app/.listing-kit/local.json" # Exercise the filtered review view.
plan="$app/.listing-kit/listing.json"
python3 - "$plan" <<'PY'
import json, sys
from pathlib import Path
phone = dict(id="iphone", store="apple", slot="iphone-di-medium", size=[1206,2622], state="active")
duo = dict(phone, id="duo", slot="iphone-duo-outer", size=[1398,2034], state="deferred",
           reason="Waiting for the Duo runtime.")
alternate = dict(phone, id="alternate", state="deferred", reason="Alternate layout awaits approval.")
play = dict(id="android", store="play", slot="phone", size=[1080,1920], state="active")
screens = [dict(id="screen%d" % i, flow=".listing-kit/flows/open.yaml") for i in range(4)]
screens[0]["only"] = ["iphone"]
screens.append(dict(id="deferred", flow=".listing-kit/flows/open.yaml", only=["duo"]))
data = dict(format=2, app="example.app", locales=[dict(id="en", apple="en-US", play="en-US")],
            targets=[phone, duo, play, alternate], screens=screens,
            graphics=dict(apple={"header-16x9": {"headline": {"en": "Hello"}}}))
Path(sys.argv[1]).write_text(json.dumps(data))
PY
shots="$app/fastlane/screenshots/en-US"
rm "$shots/"*_iphone-medium.png
fake_png "$shots/01_screen0_iphone-medium.png" 1206 2622
cp "$shots/01_screen0_iphone-medium.png" "$shots/02_screen1_iphone-medium.png"
cp "$shots/01_screen0_iphone-medium.png" "$shots/03_screen2_iphone-medium.png"
play_shots="$app/fastlane/metadata/android/en-US/images/phoneScreenshots"
mv "$play_shots/01_recipes.png" "$play_shots/01_screen1.png"
mv "$play_shots/02_recipe-detail.png" "$play_shots/02_screen2.png"
mv "$play_shots/03_shopping.png" "$play_shots/03_screen3.png"
medium='iPhone Dynamic Island (medium display)'
duo='iPhone Duo (outer display)'
result="$("$lk" validate "$app" 2>&1)"; rc=$?
it "an active iPhone target requires all four applicable screenshots"
assert_eq 1 "$rc"
assert_contains "$result" "✗ planned en-US/$medium: 3 of 4 screenshots"
it "Apple graphics declare required header files"
assert_contains "$result" 'planned Apple header en-US/header-16x9.png: MISSING'
it "optional deferred targets retain their reason"
assert_contains "$result" "deferred en-US/$duo: Waiting for the Duo runtime."
assert_not_contains "$result" "planned en-US/$duo:"
"$lk" handoff "$app" >/dev/null 2>&1
index="$(cat "$app/.listing-kit/upload/INDEX.md")"
assert_contains "$index" "en-US/$medium: 3 of 4 screenshots"
assert_contains "$index" "en-US/header-16x9.png: MISSING"
cp "$shots/01_screen0_iphone-medium.png" "$shots/04_screen3_iphone-medium.png"
fake_png "$app/store-assets/apple/en-US/header-16x9.png" 5244 2950
it "Play per-type coverage mismatches warn without failing validation"
result="$("$lk" validate "$app" 2>&1)"; rc=$?
assert_eq 0 "$rc"
assert_contains "$result" '! planned Play en-US/phone: 4 of 3 screenshots'
assert_contains "$result" "planned en-US/$medium: 4 of 4 screenshots"
it "a deferred Duo set in the upcoming requirement window is reported as deferred"
result="$("$lk" validate "$app" --as-of 2027-03-31 --ios-sdk 27.1 2>&1)"
assert_contains "$result" "deferred en-US/$duo: Waiting for the Duo runtime."
assert_not_contains "$result" "no $duo screenshots"
it "a deferred target sharing an active display keeps its reason and leaves the set active"
assert_contains "$result" "Alternate layout awaits approval."
assert_not_contains "$result" "cannot defer required screenshot class: $medium"
it "listing.json wins over even a malformed legacy plan with one warning"
printf 'malformed\n' > "$app/.listing-kit/asset-plan.json"
result="$("$lk" validate "$app" 2>&1)"; rc=$?
assert_eq 0 "$rc"
assert_contains "$result" "asset-plan.json is ignored"
assert_not_contains "$result" "safe to delete"
printf '{"apple":{"en-US":{"headers":["promo.jpg"],"screenshots":{"%s":7}}}}' "$medium" > "$app/.listing-kit/asset-plan.json"
result="$("$lk" validate "$app" 2>&1)"
warning="$(echo "$result" | grep 'asset-plan.json is ignored')"
assert_contains "$warning" "en-US/promo.jpg"
assert_contains "$warning" "en-US/$medium"
assert_not_contains "$warning" "safe to delete"
printf '{"apple":{"en-US":{"headers":["header-16x9.png"],"screenshots":{"%s":4}}}}' "$medium" > "$app/.listing-kit/asset-plan.json"
result="$("$lk" validate "$app" 2>&1)"
assert_not_contains "$result" "safe to delete"
assert_contains "$result" "Other tooling in this repository may still use it"
assert_not_contains "$result" "! asset-plan.json"

it "review and handoff label the deferred display and explain its omission"
"$lk" review "$app" >/dev/null 2>&1
assert_contains "$(cat "$app/listing-review.html")" "$duo — deferred</strong>: Waiting for the Duo runtime."
"$lk" handoff "$app" >/dev/null 2>&1
assert_contains "$(cat "$app/.listing-kit/upload/INDEX.md")" "$duo (en-US)"
assert_contains "$(cat "$app/.listing-kit/upload/INDEX.html")" 'Waiting for the Duo runtime.'
assert_contains "$(cat "$app/.listing-kit/upload/INDEX.md")" 'Alternate layout awaits approval.'
it "staged review derives coverage from the staged listing"
"$lk" hook install "$app" >/dev/null 2>&1
git -C "$app" add .gitignore app.json fastlane store-assets .listing-kit/listing.json
python3 - "$plan" <<'PYPLAN'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
data = json.loads(path.read_text())
next(t for t in data["targets"] if t["id"] == "duo")["reason"] = "Unstaged reason"
path.write_text(json.dumps(data))
PYPLAN
assert_contains "$(cat "$plan")" "Unstaged reason"
assert_not_contains "$(git -C "$app" show :.listing-kit/listing.json)" "Unstaged reason"
git -C "$app" -c user.name=Fixture -c user.email=fixture@example.test commit -qm 'Review planned listing' >/dev/null
page="$(git -C "$app" show HEAD:listing-review.html)"
assert_contains "$page" "$duo — deferred</strong>: Waiting for the Duo runtime."
assert_not_contains "$page" "Unstaged reason"
assert_contains "$page" "planned en-US/$medium: 4 of 4 screenshots"

it "Play checks the mapped locale and counts console files without a metadata folder"
python3 - "$plan" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
d = json.loads(p.read_text())
d["locales"].extend([{"id": "de", "play": "de-DE"}, {"id": "fr", "play": "fr-FR"}])
d["graphics"]["play"] = {"featureGraphic": {"headline": {"en": "Hello"}}}
android = d["targets"][2]
android["locales"] = ["en"]
d["targets"].append(dict(android, id="manual", locales=["de", "fr"], upload="console"))
p.write_text(json.dumps(d))
PY
manual="$app/store-assets/play/de-DE/screenshots/phone"
mkdir -p "$manual"
cp "$play_shots/01_screen1.png" "$manual/first.png"
result="$("$lk" validate "$app" 2>&1)"; rc=$?
assert_eq 1 "$rc"
assert_contains "$result" "store-assets/play/de-DE/screenshots/phone/01_screen1.png: MISSING"
assert_contains "$result" "! planned Play de-DE/phone: 1 of 3 screenshots"

mkdir -p "$app/store-assets/play/it-IT/screenshots/phone"
cp "$manual/first.png" "$app/store-assets/play/it-IT/screenshots/phone/store-only.png"
"$lk" review "$app" >/dev/null 2>&1
page="$(cat "$app/listing-review.html")"
assert_contains "$page" 'de-DE/screenshots/phone/first.png'
assert_contains "$page" 'it-IT/screenshots/phone/store-only.png'
assert_contains "$page" 'class="loclabel">locale: fr-FR</div>'
"$lk" handoff "$app" >/dev/null 2>&1
index="$(cat "$app/.listing-kit/upload/INDEX.md")"
assert_contains "$index" "de-DE/phone: 1 of 3 screenshots"
assert_contains "$index" "fr-FR/phone: 0 of 3 screenshots"
assert_contains "$index" "fr-FR/featureGraphic.png: MISSING"
cp "$manual/first.png" "$manual/second.png"
cp "$manual/first.png" "$manual/third.png"
fake_png "$manual/invalid.png" 12 10
result="$("$lk" validate "$app" 2>&1)"; rc=$?
assert_eq 1 "$rc"
assert_contains "$result" 'invalid.png does not fit Play slot phone'
assert_contains "$result" "✓ planned Play de-DE/phone: 3 of 3 screenshots"
rm "$manual/invalid.png"

it "deferring a store-required display still fails with files present"
python3 - "$plan" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
d = json.loads(p.read_text())
d["targets"][0].update(state="deferred", reason="Unavailable")
p.write_text(json.dumps(d))
PY
result="$("$lk" validate "$app" --as-of 2027-05-01 --ios-sdk 27.0 2>&1)"; rc=$?
assert_eq 1 "$rc"
assert_contains "$result" "cannot defer required screenshot class: $medium"
it "an active target with an empty screen list has nothing planned yet"
python3 - "$plan" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
d = json.loads(p.read_text())
d.update(targets=[dict(d["targets"][0], state="active")], screens=[])
p.write_text(json.dumps(d))
PY
result="$("$lk" validate "$app" 2>&1)"
assert_contains "$result" "! planned en-US/$medium: nothing planned yet"
it "shared sizes and labels retain independent slot counts"
python3 - "$plan" <<'PYPLAN'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
d = json.loads(p.read_text())
d["targets"] = [dict(id=slot, store="apple", slot=slot, size=size, state="active", suffix=suffix)
                for slot, size, suffix in [
                    ("ipad-13", [2048,2732], "ipad-13"), ("ipad-12-9", [2048,2732], "ipad129"),
                    ("iphone-duo-outer", [1398,2034], "outer"), ("iphone-duo-inner", [2007,2853], "inner")]]
d["screens"] = [{"id":"one", "flow":".listing-kit/flows/open.yaml", "except":["ipad-12-9"]},
                {"id":"two", "flow":".listing-kit/flows/open.yaml", "only":["ipad-12-9"]}]
p.write_text(json.dumps(d))
PYPLAN
printf '{"stores":{"apple":{"screenshots":{"slots":[{"id":"iphone-duo-inner","label":"iPhone Duo"},{"id":"iphone-duo-outer","label":"iPhone Duo"}]}}}}' > "$app/.listing-kit/specs.override.json"
remove_fixture "$shots"
fake_png "$shots/01_one_ipad-13.png" 2048 2732
cp "$shots/01_one_ipad-13.png" "$shots/01_two_ipad129.png"
fake_png "$shots/01_one_outer.png" 1398 2034
fake_png "$shots/01_one_inner.png" 2007 2853
result="$("$lk" validate "$app" 2>&1)"
assert_contains "$result" '✓ planned en-US/iPad 13": 1 of 1 screenshots'
assert_contains "$result" '✓ planned en-US/iPad 12.9": 1 of 1 screenshots'
assert_eq 2 "$(echo "$result" | grep -c '✓ planned en-US/iPhone Duo: 1 of 1 screenshots')"
sed 's/"ipad129"/"ipad-13"/' "$plan" > "$app/conflict"
mv "$app/conflict" "$plan"
mkdir -p "$app/.listing-kit/flows"
touch "$app/.listing-kit/flows/open.yaml"
result="$("$lk" plan check "$app" 2>&1)"; rc=$?
assert_eq 1 "$rc"
assert_contains "$result" "cannot distinguish ipad-12-9"

it "a deferred Apple target alone does not create an Apple locale"
new_tempdir play_only
mkdir -p "$play_only/fastlane/metadata" "$play_only/.listing-kit"
cp -R "$app/fastlane/metadata/android" "$play_only/fastlane/metadata/"
cat > "$play_only/.listing-kit/listing.json" <<'JSON'
{"format":2,"app":"example.app","locales":["en-US"],"targets":[
{"id":"android","store":"play","slot":"phone","size":[1080,1920],"state":"active"},
{"id":"iphone","store":"apple","slot":"iphone-di-medium","size":[1206,2622],"state":"deferred","reason":"iOS later"}],
"screens":[{"id":"one","flow":".listing-kit/flows/open.yaml"},{"id":"two","flow":".listing-kit/flows/open.yaml"}]}
JSON
folder="$play_only/fastlane/metadata/android/en-US/images/phoneScreenshots"
mv "$folder/01_screen1.png" "$folder/01_one.png"
mv "$folder/02_screen2.png" "$folder/02_two.png"
result="$("$lk" validate "$play_only" 2>&1)"; rc=$?
assert_eq 0 "$rc"
assert_not_contains "$result" "== Apple App Store =="
"$lk" handoff "$play_only" >/dev/null 2>&1
assert_not_contains "$(cat "$play_only/.listing-kit/upload/INDEX.md")" "iOS later"

it "a handoff with no packaged files still lists the planned shortfalls"
remove_fixture "$play_only/fastlane"
"$lk" handoff "$play_only" >/dev/null 2>&1; rc=$?
assert_eq 1 "$rc"
assert_contains "$(cat "$play_only/.listing-kit/upload/INDEX.md")" "en-US/phone: 0 of 2 screenshots"

it "deferring an iPad does not mask unknown tablet support"
printf '{"expo":{}}' > "$app/app.json"
rm "$app/.listing-kit/specs.override.json" "$app/.listing-kit/asset-plan.json"
remove_fixture "$shots"
fake_png "$shots/phone.png" 1206 2622
cat > "$plan" <<'JSON'
{"format":2,"app":"example.app","locales":["en-US"],"targets":[
{"id":"phone","store":"apple","slot":"iphone-di-medium","size":[1206,2622],"state":"active"},
{"id":"tablet","store":"apple","slot":"ipad-13","size":[2048,2732],"state":"deferred","reason":"later"}],
"screens":[{"id":"one","flow":".listing-kit/flows/open.yaml"}]}
JSON
result="$("$lk" validate "$app" 2>&1)"; rc=$?
assert_eq 1 "$rc"
assert_contains "$result" '✗ no iPad 13" screenshots'
"$lk" handoff "$app" >/dev/null 2>&1
assert_contains "$(cat "$app/.listing-kit/upload/INDEX.md")" 'no iPad 13" screenshots'
assert_contains "$result" 'cannot defer required screenshot class: iPad 13"'
assert_contains "$(cat "$app/.listing-kit/upload/INDEX.md")" 'cannot defer required screenshot class: iPad 13"'

it "an unresolved primary rule still reports its missing screenshots when deferred"
result="$(PYTHONPATH="$SCRIPTS/lib" python3 - "$app" <<'PYROWS'
from pathlib import Path
import sys
import detect, rules_check, specs
root = Path(sys.argv[1])
rules = specs.load(root)
req = detect.Requirements(root, rules)
for level, message in rules_check.apple_shots(root, "en-US", rules, req, {"ipad-13"}, planned=True):
    if level == "FAIL":
        print(message)
PYROWS
)"
assert_contains "$result" 'no iPad 13" screenshots (need ≥1) — set supportsIpad'
summary
