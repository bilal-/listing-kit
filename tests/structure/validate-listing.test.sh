#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/validate/validate-listing.sh"
APP="$ROOT/examples/expo-recipe-box"

it "the committed example listing passes validation (both stores, exit 0)"
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

# --- store-rule checks driven by synthetic PNG headers (imginfo reads the header only) ---
# png <path> <w> <h> [depth=8] [colortype=2]
png() { mkdir -p "$(dirname "$1")"; python3 - "$@" <<'PY'
import struct, sys, zlib
p, w, h = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
depth = int(sys.argv[4]) if len(sys.argv) > 4 else 8
ct = int(sys.argv[5]) if len(sys.argv) > 5 else 2
ihdr = struct.pack(">IIBBBBB", w, h, depth, ct, 0, 0, 0)
open(p, "wb").write(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr
                    + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr)))
PY
}
apple_only() { T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"; rm -rf "$T"/fastlane/metadata/android; }
play_only()  { T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"; rm -rf "$T"/fastlane/screenshots "$T"/fastlane/metadata/en-US; }
PHONE=fastlane/metadata/android/en-US/images/phoneScreenshots

it "a 6.5\" iPhone set alone satisfies the iPhone requirement"
apple_only; rm -f "$T"/fastlane/screenshots/en-US/0*.png
png "$T/fastlane/screenshots/en-US/01_home.png" 1284 2778
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" "iPhone screenshots present (1 at"
rm -rf "$T"

it "a 6.1\" set alone fails (6.9\" or 6.5\" is required)"
apple_only; rm -f "$T"/fastlane/screenshots/en-US/0*.png
png "$T/fastlane/screenshots/en-US/01_home.png" 1170 2532
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "no 6.9\" or 6.5\" iPhone screenshots"
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
assert_eq 1 "$RC" "a locale without a 6.9\"/6.5\" set fails even if en-US has one"
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

it "a JPEG feature graphic with an upper-case extension is accepted"
play_only; rm "$T/$IMG/featureGraphic.png"
python3 - "$T/$IMG/featureGraphic.JPG" <<'PY'
import struct, sys
# Minimal JPEG header: SOI + SOF0 (8-bit, 500x1024, 3 components).
sof = struct.pack(">BHHB", 8, 500, 1024, 3) + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01"
open(sys.argv[1], "wb").write(b"\xff\xd8\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof + b"\xff\xd9")
PY
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

it "JPEG screenshots with upper-case extensions count toward the iPhone set"
apple_only; rm -f "$T"/fastlane/screenshots/en-US/0*.png
python3 - "$T/fastlane/screenshots/en-US/01_home.JPEG" <<'PY'
import struct, sys
sof = struct.pack(">BHHB", 8, 2868, 1320, 3) + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01"
open(sys.argv[1], "wb").write(b"\xff\xd8\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof + b"\xff\xd9")
PY
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

summary
