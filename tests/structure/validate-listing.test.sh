#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/validate/validate-listing.sh"
# FIXTURE, not the example as shipped: a copy plus a synthetic medium-size iPhone
# screenshot, so these tests have a valid tree to mutate. The example as committed is
# checked without any addition in tests/structure/examples.test.sh.
new_tempdir APP
cp -R "$ROOT/examples/expo-recipe-box/fastlane" "$ROOT/examples/expo-recipe-box/app.json" "$APP/"
fake_png "$APP/fastlane/screenshots/en-US/medium_01.png" 1206 2622

it "a current-size fixture passes validation (both stores, exit 0)"
OUT="$(bash "$SUT" "$APP" 2>&1)"; RC=$?
assert_eq 0 "$RC" "exit 0"
assert_contains "$OUT" "LISTING VALID"
assert_contains "$OUT" "iPhone Dynamic Island (medium display) screenshots present"
assert_contains "$OUT" 'iPad 13" screenshots present'            # required since supportsTablet
assert_contains "$OUT" "Feature graphic 1024x500"
assert_contains "$OUT" "secret scan: clean"

it "rejects demo account filenames anywhere in the listing, even when empty"
for name in demo_user demo_password; do
  demo="$APP/fastlane/metadata/review_information/$name.txt"
  mkdir -p "${demo%/*}"
  for content in '' $' \t\n' 'private-demo-value'; do
    printf '%s' "$content" > "$demo"
    OUT="$(bash "$SUT" "$APP" 2>&1)"; assert_eq 1 "$?"
    assert_contains "$OUT" "$name.txt"
    assert_contains "$OUT" "App Store Connect"
    assert_contains "$OUT" "outside the repo"
    assert_not_contains "$OUT" "private-demo-value"
  done
  rm "$demo"
done
touch "$APP/fastlane/screenshots/en-US/demo_user.txt"
OUT="$(bash "$SUT" "$APP" 2>&1)"; assert_eq 1 "$?"
assert_contains "$OUT" "demo_user.txt"
rm "$APP/fastlane/screenshots/en-US/demo_user.txt"

