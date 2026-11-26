#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir T
cp -R "$ROOT/examples/expo-recipe-box/fastlane" "$ROOT/examples/expo-recipe-box/app.json" "$T/"
fake_png "$T/fastlane/screenshots/en-US/medium.png" 1206 2622
run(){ bash "$SCRIPTS/validate/validate-listing.sh" "$T" "$@" 2>&1; }
it "dated Duo requirements respect the warning window, start date and SDK exception"
OUT="$(run --as-of 2027-01-01 --ios-sdk 27.1)"; assert_eq 0 "$?"
assert_contains "$OUT" "required from 2027-04-01 (90 days)"
OUT="$(run --as-of 2027-04-01 --ios-sdk 27.1)"; assert_eq 1 "$?"
assert_contains "$OUT" "required since 2027-04-01"
assert_contains "$OUT" "store rules verified on 2026-11-26"
assert_contains "$OUT" "126 days old"
OUT="$(run --as-of 2027-04-01 --ios-sdk 27.0)"; assert_eq 0 "$?"
it "unknown SDK at the deadline warns and shows the missing evidence"
OUT="$(run --as-of 2027-04-01)"; assert_eq 0 "$?"
assert_contains "$OUT" "--ios-sdk X.Y"
it "a detected TV app requires its own screenshots and banner; Wear validates its own shape"
mkdir -p "$T/android/src/main"
printf '%s\n' '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application><activity><intent-filter><category android:name="android.intent.category.LEANBACK_LAUNCHER"/></intent-filter></activity></application></manifest>' > "$T/android/src/main/AndroidManifest.xml"
fake_png "$T/fastlane/metadata/android/en-US/images/wearScreenshots/watch.png" 383 384
OUT="$(run)"; assert_eq 1 "$?"
assert_contains "$OUT" "TV banner MISSING"
assert_contains "$OUT" "Android TV screenshots"
assert_contains "$OUT" "watch.png"
assert_contains "$OUT" "384"
assert_contains "$OUT" "1:1"
it "both Duo slots have their own cap and Watch framing is an informational note"
shots="$T/fastlane/screenshots/en-US"
fake_png "$shots/outer-1.png" 1398 2034
fake_png "$shots/inner-1.png" 2853 2007
fake_png "$shots/watch.png" 410 502
for i in 2 3 4 5 6; do
  ln "$shots/outer-1.png" "$shots/outer-$i.png"
  ln "$shots/inner-1.png" "$shots/inner-$i.png"
done
rm "$T/android/src/main/AndroidManifest.xml" "$T/fastlane/metadata/android/en-US/images/wearScreenshots/watch.png"
OUT="$(run)"; assert_eq 0 "$?"
assert_contains "$OUT" "iPhone Duo (outer display) screenshots present (6)"
assert_contains "$OUT" "iPhone Duo (inner display) screenshots present (6)"
assert_contains "$OUT" "Apple Watch: framing forbidden"
for i in 7 8 9 10 11; do ln "$shots/outer-1.png" "$shots/outer-$i.png"; done
OUT="$(run)"; assert_eq 1 "$?"
assert_contains "$OUT" "iPhone Duo (outer display): 11 screenshots"
rm "$shots/outer-11.png"
it "large-screen promotion bounds are independent of the phone upload bounds"
tablet="$T/fastlane/metadata/android/en-US/images/tenInchScreenshots"
fake_png "$tablet/01.png" 7680 4320
for i in 02 03 04; do ln "$tablet/01.png" "$tablet/$i.png"; done
OUT="$(run)"; assert_eq 0 "$?"
assert_not_contains "$OUT" "10-inch tablet: only"
assert_not_contains "$OUT" "01.png: side outside"
remove_fixture "$tablet"
it "the phone byte cap is inclusive"
phone="$T/fastlane/metadata/android/en-US/images/phoneScreenshots/01_recipes.png"
pad_png(){ python3 -I -B - "$phone" "$1" <<'PYTEST'
import struct, sys, zlib
from pathlib import Path
path = Path(sys.argv[1])
data = path.read_bytes()
chunk = b'npAD' + bytes(int(sys.argv[2]) - len(data) - 12)
path.write_bytes(data[:-12] + struct.pack(">I", len(chunk)-4) + chunk
                 + struct.pack(">I", zlib.crc32(chunk)) + data[-12:])
PYTEST
}
cp "$phone" "$T/source.png"
pad_png 8388608
OUT="$(run)"; assert_eq 0 "$?"
assert_not_contains "$OUT" "exceeds 8388608 bytes"
cp "$T/source.png" "$phone"; pad_png 8388609
OUT="$(run)"; assert_eq 1 "$?"
assert_contains "$OUT" "01_recipes.png: exceeds 8388608 bytes"
summary
