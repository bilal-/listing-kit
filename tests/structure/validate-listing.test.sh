#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/validate/validate-listing.sh"
# Keep historical example captures unchanged; add a synthetic medium-size test fixture.
APP="$(mktemp -d)"
cp -R "$ROOT/examples/expo-recipe-box/fastlane" "$ROOT/examples/expo-recipe-box/app.json" "$APP/"
fake_png "$APP/fastlane/screenshots/en-US/medium_01.png" 1206 2622
trap 'rm -rf "$APP"' EXIT

it "a current-size fixture passes validation (both stores, exit 0)"
OUT="$(bash "$SUT" "$APP" 2>&1)"; RC=$?
assert_eq 0 "$RC" "exit 0"
assert_contains "$OUT" "LISTING VALID"
assert_contains "$OUT" "iPhone screenshots present"
assert_contains "$OUT" "iPad screenshots present"            # required since supportsTablet
assert_contains "$OUT" "feature graphic 1024x500 24-bit no-alpha"
assert_contains "$OUT" "secret scan: clean"

# --- negative cases (text/file-ops only; no ImageMagick needed in CI) ---
it "fails when an App Store copy field exceeds its limit"
T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
printf 'x%.0s' {1..40} > "$T/fastlane/metadata/en-US/name.txt"   # 40 > 30
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "exit 1 on over-limit name"
assert_contains "$OUT" "OVER LIMIT"
rm -rf "$T"

it "fails when iPad screenshots are missing but the app supports iPad"
T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
rm -f "$T"/fastlane/screenshots/en-US/ipad13_*.png
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "exit 1 when iPad set missing"
assert_contains "$OUT" "NO iPad screenshots"
rm -rf "$T"

it "fails when the Play feature graphic is missing"
T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"
rm -f "$T"/fastlane/metadata/android/en-US/images/featureGraphic.png
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "exit 1 when feature graphic missing"
assert_contains "$OUT" "feature graphic MISSING"
rm -rf "$T"

# --- #3: a field at exactly the limit with a trailing newline must NOT over-count ---
it "a 30-char name with a trailing newline counts as 30/30, not 31/30"
T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
{ printf 'x%.0s' {1..30}; printf '\n'; } > "$T/fastlane/metadata/en-US/name.txt"   # 30 chars + newline
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC" "exit 0 — trailing newline is stripped before counting"
assert_contains "$OUT" "name: 30/30 chars"
assert_not_contains "$OUT" "OVER LIMIT"
rm -rf "$T"

# --- #2: single-store listings validate without failing for the absent store ---
it "a Play-only listing passes (no spurious Apple iPhone-screenshot failure)"
T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"; rm -rf "$T"/fastlane/screenshots "$T"/fastlane/metadata/en-US
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC" "exit 0 for Play-only"
assert_contains "$OUT" "== Google Play =="
assert_not_contains "$OUT" "== Apple App Store =="
rm -rf "$T"

it "an Apple-only listing passes (no spurious Play feature-graphic failure)"
T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"; rm -rf "$T"/fastlane/metadata/android
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC" "exit 0 for Apple-only"
assert_contains "$OUT" "== Apple App Store =="
assert_not_contains "$OUT" "== Google Play =="
rm -rf "$T"

# --- #1: iPad requirement is detected for NATIVE iOS (pbxproj), not just Expo ---
it "fails on a native-iOS universal app (TARGETED_DEVICE_FAMILY=2) with no iPad screenshots"
T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"            # NOTE: no app.json → not the Expo path
rm -f "$T"/fastlane/screenshots/en-US/ipad13_*.png
mkdir -p "$T/App.xcodeproj"; printf 'TARGETED_DEVICE_FAMILY = "1,2";\n' > "$T/App.xcodeproj/project.pbxproj"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "exit 1 — native iPad support detected, iPad shots required"
assert_contains "$OUT" "NO iPad screenshots"
rm -rf "$T"

