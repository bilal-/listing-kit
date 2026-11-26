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
fake_png "$shots/one.png" 1206 2622
cp "$shots/one.png" "$shots/two.png"
cp "$shots/one.png" "$shots/three.png"
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
cp "$shots/one.png" "$shots/four.png"
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
assert_eq 1 "$(echo "$result" | grep -c '! .*asset-plan.json.*ignored.*safe to delete')"
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
git -C "$app" -c user.name=Fixture -c user.email=fixture@example.test commit -qm 'Review planned listing' >/dev/null
page="$(git -C "$app" show HEAD:listing-review.html)"
assert_contains "$page" "$duo — deferred</strong>: Waiting for the Duo runtime."
assert_contains "$page" "planned en-US/$medium: 4 of 4 screenshots"

it "Play checks the mapped locale and counts console files without a metadata folder"
python3 - "$plan" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
d = json.loads(p.read_text())
d["locales"].append({"id": "de", "play": "de-DE"})
android = d["targets"][2]
android["locales"] = ["en"]
d["targets"].append(dict(android, id="manual", locales=["de"], upload="console"))
p.write_text(json.dumps(d))
PY
manual="$app/store-assets/play/de-DE/screenshots/phone"
mkdir -p "$manual"
cp "$app"/fastlane/metadata/android/en-US/images/phoneScreenshots/01_*.png "$manual/first.png"
result="$("$lk" validate "$app" 2>&1)"; rc=$?
assert_eq 0 "$rc"
assert_contains "$result" "! planned Play de-DE/phone: 1 of 3 screenshots"

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
it "an active target with an empty screen list expects zero screenshots"
python3 - "$plan" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
d = json.loads(p.read_text())
d.update(targets=[dict(d["targets"][0], state="active")], screens=[])
p.write_text(json.dumps(d))
PY
result="$("$lk" validate "$app" 2>&1)"
assert_contains "$result" "✗ planned en-US/$medium: 4 of 0 screenshots"
summary