it "validates optional review information without printing its contents"
review="$APP/fastlane/metadata/review_information"
for field in first_name last_name notes; do printf 'private fixture' > "$review/$field.txt"; done
printf 'test@example.org' > "$review/email_address.txt"
printf '+1 (555) 010-1234' > "$review/phone_number.txt"
OUT="$(bash "$SUT" "$APP" 2>&1)"; assert_eq 0 "$?"
for field in first_name last_name notes email_address phone_number; do assert_contains "$OUT" "$field"; done
assert_not_contains "$OUT" "private fixture"
assert_not_contains "$OUT" "test@example.org"
printf 'invalid-private-value' | tee "$review/email_address.txt" > "$review/phone_number.txt"
OUT="$(bash "$SUT" "$APP" 2>&1)"; assert_eq 1 "$?"
assert_contains "$OUT" "email_address"
assert_contains "$OUT" "phone_number"
assert_not_contains "$OUT" "invalid-private-value"
rm "$review"/*.txt

it "checks the Play video URL scheme and host"
video="$APP/fastlane/metadata/android/en-US/video.txt"
for url in 'https://www.youtube.com/watch?v=example' 'https://youtu.be/example'; do
  printf '%s' "$url" > "$video"
  OUT="$(bash "$SUT" "$APP" 2>&1)"; assert_eq 0 "$?"
done
for url in 'http://youtu.be/example' 'https://youtube.com.example.org/watch' 'https://youtube.com@example.org/watch'; do
  printf '%s' "$url" > "$video"
  OUT="$(bash "$SUT" "$APP" 2>&1)"; assert_eq 1 "$?"
  assert_contains "$OUT" "YouTube"
done
rm "$video"

# --- negative cases (text/file-ops only; no ImageMagick needed in CI) ---
it "fails when an App Store copy field exceeds its limit"
new_tempdir T; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
printf 'x%.0s' {1..40} > "$T/fastlane/metadata/en-US/name.txt"   # 40 > 30
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "exit 1 on over-limit name"
assert_contains "$OUT" "OVER LIMIT"
remove_fixture "$T"

it "fails when iPad screenshots are missing but the app supports iPad"
new_tempdir T; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
rm -f "$T"/fastlane/screenshots/en-US/ipad13_*.png
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "exit 1 when iPad set missing"
assert_contains "$OUT" 'no iPad 13" screenshots'
remove_fixture "$T"

it "fails when the Play feature graphic is missing"
new_tempdir T; cp -R "$APP/fastlane" "$T/"
rm -f "$T"/fastlane/metadata/android/en-US/images/featureGraphic.png
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "exit 1 when feature graphic missing"
assert_contains "$OUT" "Feature graphic MISSING"
remove_fixture "$T"

# --- #3: a field at exactly the limit with a trailing newline must NOT over-count ---
it "a 30-char name with a trailing newline counts as 30/30, not 31/30"
new_tempdir T; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
{ printf 'x%.0s' {1..30}; printf '\n'; } > "$T/fastlane/metadata/en-US/name.txt"   # 30 chars + newline
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC" "exit 0 — trailing newline is stripped before counting"
assert_contains "$OUT" "name: 30/30 chars"
assert_not_contains "$OUT" "OVER LIMIT"
remove_fixture "$T"

# --- #2: single-store listings validate without failing for the absent store ---
it "a Play-only listing passes (even with an unrelated fastlane/metadata/README.md)"
new_tempdir T; cp -R "$APP/fastlane" "$T/"; rm -rf "$T"/fastlane/screenshots "$T"/fastlane/metadata/en-US "$T"/fastlane/metadata/*.txt
printf '# Listing metadata notes\n' > "$T/fastlane/metadata/README.md"
mkdir -p "$T/fastlane/metadata/notes" "$T/fastlane/screenshots/notes"
touch "$T/fastlane/metadata/notes/README.md" "$T/fastlane/screenshots/notes/README.md"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC" "exit 0 for Play-only with README.md"
assert_contains "$OUT" "== Google Play =="
assert_not_contains "$OUT" "== Apple App Store =="
remove_fixture "$T"

it "an Apple-only listing passes (no spurious Play feature-graphic failure)"
new_tempdir T; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"; remove_fixture "$T"/fastlane/metadata/android
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC" "exit 0 for Apple-only"
assert_contains "$OUT" "== Apple App Store =="
assert_not_contains "$OUT" "== Google Play =="
remove_fixture "$T"

# --- #1: iPad requirement is detected for NATIVE iOS (pbxproj), not just Expo ---
it "fails on a native-iOS universal app (TARGETED_DEVICE_FAMILY=2) with no iPad screenshots"
new_tempdir T; cp -R "$APP/fastlane" "$T/"            # NOTE: no app.json → not the Expo path
rm -f "$T"/fastlane/screenshots/en-US/ipad13_*.png
cp -R "$ROOT/tests/fixtures/platforms/flutter/ios/Runner.xcodeproj" "$T/"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "exit 1 — native iPad support detected, iPad shots required"
assert_contains "$OUT" 'no iPad 13" screenshots'
remove_fixture "$T"

# --- store-rule checks driven by tiny synthetic images (tests/helpers.sh) ---
png() { fake_png "$@"; }   # <path> <w> <h> [depth=8] [colortype=2]
apple_only() { new_tempdir T; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"; remove_fixture "$T"/fastlane/metadata/android; }
play_only()  { new_tempdir T; cp -R "$APP/fastlane" "$T/"; remove_fixture "$T"/fastlane/screenshots "$T"/fastlane/metadata/en-US "$T"/fastlane/metadata/*.txt; }
PHONE=fastlane/metadata/android/en-US/images/phoneScreenshots

it "a Face ID large set alone cannot fill the medium upload slot"
apple_only; rm -f "$T"/fastlane/screenshots/en-US/0*.png "$T"/fastlane/screenshots/en-US/medium_01.png
png "$T/fastlane/screenshots/en-US/01_home.png" 1284 2778
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "no iPhone Dynamic Island (medium display) screenshots"
remove_fixture "$T"

it "a Face ID medium set does not fill the Dynamic Island medium slot"
apple_only; rm -f "$T"/fastlane/screenshots/en-US/0*.png "$T"/fastlane/screenshots/en-US/medium_01.png
png "$T/fastlane/screenshots/en-US/01_home.png" 1170 2532
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "no iPhone Dynamic Island (medium display) screenshots"
remove_fixture "$T"

it "an 11\" iPad set does not satisfy the 13\" iPad requirement"
apple_only; rm -f "$T"/fastlane/screenshots/en-US/ipad13_*.png
png "$T/fastlane/screenshots/en-US/ipad11_01.png" 1668 2420
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" 'no iPad 13" screenshots'
remove_fixture "$T"

it "landscape screenshots are recognized"
apple_only; png "$T/fastlane/screenshots/en-US/05_wide.png" 2868 1320
OUT="$(bash "$SUT" "$T" 2>&1)"
assert_not_contains "$OUT" "not a recognized App Store size"
remove_fixture "$T"

it "more than 10 screenshots in one display class fails"
apple_only
for i in 05 06 07 08 09 10 11; do png "$T/fastlane/screenshots/en-US/${i}_x.png" 1320 2868; done
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "11 screenshots (App Store max is 10"
remove_fixture "$T"

it "each screenshot locale is checked on its own"
apple_only; mkdir -p "$T/fastlane/screenshots/de-DE"
png "$T/fastlane/screenshots/de-DE/01_home.png" 1170 2532
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "a locale without a Dynamic Island medium set fails even if en-US has one"
assert_contains "$OUT" "screenshots de-DE:"
remove_fixture "$T"

it "keywords are limited to 100 UTF-8 bytes, not characters"
apple_only
python3 -c "import sys;open(sys.argv[1],'w',encoding='utf-8').write('料'*40)" "$T/fastlane/metadata/en-US/keywords.txt"   # 40 chars, 120 bytes
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "keywords: 120/100 bytes OVER LIMIT"
remove_fixture "$T"

it "a 16-bit-depth Play screenshot fails (24-bit means 8 bits per channel)"
play_only; png "$T/$PHONE/05_deep.png" 1080 1920 16 2
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "05_deep.png: must be 24-bit no-alpha (depth=16"
remove_fixture "$T"

it "Play phone screenshots allow 2.3:1 and reject larger ratios"
play_only; png "$T/$PHONE/05_tall.png" 1000 2300
OUT="$(bash "$SUT" "$T" 2>&1)"; assert_eq 0 "$?"
png "$T/$PHONE/05_tall.png" 1000 2301
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "05_tall.png: aspect"
remove_fixture "$T"

it "a phone listing needs two phone images as well as two overall"
play_only; rm -f "$T/$PHONE"/*.png
mkdir -p "$T/app/src/main"
echo 'plugins { id("com.android.application") }' > "$T/app/build.gradle.kts"
printf '<manifest/>\n' > "$T/app/src/main/AndroidManifest.xml"
png "$T/$PHONE/01_home.png" 1080 1920
png "$T/fastlane/metadata/android/en-US/images/tenInchScreenshots/01_home.png" 1920 1080
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "one phone image falls short of the phone slot minimum"
assert_contains "$OUT" "screenshots across device types: 2"
assert_contains "$OUT" "promotion eligibility"
remove_fixture "$T"

it "a single Play screenshot fails"
play_only; rm -f "$T/$PHONE"/0[2-9]*.png
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "need ≥2"
remove_fixture "$T"

it "a non-PNG file with a .png name fails cleanly instead of crashing"
play_only; printf 'not a png' > "$T/$PHONE/05_bogus.png"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_not_contains "$OUT" "integer expression"
assert_not_contains "$OUT" "Traceback"
remove_fixture "$T"

# --- fastlane supply layout: graphics are files directly in images/ ---
IMG=fastlane/metadata/android/en-US/images

it "the old nested images/featureGraphic/ layout fails (supply never uploads it)"
play_only; mkdir -p "$T/$IMG/featureGraphic"; mv "$T/$IMG/featureGraphic.png" "$T/$IMG/featureGraphic/"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "images/featureGraphic/ is not uploaded by fastlane supply"
remove_fixture "$T"

it "a JPEG feature graphic is accepted"
play_only; rm "$T/$IMG/featureGraphic.png"
fake_jpeg "$T/$IMG/featureGraphic.jpg" 1024 500
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" "Feature graphic 1024x500"
remove_fixture "$T"

it "a missing Play icon fails (it's required)"
play_only; rm "$T/$IMG/icon.png"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "App icon MISSING"
remove_fixture "$T"

it "Wear OS screenshots are validated"
play_only; png "$T/$IMG/wearScreenshots/01.png" 384 384 8 6
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "RGBA wear screenshot fails"
assert_contains "$OUT" "Wear OS screenshots: 1"
remove_fixture "$T"

# --- required copy must be present, non-empty, and URLs must be URLs ---
it "an empty required field fails"
apple_only; : > "$T/fastlane/metadata/en-US/name.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "name: file is empty"
remove_fixture "$T"

it "a missing support URL fails (Apple requires it)"
apple_only; rm "$T/fastlane/metadata/en-US/support_url.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "support_url: REQUIRED file missing"
remove_fixture "$T"

it "a URL field that isn't a URL fails"
apple_only; echo "see our website" > "$T/fastlane/metadata/en-US/privacy_url.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "privacy_url: not a single http(s) URL"
remove_fixture "$T"

it "JPEG screenshots count toward the iPhone set"
apple_only; rm -f "$T"/fastlane/screenshots/en-US/0*.png "$T"/fastlane/screenshots/en-US/medium_01.png
fake_jpeg "$T/fastlane/screenshots/en-US/01_home.jpeg" 1179 2556
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" "iPhone Dynamic Island (medium display) screenshots present (1"
remove_fixture "$T"

# --- iPad detection beyond app.json ---
it "detects supportsTablet in a dynamic app.config.ts"
apple_only; rm "$T/app.json" "$T"/fastlane/screenshots/en-US/ipad13_*.png
printf 'export default { ios: { supportsTablet: true } };\n' > "$T/app.config.ts"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" 'no iPad 13" screenshots'
remove_fixture "$T"

it "LK_SUPPORTS_IPAD=0 overrides detection"
apple_only; rm -f "$T"/fastlane/screenshots/en-US/ipad13_*.png
OUT="$(LK_SUPPORTS_IPAD=0 bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_not_contains "$OUT" "iPad"
remove_fixture "$T"

it "an upper-case extension fails (fastlane won't upload it on Linux)"
apple_only; mv "$T/fastlane/screenshots/en-US/01_recipes.png" "$T/fastlane/screenshots/en-US/01_recipes.PNG"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "01_recipes.PNG: rename with a lower-case extension"
remove_fixture "$T"

it "an unrecognized App Store screenshot size fails"
apple_only; png "$T/fastlane/screenshots/en-US/09_odd.png" 100 100
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "09_odd.png: 100x100 is not an App Store screenshot size"
remove_fixture "$T"

it "an RGB PNG with tRNS transparency fails the no-alpha check"
apple_only
fake_png "$T/fastlane/screenshots/en-US/05_trns.png" 1320 2868 8 2 trns
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "05_trns.png: must be RGB no-alpha (colortype=2+tRNS)"
remove_fixture "$T"

it "a screenshot locale without a metadata folder still needs its copy"
apple_only; mkdir -p "$T/fastlane/screenshots/fr-FR"
cp "$T"/fastlane/screenshots/en-US/*.png "$T/fastlane/screenshots/fr-FR/"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "locale fr-FR:"
assert_contains "$OUT" "name: REQUIRED file missing"
remove_fixture "$T"

it "fields missing from a locale fall back to metadata/default/"
apple_only; mkdir -p "$T/fastlane/metadata/default"
mv "$T/fastlane/metadata/en-US/support_url.txt" "$T/fastlane/metadata/en-US/privacy_url.txt" "$T/fastlane/metadata/default/"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" "support_url: https://"
remove_fixture "$T"

it "a bare https:// URL fails"
apple_only; echo "https://" > "$T/fastlane/metadata/en-US/support_url.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "support_url: not a single http(s) URL"
remove_fixture "$T"

it "a non-UTF-8 copy file fails instead of being skipped"
apple_only; printf 'Caf\xe9\n' > "$T/fastlane/metadata/en-US/subtitle.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "subtitle: not valid UTF-8"
assert_contains "$OUT" "name: 23/30"   # other fields are still checked
remove_fixture "$T"

it "a JPEG Play icon fails (Play requires PNG)"
play_only; rm "$T/$IMG/icon.png"
fake_jpeg "$T/$IMG/icon.jpg" 512 512
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "icon must be a PNG"
remove_fixture "$T"

it "LK_SUPPORTS_IPHONE=0 allows an iPad-only listing"
apple_only; rm -f "$T"/fastlane/screenshots/en-US/0*.png "$T"/fastlane/screenshots/en-US/medium_01.png
OUT="$(LK_SUPPORTS_IPHONE=0 bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
remove_fixture "$T"

it "promotion eligibility needs 9:16 or 16:9, not just 1080px"
play_only; rm -f "$T/$PHONE"/*.png
for i in 1 2 3 4; do png "$T/$PHONE/0${i}.png" 1080 2160; done
OUT="$(bash "$SUT" "$T" 2>&1)"
assert_contains "$OUT" "only 0 screenshot(s)" "1080x2160 (1:2) doesn't count"
rm -f "$T/$PHONE"/*.png
for i in 1 2 3 4; do png "$T/$PHONE/0${i}.png" 1080 1920; done
OUT="$(bash "$SUT" "$T" 2>&1)"
assert_not_contains "$OUT" "promotion eligibility" "four 1080x1920 shots qualify"
remove_fixture "$T"

it "a truncated PNG (header but no image data) fails"
apple_only; head -c 33 "$T/fastlane/screenshots/en-US/01_recipes.png" > "$T/x" && mv "$T/x" "$T/fastlane/screenshots/en-US/01_recipes.png"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "01_recipes.png: 0x0 is not an App Store screenshot size"
remove_fixture "$T"

it "a 41-byte truncated PNG (IHDR + IDAT chunk header) fails"
apple_only
python3 -c 'import struct,sys,zlib
ihdr=struct.pack(">IIBBBBB",1206,2622,8,2,0,0,0)
open(sys.argv[1],"wb").write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"+ihdr+struct.pack(">I",zlib.crc32(b"IHDR"+ihdr))+b"\x00\x00\x00\x01IDAT")
' "$T/fastlane/screenshots/en-US/medium_01.png"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "medium_01.png: 0x0 is not an App Store screenshot size"
rm -rf "$T"

it "a JPEG without SOS or EOI fails validation"
play_only; rm "$T/$IMG/featureGraphic.png"
python3 -c 'import struct,sys
sof=struct.pack(">BHHB",8,500,1024,3)+b"\x01\x22\x00\x02\x11\x01\x03\x11\x01"
open(sys.argv[1],"wb").write(b"\xff\xd8\xff\xc0"+struct.pack(">H",len(sof)+2)+sof+b"\xff\xd9")
' "$T/$IMG/featureGraphic.jpg"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "Feature graphic must be 1024x500"
rm -rf "$T"

it "a JPEG saved as icon.png fails"
play_only; fake_jpeg "$T/$IMG/icon.png" 512 512
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "icon must be a PNG"
remove_fixture "$T"

it "a Play tree with no locale folders fails"
new_tempdir T; mkdir -p "$T/fastlane/metadata/android"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "has no locale folders"
remove_fixture "$T"

it "an App Store name under 2 characters fails"
apple_only; printf 'R\n' > "$T/fastlane/metadata/en-US/name.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "under the 2-chars minimum"
remove_fixture "$T"

it "Play changelogs are limited to 500 characters"
play_only; mkdir -p "$T/fastlane/metadata/android/en-US/changelogs"
printf 'x%.0s' $(seq 1 501) > "$T/fastlane/metadata/android/en-US/changelogs/42.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "changelogs/42: 501/500 chars OVER LIMIT"
remove_fixture "$T"

it "hidden folders (metadata/.backup) are not treated as locales"
apple_only; mkdir -p "$T/fastlane/metadata/.backup"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_not_contains "$OUT" "locale .backup"
remove_fixture "$T"


it "checks public .listing-kit files while excluding local settings"
mkdir -p "$APP/.listing-kit/config"
for file in local.json config/secrets.local; do
  echo 'AKIAIOSFODNN7EXAMPLE' > "$APP/.listing-kit/$file"
done
OUT="$(bash "$SUT" "$APP" 2>&1)"; RC=$?
assert_eq 0 "$RC"
echo 'AKIAIOSFODNN7EXAMPLE' > "$APP/.listing-kit/config/notes"
OUT="$(bash "$SUT" "$APP" 2>&1)"; RC=$?
assert_ne 0 "$RC"
assert_contains "$OUT" '.listing-kit/config/notes'

it "fails with exit 1 when pointed at a directory with no listing at all"
for sub in "" "fastlane" "fastlane/metadata"; do
  new_tempdir T; [ -n "$sub" ] && mkdir -p "$T/$sub"
  OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
  assert_eq 1 "$RC" "empty listing ($sub) exits 1"
  assert_contains "$OUT" "no App Store or Google Play listing was found under $T"
  assert_not_contains "$OUT" "LISTING VALID"
  rm -rf "$T"
done

it "detects a tree with only Apple app-level files as an Apple listing"
new_tempdir T; mkdir -p "$T/fastlane/metadata"
printf '2026 Example Inc.\n' > "$T/fastlane/metadata/copyright.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "incomplete Apple listing exits 1"
assert_contains "$OUT" "== Apple App Store =="
assert_contains "$OUT" "copyright: set"
assert_not_contains "$OUT" "no App Store or Google Play listing was found"
rm -rf "$T"

it "detects a tree with only metadata/default/ as an Apple listing and validates its copy"
new_tempdir T; mkdir -p "$T/fastlane/metadata/default"
cp "$APP/fastlane/metadata/en-US/"*.txt "$T/fastlane/metadata/default/"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "default copy without screenshots exits 1"
assert_contains "$OUT" "== Apple App Store =="
assert_contains "$OUT" "name: 23/30 chars"
assert_not_contains "$OUT" "no App Store or Google Play listing was found"
rm -rf "$T"

it "counts failures of python helpers (locale discovery and imginfo) as validation failures"
new_tempdir SHIM_ROOT
SHIM="$SHIM_ROOT/scripts"
mkdir -p "$SHIM"
cp -R "$SKILL_DIR/specs" "$SHIM_ROOT/"
cp -R "$SCRIPTS/validate" "$SCRIPTS/lib" "$SHIM/"
printf '\ndef apple_locales(*args, **kwargs): raise RuntimeError("apple_assets.py failed")\n' >> "$SHIM/lib/apple_assets.py"
apple_only
OUT="$(bash "$SHIM/validate/validate-listing.sh" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "apple_assets.py --locales failure exits 1"
assert_contains "$OUT" "RuntimeError: apple_assets.py failed"
assert_not_contains "$OUT" "LISTING VALID"
rm -rf "$T"
# 2. listing.py failing on play-locales
cp "$SCRIPTS/lib/apple_assets.py" "$SHIM/lib/apple_assets.py"
printf '\ndef play_locales(fl): raise RuntimeError("listing.py failed")\n' >> "$SHIM/lib/listing.py"
play_only
OUT="$(bash "$SHIM/validate/validate-listing.sh" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "listing.py play-locales failure exits 1"
assert_contains "$OUT" "listing.py"
assert_not_contains "$OUT" "LISTING VALID"
rm -rf "$T"
# 3. imginfo.py failing on screenshots/graphics (even when device screenshot minimums are overridden)
cp "$SCRIPTS/lib/listing.py" "$SHIM/lib/listing.py"
printf '\ndef validate_many(paths, accept=None): raise RuntimeError("imginfo.py failed")\n' >> "$SHIM/lib/imginfo.py"
apple_only
OUT="$(LK_SUPPORTS_IPHONE=0 LK_SUPPORTS_IPAD=0 bash "$SHIM/validate/validate-listing.sh" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "imginfo.py failure on Apple screenshots exits 1"
assert_contains "$OUT" "imginfo.py"
assert_not_contains "$OUT" "all screenshots are RGB/no-alpha"
rm -rf "$T"
play_only
OUT="$(bash "$SHIM/validate/validate-listing.sh" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "imginfo.py failure on Play graphics exits 1"
assert_contains "$OUT" "imginfo.py"
assert_not_contains "$OUT" "integer expression"
remove_fixture "$T" "$SHIM_ROOT"

it "warns once when ImageMagick is unavailable and fails on bad full decode of any screenshot or graphic"
new_tempdir NOIM_BIN
for cmd in bash sh python3 dirname basename grep sort uniq head od tr awk cat mktemp rm; do
  p="$(command -v "$cmd" 2>/dev/null || true)"
  [ -n "$p" ] && ln -s "$p" "$NOIM_BIN/$cmd"
done
new_tempdir T; cp -R "$APP/fastlane" "$APP/app.json" "$T/"
fake_png "$T/store-assets/apple/en-US/header-16x9.png" 5244 2950
fake_png "$T/fastlane/metadata/android/en-US/images/tvBanner.png" 1280 720
OUT="$(PATH="$NOIM_BIN" "$BASH_BIN" "$SUT" "$T" 2>&1)"; RC=$?
assert_not_contains "$OUT" "command not found" "restricted PATH supplies every validator command"
assert_eq 0 "$RC" "structural-only validation passes with a warning when IM is absent"
assert_contains "$OUT" "structurally only"
WARN_LINES="$(printf '%s\n' "$OUT" | grep -c 'structurally only' || true)"
assert_eq 1 "$WARN_LINES" "prints exactly ONE structural-only warning across all images"

# PATH stub reporting bad decode for each asset category
for bad_target in "medium_01.png" "phoneScreenshots/01_recipes.png" "featureGraphic.png" "icon.png" "tvBanner.png"; do
  new_stubdir
  cat > "$STUB_BIN/magick" <<EOF
#!/usr/bin/env bash
case "\$*" in *"$bad_target"*) exit 1;; *) exit 0;; esac
EOF
  chmod +x "$STUB_BIN/magick"
  OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" "$T" 2>&1)"; RC=$?
  assert_eq 1 "$RC" "bad decode of $bad_target fails validation"
  assert_contains "$OUT" "${bad_target##*/}"
