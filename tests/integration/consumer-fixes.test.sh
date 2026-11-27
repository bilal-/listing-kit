#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
F="$ROOT/tests/fixtures/platforms"
detect(){ python3 -I -B "$SCRIPTS/lib/detect.py" "$1"; }
it "only shipping application settings determine platform support"
assert_contains "$(detect "$F/flutter")" $'hasMacApp\tunknown'
assert_contains "$(detect "$F/iphone")" $'supportsIpad\tno'
assert_contains "$(detect "$F/wear")" $'supportsAndroidPhone\tno'
assert_contains "$(detect "$F/expo")" $'hasWearOs\tunknown'
new_tempdir T
cp -R "$F/flutter/." "$T/"
mac="$T/macos/Runner.xcodeproj/project.pbxproj"
sed 's/SDKROOT = macosx;/SDKROOT = macosx; TARGETED_DEVICE_FAMILY = "1,2";/' "$mac" > "$T/mac-settings"
mv "$T/mac-settings" "$mac"
assert_contains "$(detect "$T")" $'hasMacApp\tunknown'
new_tempdir T
cp -R "$F/iphone/App.xcodeproj" "$T/"
sed 's/buildConfigurationList = LApp/buildConfigurationList = Missing/' "$F/iphone/App.xcodeproj/project.pbxproj" > "$T/App.xcodeproj/project.pbxproj"
assert_contains "$(detect "$T")" $'supportsIphone\tunknown'
assert_contains "$(detect "$T")" $'hasWatchApp\tunknown'
new_tempdir T
cp -R "$ROOT/examples/expo-recipe-box/fastlane" "$T/"
remove_fixture "$T/fastlane/screenshots"
validate(){ bash "$SCRIPTS/validate/validate-listing.sh" "$T" "$@"; }
it "empty Apple screenshots enforce the rules minimum and name the primary-condition fix"
OUT="$(validate)"
assert_contains "$OUT" "across primary device families (need ≥1)"
assert_contains "$OUT" "LK_SUPPORTS_IPHONE"
assert_contains "$OUT" "platforms"
it "invalid listing plan produces a failure identifying the error"
mkdir -p "$T/.listing-kit"
echo '{' > "$T/.listing-kit/listing.json"
OUT="$(validate)"
assert_contains "$OUT" "platform overrides ignored"
assert_contains "$OUT" "Expecting property name"
remove_fixture "$T/.listing-kit/listing.json"
it "all consumers reject unknown manual folders and sizes outside the assigned slot"
for dir in vision-pro bogus; do
  file="$T/store-assets/apple/en-US/screenshots/$dir/wrong.png"
  fake_png "$file" 1206 2622
  case "$dir" in vision-pro) message="does not fit Apple slot vision-pro";; bogus) message="unknown apple slot bogus";; esac
  assert_contains "$(validate)" "$message"
  OUT="$(bash "$SCRIPTS/package/build-review.sh" "$T" 2>&1)"; rc=$?
  assert_eq 1 "$rc"
  assert_contains "$OUT" "$message"
  assert_contains "$(python3 -B "$SCRIPTS/handoff/handoff.py" "$T" 2>&1)" "$message"
  remove_fixture "${file%/*}"
done
it "metadata-only languages can reuse platform-root captures, and manual shared sizes stay assigned"
fake_png "$T/fastlane/screenshots/appleTV/en-US/tv.png" 1920 1080
fake_png "$T/fastlane/screenshots/iMessage/en-US/message.png" 1206 2622
fake_png "$T/store-assets/apple/en-US/screenshots/ipad-12-9/old.png" 2048 2732
cp "$F/expo/app.json" "$T/"
OUT="$(validate)"
assert_contains "$OUT" "Apple TV screenshots present"
assert_contains "$OUT" 'no iPad 13" screenshots'
it "the Play validator, review and hand upload reject an invalid manual size"
bad_play="$T/store-assets/play/en-US/screenshots/xr/off-size.png"
fake_png "$bad_play" 1206 2622
assert_contains "$(validate)" "does not fit Play slot xr"
OUT="$(bash "$SCRIPTS/package/build-review.sh" "$T" 2>&1)"; assert_eq 1 "$?"
assert_contains "$OUT" "does not fit Play slot xr"
assert_contains "$(python3 -B "$SCRIPTS/handoff/handoff.py" "$T" 2>&1)" "does not fit Play slot xr"
remove_fixture "$bad_play"
it "only active framed captures count"
fake_png "$T/fastlane/screenshots/en-US/phone.png" 1206 2622
fake_png "$T/fastlane/screenshots/en-US/pad_framed.png" 2064 2752
remove_fixture "$T/fastlane/screenshots/iMessage"
OUT="$(validate)"
assert_contains "$OUT" "no iPhone Dynamic Island (medium display) screenshots"
it "the App Store and iMessage each have their own display class limit"
for i in 1 2 3 4 5 6; do
  fake_png "$T/fastlane/screenshots/en-US/${i}_framed.png" 1206 2622
  fake_png "$T/fastlane/screenshots/iMessage/en-US/$i.png" 1206 2622
done
OUT="$(validate)"
assert_not_contains "$OUT" "12 screenshots"
assert_contains "$OUT" "iMessage iPhone Dynamic Island (medium display) screenshots present (6)"
it "default transcript limits warnings and verbose retains evidence"
new_tempdir EX
cp -R "$ROOT/examples/expo-recipe-box"/{fastlane,app.json} "$EX/"
OUT="$(bash "$SCRIPTS/validate/validate-listing.sh" "$EX")"
assert_contains "$OUT" "LISTING VALID"
assert_not_contains "$OUT" "optional, absent"
assert_not_contains "$OUT" "isUpdate=unknown"
warnings="$(echo "$OUT" | sed -nE 's/.*· ([0-9]+) warnings.*/\1/p')"
if [ "${warnings:-99}" -le 3 ]; then pass; else fail "expected at most three warnings, got $warnings"; fi
assert_contains "$(validate --verbose)" "isUpdate=unknown"
it "review forwards deadline and SDK"
bash "$SCRIPTS/package/build-review.sh" "$T" --as-of 2027-04-01 --ios-sdk 27.1 >/dev/null
assert_contains "$(cat "$T/listing-review.html")" "required since 2027-04-01"
summary
