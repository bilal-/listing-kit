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
rm -f "$T"/fastlane/metadata/android/en-US/images/featureGraphic/featureGraphic.png
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

summary