done
rm -rf "$T"

if command -v magick >/dev/null 2>&1 || command -v convert >/dev/null 2>&1; then
  it "real ImageMagick: rejects a Play feature graphic with valid header/tables but corrupt scan"
  play_only; rm "$T/$IMG/featureGraphic.png"
  python3 - "$T/$IMG/featureGraphic.jpg" <<'PY'
import struct, sys
def seg(m, d): return b"\xff" + bytes([m]) + struct.pack(">H", len(d) + 2) + d
dqt = seg(0xDB, b"\x00" + b"\x10" * 64)
sof = seg(0xC0, struct.pack(">BHHB", 8, 500, 1024, 3) + b"\x01\x22\x00\x02\x11\x00\x03\x11\x00")
dht = seg(0xC4, b"\x00\x01" + b"\x00" * 15 + b"\x00") + seg(0xC4, b"\x10\x01" + b"\x00" * 15 + b"\x00")
sos = seg(0xDA, b"\x03\x01\x00\x02\x00\x03\x00\x00\x3f\x00")
open(sys.argv[1], "wb").write(b"\xff\xd8" + dqt + sof + dht + sos + b"\x01\xff\xd9")
PY
  OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
  assert_eq 1 "$RC" "real IM rejects corrupt scan in 1024x500 featureGraphic.jpg"
  assert_not_contains "$OUT" "✓ Feature graphic 1024x500"
  rm -rf "$T"
