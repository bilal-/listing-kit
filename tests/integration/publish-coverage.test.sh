#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir app
new_tempdir credentials
new_stubdir
export PATH="$STUB_BIN:$PATH"
export APP_STORE_CONNECT_API_KEY_PATH="$credentials/apple.json" SUPPLY_JSON_KEY="$credentials/play.json"
printf '{}\n' > "$APP_STORE_CONNECT_API_KEY_PATH"
printf '{}\n' > "$SUPPLY_JSON_KEY"
unset LK_PUBLISH_UNVERIFIED LK_SUPPORTS_IPHONE LK_SUPPORTS_IPAD
cat > "$STUB_BIN/fastlane" <<'PY'
#!/usr/bin/env python3
import os, sys
from pathlib import Path
args = sys.argv[1:]
if args == ["--version"]:
    print("fastlane 2.242.0")
    sys.exit(0)
if args[:2] not in (["deliver", "download_metadata"], ["deliver", "download_screenshots"], ["supply", "init"]):
    sys.exit("Unexpected fastlane command")
option = "--screenshots_path" if args[1] == "download_screenshots" else "--metadata_path"
destination = Path(args[args.index(option) + 1])
destination.mkdir()
if args[1] == "download_metadata":
    # Ordinary text tests begin with the app's existing category.
    (destination / "primary_category.txt").write_bytes(Path(os.environ["APPLE_CATEGORY"]).read_bytes())
store = "apple" if args[0] == "deliver" else "play"
view = Path.cwd().parents[1] / (store + "-view")
Path(os.environ["VIEW_FILES"]).write_text("\n".join(sorted(
    str(path.relative_to(view)) for path in view.rglob("*") if path.is_file())))
PY
chmod +x "$STUB_BIN/fastlane"
lk="$SKILL_DIR/bin/listing-kit"
git init -q "$app"
export VIEW_FILES="$credentials/view-files"
example="$ROOT/examples/expo-recipe-box"
cp -R "$example/fastlane" "$example/app.json" "$app/"
meta="$app/fastlane/metadata"
export APPLE_CATEGORY="$meta/primary_category.txt"
cp -R "$meta/en-US" "$meta/fr-FR"
mkdir -p "$app/.listing-kit/flows"
plan="$app/.listing-kit/listing.json"
touch "$app/.listing-kit/flows/open.yaml"
cat > "$plan" <<'JSON'
{
  "format": 2, "app": "example.app", "platforms": {"supportsIpad": false},
  "locales": [{"id": "en", "apple": "en-US", "play": "en-US"}, {"id": "fr", "apple": "fr-FR"}],
  "screens": [
    {"id": "one", "flow": ".listing-kit/flows/open.yaml"},
    {"id": "two", "flow": ".listing-kit/flows/open.yaml", "only": ["android"]}
  ],
  "targets": [
    {"id": "phone", "store": "apple", "slot": "iphone-di-medium", "size": [1206,2622], "state": "active", "locales": ["en"]},
    {"id": "large", "store": "apple", "slot": "iphone-di-large", "size": [1320,2868], "state": "deferred", "reason": "later"},
    {"id": "android", "store": "play", "slot": "phone", "size": [1080,1920], "state": "active"}
  ],
  "graphics": {"apple": {"header-16x9": {"headline": {"en": "Hello", "fr": "Bonjour"}}}}
}
JSON
remove_fixture "$app/fastlane/screenshots"
fake_png "$app/fastlane/screenshots/en-US/01_one_iphone-medium.png" 1206 2622
fake_png "$app/store-assets/apple/en-US/header-16x9.png" 5244 2950
mkdir -p "$app/store-assets/apple/fr-FR"
cp "$app/store-assets/apple/en-US/header-16x9.png" "$app/store-assets/apple/fr-FR/"
play_shots="$meta/android/en-US/images/phoneScreenshots"
mv "$play_shots/01_recipes.png" "$play_shots/01_one.png"
mv "$play_shots/02_recipe-detail.png" "$play_shots/02_two.png"

rm "$play_shots/03_shopping.png" "$play_shots/04_settings.png"

it "Apple text, graphics and deferrals are validated in a locale with no planned screenshots"
out="$("$lk" validate "$app" 2>&1)"; assert_eq 0 "$?"
assert_contains "$out" 'locale fr-FR:'
assert_contains "$out" 'deferred fr-FR/iPhone'
assert_not_contains "$out" 'screenshots fr-FR:'
"$lk" handoff "$app" >/dev/null 2>&1; assert_eq 0 "$?"
index="$(cat "$app/.listing-kit/upload/INDEX.md")"
assert_contains "$index" '(fr-FR) — later'
assert_not_contains "$index" 'fr-FR: no'
assert_file "$app/.listing-kit/upload/apple/fr-FR/text/name.txt"

it "the Apple preview validates and includes the mapped metadata-only locale"
out="$("$lk" publish "$app" --store apple 2>&1)"; assert_eq 0 "$?"
assert_contains "$out" 'deferred fr-FR/iPhone'
assert_contains "$out" 'apple metadata/fr-FR/name.txt added'
assert_not_contains "$out" 'screenshots fr-FR:'

