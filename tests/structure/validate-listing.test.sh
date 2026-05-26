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

summary