else
  it "real decoder rejects invalid feature graphic pixels"
  skip "no ImageMagick"
fi

it "rejects oversized PNG/JPEG and malformed assets before starting ImageMagick"
new_tempdir T
fake_png "$T/$PHONE/over.png" 8001 8000 1 0
fake_jpeg "$T/$PHONE/over.jpg" 8001 8000
fake_jpeg "$T/store-assets/apple/en-US/header.jpg" 8001 8000
printf garbage > "$T/$PHONE/damaged.png"
new_stubdir; stub magick
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_eq "" "$(stub_log)" "no decoder invoked for structurally rejected files"
rm -rf "$T"

it "checks the TV banner and all duplicate graphic candidates"
play_only
printf broken > "$T/$IMG/tvBanner.png"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "a corrupt optional TV banner fails validation"
assert_contains "$OUT" "tvBanner.png"
fake_png "$T/$IMG/tvBanner.png" 1280 720
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC" "valid TV banner passes"
assert_contains "$OUT" "TV banner 1280x720"
fake_png "$T/$IMG/tvBanner.png" 1280 720 8 6
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "RGBA TV banner fails Play 24-bit no-alpha rule"
assert_contains "$OUT" "TV banner must be 1280x720"
rm -f "$T/$IMG/tvBanner.png"; fake_png "$T/$IMG/tvBanner.png" 1280 720 8 0
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "a grayscale PNG banner is not a 24-bit PNG"
. "$SCRIPTS/lib/imagemagick.sh"
if im_resolve convert; then
  rm -f "$T/$IMG/tvBanner.png"
  "${IM[@]}" -size 1280x720 gradient: -colorspace Gray "$T/$IMG/tvBanner.jpg"
  OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
  assert_eq 0 "$RC" "a grayscale JPEG banner is a valid JPEG and passes"
  rm -f "$T/$IMG/tvBanner.jpg"