# --- store-rule checks driven by tiny synthetic images (tests/helpers.sh) ---
png() { fake_png "$@"; }   # <path> <w> <h> [depth=8] [colortype=2]
apple_only() { T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"; rm -rf "$T"/fastlane/metadata/android; }
play_only()  { T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"; rm -rf "$T"/fastlane/screenshots "$T"/fastlane/metadata/en-US; }
PHONE=fastlane/metadata/android/en-US/images/phoneScreenshots

it "a Face ID large set alone cannot fill the medium upload slot"
apple_only; rm -f "$T"/fastlane/screenshots/en-US/0*.png "$T"/fastlane/screenshots/en-US/medium_01.png
png "$T/fastlane/screenshots/en-US/01_home.png" 1284 2778
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "no iPhone Dynamic Island (medium display) screenshots"
rm -rf "$T"

it "a Face ID medium set does not fill the Dynamic Island medium slot"
apple_only; rm -f "$T"/fastlane/screenshots/en-US/0*.png "$T"/fastlane/screenshots/en-US/medium_01.png
png "$T/fastlane/screenshots/en-US/01_home.png" 1170 2532
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "no iPhone Dynamic Island (medium display) screenshots"
rm -rf "$T"

it "an 11\" iPad set does not satisfy the 13\" iPad requirement"
apple_only; rm -f "$T"/fastlane/screenshots/en-US/ipad13_*.png
png "$T/fastlane/screenshots/en-US/ipad11_01.png" 1668 2420
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "NO iPad screenshots"
rm -rf "$T"

it "landscape screenshots are recognized"
apple_only; png "$T/fastlane/screenshots/en-US/05_wide.png" 2868 1320
OUT="$(bash "$SUT" "$T" 2>&1)"
assert_not_contains "$OUT" "not a recognized App Store size"
rm -rf "$T"

it "more than 10 screenshots in one display class fails"
apple_only
for i in 05 06 07 08 09 10 11; do png "$T/fastlane/screenshots/en-US/${i}_x.png" 1320 2868; done
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "11 screenshots (App Store max is 10"
rm -rf "$T"

it "each screenshot locale is checked on its own"
apple_only; mkdir -p "$T/fastlane/screenshots/de-DE"
png "$T/fastlane/screenshots/de-DE/01_home.png" 1170 2532
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "a locale without a Dynamic Island medium set fails even if en-US has one"
assert_contains "$OUT" "screenshots de-DE:"
rm -rf "$T"

it "keywords are limited to 100 UTF-8 bytes, not characters"
apple_only
python3 -c "import sys;open(sys.argv[1],'w',encoding='utf-8').write('料'*40)" "$T/fastlane/metadata/en-US/keywords.txt"   # 40 chars, 120 bytes
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "keywords: 120/100 bytes OVER LIMIT"
rm -rf "$T"

it "a 16-bit-depth Play screenshot fails (24-bit means 8 bits per channel)"
play_only; png "$T/$PHONE/05_deep.png" 1080 1920 16 2
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "05_deep.png: must be 24-bit no-alpha (depth=16"
rm -rf "$T"

it "a Play screenshot over 2:1 fails"
play_only; png "$T/$PHONE/05_tall.png" 1080 2400
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "05_tall.png: aspect"
rm -rf "$T"

it "Play's 2-screenshot minimum counts across device types"
play_only; rm -f "$T/$PHONE"/*.png
png "$T/$PHONE/01_home.png" 1080 1920
png "$T/fastlane/metadata/android/en-US/images/tenInchScreenshots/01_home.png" 1920 1080
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC" "1 phone + 1 tablet passes"
assert_contains "$OUT" "screenshots across device types: 2"
assert_contains "$OUT" "promotion eligibility"
rm -rf "$T"

it "a single Play screenshot fails"
play_only; rm -f "$T/$PHONE"/0[2-9]*.png
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "need ≥2"
rm -rf "$T"

it "a non-PNG file with a .png name fails cleanly instead of crashing"
play_only; printf 'not a png' > "$T/$PHONE/05_bogus.png"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_not_contains "$OUT" "integer expression"
assert_not_contains "$OUT" "Traceback"
rm -rf "$T"

# --- fastlane supply layout: graphics are files directly in images/ ---
IMG=fastlane/metadata/android/en-US/images

it "the old nested images/featureGraphic/ layout fails (supply never uploads it)"
play_only; mkdir -p "$T/$IMG/featureGraphic"; mv "$T/$IMG/featureGraphic.png" "$T/$IMG/featureGraphic/"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "images/featureGraphic/ is not uploaded by fastlane supply"
rm -rf "$T"

it "a JPEG feature graphic is accepted"
play_only; rm "$T/$IMG/featureGraphic.png"
fake_jpeg "$T/$IMG/featureGraphic.jpg" 1024 500
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" "feature graphic 1024x500"
rm -rf "$T"

it "a missing Play icon fails (it's required)"
play_only; rm "$T/$IMG/icon.png"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "Play icon MISSING"
rm -rf "$T"

it "Wear OS screenshots are validated"
play_only; png "$T/$IMG/wearScreenshots/01.png" 384 384 8 6
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "RGBA wear screenshot fails"
assert_contains "$OUT" "Wear OS screenshots: 1"
rm -rf "$T"

# --- required copy must be present, non-empty, and URLs must be URLs ---
it "an empty required field fails"
apple_only; : > "$T/fastlane/metadata/en-US/name.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "name: file is empty"
rm -rf "$T"

it "a missing support URL fails (Apple requires it)"
apple_only; rm "$T/fastlane/metadata/en-US/support_url.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "support_url: REQUIRED file missing"
rm -rf "$T"

it "a URL field that isn't a URL fails"
apple_only; echo "see our website" > "$T/fastlane/metadata/en-US/privacy_url.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "privacy_url: not a single http(s) URL"
rm -rf "$T"

it "JPEG screenshots count toward the iPhone set"
apple_only; rm -f "$T"/fastlane/screenshots/en-US/0*.png "$T"/fastlane/screenshots/en-US/medium_01.png
fake_jpeg "$T/fastlane/screenshots/en-US/01_home.jpeg" 1179 2556
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" "iPhone screenshots present (1 at"
rm -rf "$T"

# --- iPad detection beyond app.json ---
it "detects supportsTablet in a dynamic app.config.ts"
apple_only; rm "$T/app.json" "$T"/fastlane/screenshots/en-US/ipad13_*.png
printf 'export default { ios: { supportsTablet: true } };\n' > "$T/app.config.ts"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "NO iPad screenshots"
rm -rf "$T"

it "LK_SUPPORTS_IPAD=0 overrides detection"
apple_only; rm -f "$T"/fastlane/screenshots/en-US/ipad13_*.png
OUT="$(LK_SUPPORTS_IPAD=0 bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_not_contains "$OUT" "iPad"
rm -rf "$T"

it "an upper-case extension fails (fastlane won't upload it on Linux)"
apple_only; mv "$T/fastlane/screenshots/en-US/01_recipes.png" "$T/fastlane/screenshots/en-US/01_recipes.PNG"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "01_recipes.PNG: rename with a lower-case extension"
rm -rf "$T"

it "an unrecognized App Store screenshot size fails"
apple_only; png "$T/fastlane/screenshots/en-US/09_odd.png" 100 100
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "09_odd.png: 100x100 is not an App Store screenshot size"
rm -rf "$T"

it "an RGB PNG with tRNS transparency fails the no-alpha check"
apple_only
fake_png "$T/fastlane/screenshots/en-US/05_trns.png" 1320 2868 8 2 trns
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "05_trns.png: must be RGB no-alpha (colortype=2+tRNS)"
rm -rf "$T"

it "a screenshot locale without a metadata folder still needs its copy"
apple_only; mkdir -p "$T/fastlane/screenshots/fr-FR"
cp "$T"/fastlane/screenshots/en-US/*.png "$T/fastlane/screenshots/fr-FR/"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "locale fr-FR:"
assert_contains "$OUT" "name: REQUIRED file missing"
rm -rf "$T"

it "fields missing from a locale fall back to metadata/default/"
apple_only; mkdir -p "$T/fastlane/metadata/default"
mv "$T/fastlane/metadata/en-US/support_url.txt" "$T/fastlane/metadata/en-US/privacy_url.txt" "$T/fastlane/metadata/default/"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" "support_url: https://"
rm -rf "$T"

it "a bare https:// URL fails"
apple_only; echo "https://" > "$T/fastlane/metadata/en-US/support_url.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "support_url: not a single http(s) URL"
rm -rf "$T"

it "a non-UTF-8 copy file fails instead of being skipped"
apple_only; printf 'Caf\xe9\n' > "$T/fastlane/metadata/en-US/subtitle.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "subtitle: not valid UTF-8"
assert_contains "$OUT" "name: 23/30"   # other fields are still checked
rm -rf "$T"

it "a JPEG Play icon fails (Play requires PNG)"
play_only; rm "$T/$IMG/icon.png"
fake_jpeg "$T/$IMG/icon.jpg" 512 512
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "icon must be a PNG"
rm -rf "$T"

it "LK_SUPPORTS_IPHONE=0 allows an iPad-only listing"
apple_only; rm -f "$T"/fastlane/screenshots/en-US/0*.png "$T"/fastlane/screenshots/en-US/medium_01.png
OUT="$(LK_SUPPORTS_IPHONE=0 bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
rm -rf "$T"

it "promotion eligibility needs 9:16 or 16:9, not just 1080px"
play_only; rm -f "$T/$PHONE"/*.png
for i in 1 2 3 4; do png "$T/$PHONE/0${i}.png" 1080 2160; done
OUT="$(bash "$SUT" "$T" 2>&1)"
assert_contains "$OUT" "only 0 screenshot(s)" "1080x2160 (1:2) doesn't count"
rm -f "$T/$PHONE"/*.png
for i in 1 2 3 4; do png "$T/$PHONE/0${i}.png" 1080 1920; done
OUT="$(bash "$SUT" "$T" 2>&1)"
assert_not_contains "$OUT" "promotion eligibility" "four 1080x1920 shots qualify"
rm -rf "$T"

it "a truncated PNG (header but no image data) fails"
apple_only; head -c 33 "$T/fastlane/screenshots/en-US/01_recipes.png" > "$T/x" && mv "$T/x" "$T/fastlane/screenshots/en-US/01_recipes.png"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "01_recipes.png: 0x0 is not an App Store screenshot size"
rm -rf "$T"

it "a JPEG saved as icon.png fails"
play_only; fake_jpeg "$T/$IMG/icon.png" 512 512
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "icon must be a PNG"
rm -rf "$T"

it "a Play tree with no locale folders fails"
T="$(mktemp -d)"; mkdir -p "$T/fastlane/metadata/android"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "has no locale folders"
rm -rf "$T"

it "an App Store name under 2 characters fails"
apple_only; printf 'R\n' > "$T/fastlane/metadata/en-US/name.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "under the 2-chars minimum"
rm -rf "$T"

it "Play changelogs are limited to 500 characters"
play_only; mkdir -p "$T/fastlane/metadata/android/en-US/changelogs"
printf 'x%.0s' $(seq 1 501) > "$T/fastlane/metadata/android/en-US/changelogs/42.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "changelogs/42: 501/500 chars OVER LIMIT"
rm -rf "$T"

it "hidden folders (metadata/.backup) are not treated as locales"
apple_only; mkdir -p "$T/fastlane/metadata/.backup"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_not_contains "$OUT" "locale .backup"
rm -rf "$T"

summary