it "a metadata-only locale inherits the required display supplied by the primary locale"
cp "$plan" "$credentials/original-plan.json"
sed 's/"iphone-di-large", "size": \[1320,2868\]/"iphone-di-medium", "size": [1206,2622]/' "$credentials/original-plan.json" > "$plan"
out="$("$lk" validate "$app" 2>&1)"; assert_eq 0 "$?"
assert_contains "$out" 'deferred fr-FR/iPhone Dynamic Island (medium display): later'
"$lk" handoff "$app" >/dev/null 2>&1; assert_eq 0 "$?"
assert_not_contains "$(cat "$app/.listing-kit/upload/INDEX.md")" 'cannot defer required screenshot class'
out="$("$lk" publish "$app" --store apple 2>&1)"; assert_eq 0 "$?"
assert_contains "$out" 'deferred fr-FR/iPhone Dynamic Island (medium display): later'
mv "$credentials/original-plan.json" "$plan"

it "only the planned locale is missing screenshots when capture has not started"
mv "$app/fastlane/screenshots" "$credentials/captures"
out="$("$lk" validate "$app" 2>&1)"; assert_eq 1 "$?"
assert_contains "$out" 'planned en-US/iPhone Dynamic Island (medium display): 0 of 1 screenshots'
assert_not_contains "$out" 'screenshots fr-FR:'
mv "$credentials/captures" "$app/fastlane/screenshots"

it "publish views contain only listing trees and plan files"
mkdir -p "$app/android/app/src/main" "$app/ios/App.xcodeproj"
touch "$app/ios/App.xcodeproj/project.pbxproj" "$app/ios/Info.plist" "$app/app.config.js"
echo 'plugins { id "com.android.application" }' > "$app/android/app/build.gradle"
manifest="$app/android/app/src/main/AndroidManifest.xml"
echo '<manifest><application/></manifest>' > "$manifest"
out="$("$lk" publish "$app" --store play 2>&1)"; assert_eq 0 "$?"
files="$(cat "$VIEW_FILES")"
assert_contains "$files" 'fastlane/metadata/android/en-US/title.txt'
unexpected="$(grep -Ev '^(fastlane/(metadata|screenshots)/|store-assets/(apple|play)/|\.listing-kit/(listing|asset-plan|specs\.override)\.json$)' "$VIEW_FILES")"
assert_eq '' "$unexpected"

it "a Maps key in the Android application manifest permits a text-only Play preview"
printf '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application><meta-data android:name="com.google.android.geo.API_KEY" android:value="AIza%035d"/></application></manifest>\n' 0 > "$manifest"
out="$("$lk" publish "$app" --store play 2>&1)"; assert_eq 0 "$?"
assert_contains "$out" 'play metadata/en-US/title.txt added'
assert_contains "$out" '--skip_upload_screenshots'
assert_not_contains "$out" 'Credential-like content'
rm "$manifest"

it "empty video requires explicit consent for that exact Play locale"
video="$meta/android/en-US/video.txt"
: > "$video"
out="$("$lk" publish "$app" --store play 2>&1)"; assert_eq 1 "$?"
assert_contains "$out" "would clear the live video"
cp "$plan" "$credentials/before-video.json"
python3 - "$plan" <<'PYVIDEO'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
data = json.loads(p.read_text())
data["locales"][0]["clearPlayVideo"] = True
p.write_text(json.dumps(data))
PYVIDEO
out="$("$lk" publish "$app" --store play 2>&1)"; assert_eq 0 "$?"
assert_contains "$out" "metadata/en-US/video.txt"
assert_contains "$out" "Cannot touch"
rm "$video"
mv "$credentials/before-video.json" "$plan"

it "a missing Play metadata directory fails validation for the exact planned paths"
mv "$meta/android" "$credentials/play-metadata"
out="$("$lk" validate "$app" 2>&1)"; assert_eq 1 "$?"
assert_contains "$out" 'fastlane/metadata/android/en-US/images/phoneScreenshots/01_one.png: MISSING'
assert_contains "$out" '✗ planned Play en-US/phone: 0 of 2 screenshots'
mv "$credentials/play-metadata" "$meta/android"

it "a custom 12.9-inch suffix selects its own deliver group at the shared iPad size"
python3 - "$plan" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
data = json.loads(path.read_text())
for slot, suffix in [("ipad-13", "tablet"), ("ipad-12-9", "ipad129")]:
    data["targets"].append(dict(id=slot, store="apple", slot=slot, suffix=suffix,
                                size=[2048,2732], state="active", locales=["en"]))
path.write_text(json.dumps(data))
PY
fake_png "$app/fastlane/screenshots/en-US/01_one_tablet.png" 2048 2732
cp "$app/fastlane/screenshots/en-US/01_one_tablet.png" "$app/fastlane/screenshots/en-US/01_one_ipad129.png"
out="$("$lk" publish "$app" --store apple 2>&1)"; assert_eq 0 "$?"
assert_contains "$out" 'en-US APP_IPAD_PRO_129 1 local images'
assert_contains "$out" 'en-US APP_IPAD_PRO_3GEN_129 1 local images'

it "screenshots present on disk in a locale the plan does not cover are still checked"
fake_png "$app/fastlane/screenshots/fr-FR/old.png" 1000 1000
out="$("$lk" validate "$app" 2>&1)"; assert_eq 1 "$?"
assert_contains "$out" 'screenshots fr-FR:'
assert_contains "$out" 'old.png'
remove_fixture "$app/fastlane/screenshots/fr-FR"
out="$("$lk" validate "$app" 2>&1)"; assert_eq 0 "$?"
assert_not_contains "$out" 'screenshots fr-FR:'

summary