else
  it "TV banner JPEG validation"
  skip "no ImageMagick"
fi
rm -f "$T/$IMG/tvBanner.png"
fake_jpeg "$T/$IMG/featureGraphic.jpg" 1024 500
printf broken > "$T/$IMG/featureGraphic.png"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "duplicate featureGraphic"
assert_contains "$OUT" "featureGraphic.png: image failed"
assert_not_contains "$OUT" "✓ Feature graphic" "ambiguous duplicate graphic does not report pass"
rm -rf "$T"

it "rejects a two-frame APNG screenshot with a damaged second frame with a clear acTL reason"
apple_only
python3 - "$T/fastlane/screenshots/en-US/05_apng.png" <<'PY'
import struct, sys, zlib
def chunk(k, d): return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))
w, h = 1206, 2622
ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
comp = zlib.compressobj(1)
row = b"\x00" * (1 + w * 3)
z = bytearray()
for _ in range(h): z.extend(comp.compress(row))
z.extend(comp.flush())
actl = chunk(b"acTL", struct.pack(">II", 2, 0))
fctl0 = chunk(b"fcTL", struct.pack(">IIIIIHHBB", 0, w, h, 0, 0, 1, 10, 0, 0))
fctl1 = chunk(b"fcTL", struct.pack(">IIIIIHHBB", 1, w, h, 0, 0, 1, 10, 0, 0))
fdat_bad = chunk(b"fdAT", struct.pack(">I", 2) + b"damaged-second-frame-data")
open(sys.argv[1], "wb").write(b"\x89PNG\r\n\x1a\n" + ihdr + actl + fctl0 + chunk(b"IDAT", bytes(z)) + fctl1 + fdat_bad + chunk(b"IEND", b""))
PY
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "APNG screenshot fails validation"
assert_contains "$OUT" "05_apng.png: animated PNG (acTL)"
assert_not_contains "$OUT" "05_apng.png: 0x0" "does not emit redundant 0x0 size error after acTL reason"
rm -rf "$T"

it "reports the decoder's resource limit as a warning on each blocked asset"
play_only
fake_png "$T/store-assets/apple/en-US/header.png" 3840 1646
cp -R "$APP/fastlane/screenshots" "$T/fastlane/"
cp -R "$APP/fastlane/metadata/en-US" "$APP/fastlane/metadata/"*.txt "$T/fastlane/metadata/"
new_stubdir
cat > "$STUB_BIN/magick" <<'LIMIT'
#!/bin/sh
echo 'Image width exceeds user limit in IHDR' >&2
exit 1
LIMIT
chmod +x "$STUB_BIN/magick"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC" "policy warnings allow a structurally valid listing"
for asset in header.png medium_01.png icon.png featureGraphic.png 01_recipes.png; do
  warnings="$(printf '%s\n' "$OUT" | grep ' ! ' || true)"
  assert_contains "$warnings" "$asset: could not decode: Image width exceeds user limit"
done
rm -rf "$T"

summary
