#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
SUT="$SCRIPTS/validate/validate-listing.sh"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
cp -R "$ROOT/examples/expo-recipe-box/fastlane" "$ROOT/examples/expo-recipe-box/app.json" "$T/"
SHOTS="$T/fastlane/screenshots/en-US"
HEADERS="$T/store-assets/apple/en-US"
mkdir -p "$T/.listing-kit" "$HEADERS"

it "large screenshots do not satisfy the required medium slot"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" 'no iPhone Dynamic Island (medium display) screenshots'

it "native medium dimensions satisfy the required slot"
fake_png "$SHOTS/medium.png" 1206 2622
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" 'no asset-plan.json'

it "a planned but missing Duo set fails, despite other valid iPhone sets"
cat > "$T/.listing-kit/asset-plan.json" <<'JSON'
{"apple":{"en-US":{"screenshots":{"iPhone Dynamic Island (medium display)":1,"iPhone Duo":2},"headers":["header-16x9.png","header-21x9.png"]}}}
JSON
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" 'iPhone Duo: 0 of 2 screenshots'
assert_contains "$OUT" 'header-16x9.png: MISSING'

it "both Duo displays and both header sizes validate"
fake_png "$SHOTS/duo-outer.png" 1398 2034
fake_png "$SHOTS/duo-inner.png" 2853 2007
fake_png "$HEADERS/header-16x9.png" 5244 2950
fake_png "$HEADERS/header-21x9.png" 3840 1646
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" 'iPhone Duo: 2 of 2 screenshots'
assert_contains "$OUT" '5244x2950 RGB/no-alpha'

it "review keeps headers separate from screenshots and labels the upload slots"
bash "$SCRIPTS/package/build-review.sh" "$T" >/dev/null
PAGE="$(cat "$T/listing-review.html")"
assert_contains "$PAGE" 'Header Asset (manual console upload)'
assert_contains "$PAGE" 'store-assets/apple/en-US/header-16x9.png'
assert_contains "$PAGE" '<div class="dc">iPhone Dynamic Island (medium display)'
assert_contains "$PAGE" '<div class="dc">iPhone Duo'

it "review includes a locale that only has header artwork"
fake_png "$T/store-assets/apple/fr-FR/header.png" 3840 1646
bash "$SCRIPTS/package/build-review.sh" "$T" >/dev/null
assert_contains "$(cat "$T/listing-review.html")" 'store-assets/apple/fr-FR/header.png'
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "header-only locale needs required store copy"
assert_contains "$OUT" 'locale fr-FR:'
assert_contains "$OUT" 'name: REQUIRED file missing'
# Complete the locale before exercising unrelated header format checks below.
cp -R "$T/fastlane/metadata/en-US" "$T/fastlane/metadata/fr-FR"

it "a plan-only locale needs required store copy"
printf '%s\n' '{"apple":{"de-DE":{"deferredScreenshots":{"iPhone Duo":"No runtime"}}}}' > "$T/.listing-kit/asset-plan.json"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" 'locale de-DE:'
assert_contains "$OUT" 'name: REQUIRED file missing'
# Restore the approved plan used by the remaining asset cases.
printf '%s\n' '{"apple":{"en-US":{"screenshots":{"iPhone Dynamic Island (medium display)":1,"iPhone Duo":2},"headers":["header-16x9.png","header-21x9.png"]}}}' > "$T/.listing-kit/asset-plan.json"

it "transparent, deep-color and wrong-size headers fail"
for spec in '5244 2950 8 6' '5244 2950 16 2' '1024 500 8 2'; do
  fake_png "$HEADERS/header-16x9.png" $spec
  OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
  assert_eq 1 "$RC" "reject header $spec"
done
fake_png "$HEADERS/header-16x9.png" 5244 2950 8 2 trns
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC" "RGB with tRNS is still transparent"

it "a JPEG disguised as the PNG-only header is rejected"
fake_jpeg "$HEADERS/header-16x9.png" 5244 2950
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
fake_png "$HEADERS/header-16x9.png" 5244 2950
fake_jpeg "$HEADERS/alternate.jpg" 3840 1646
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC" "21:9 JPEG is accepted"

it "a malformed or misspelled plan fails rather than silently skipping coverage"
for plan in '{' '{"aple":{}}' '{"apple":{"en-US":{"screenshots":{"iPhone mystery":5}}}}' '{"apple":{"en-US":{"headers":["../../outside.png"]}}}' '{"apple":{"en-US":{"screenshots":{"iPhone Duo":true}}}}'; do
  printf '%s\n' "$plan" > "$T/.listing-kit/asset-plan.json"
  OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
  assert_eq 1 "$RC"
  assert_contains "$OUT" 'asset-plan.json:'
done

it "a missing locale is not satisfied by another locale's screenshots"
printf '%s\n' '{"apple":{"de-DE":{"screenshots":{"iPhone Duo":1}}}}' > "$T/.listing-kit/asset-plan.json"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" 'planned de-DE/iPhone Duo: 0 of 1 screenshots'
it "deferred Duo warns without failing the remaining listing"
cat > "$T/.listing-kit/asset-plan.json" <<'JSON'
{"apple":{"en-US":{"screenshots":{"iPhone Dynamic Island (medium display)":1},"headers":["header-16x9.png"],"deferredScreenshots":{"iPhone Duo":"Xcode 27.1 & runtime unavailable <check>"}}}}
JSON
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" 'deferred en-US/iPhone Duo:'
bash "$SCRIPTS/package/build-review.sh" "$T" >/dev/null 2>&1
PAGE="$(cat "$T/listing-review.html")"
assert_contains "$PAGE" 'Deferred screenshot targets'
assert_contains "$PAGE" 'iPhone Duo — deferred'
assert_contains "$PAGE" 'Xcode 27.1 &amp; runtime unavailable &lt;check&gt;'
assert_contains "$PAGE" '<div class="dc">iPhone Dynamic Island (medium display)'
assert_contains "$PAGE" 'Header Asset (manual console upload)'
assert_not_contains "$PAGE" 'src="fastlane/screenshots/en-US/duo-outer.png"'
assert_file "$SHOTS/duo-outer.png" "deferral preserves existing assets on disk"

it "an active and deferred target conflict instead of silently skipping it"
printf '%s\n' '{"apple":{"en-US":{"screenshots":{"iPhone Duo":2},"deferredScreenshots":{"iPhone Duo":"No runtime"}}}}' > "$T/.listing-kit/asset-plan.json"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" 'both active and deferred'

it "a malformed deferral cannot silently remove an expected target"
for plan in \
  '{"apple":{"en-US":{"deferredScreenshots":{"iPhone mystery":"No runtime"}}}}' \
  '{"apple":{"en-US":{"deferredScreenshots":{"iPhone Duo":" "}}}}' \
  '{"apple":{"en-US":{"deferredScreenshots":{"iPhone Duo":true}}}}' \
  '{"apple":{"en-US":{"deferredScreenshots":{"iPhone Duo":"line1\nline2"}}}}'; do
  printf '%s\n' "$plan" > "$T/.listing-kit/asset-plan.json"
  OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
  assert_eq 1 "$RC"
done

it "existing required screenshots cannot be hidden by a deferral"
for display in 'iPhone Dynamic Island (medium display)' 'iPad 13"'; do
  python3 - "$T/.listing-kit/asset-plan.json" "$display" <<'PYTEST'
import json, sys
with open(sys.argv[1], 'w') as f:
    json.dump({'apple': {'en-US': {'deferredScreenshots': {sys.argv[2]: 'No simulator'}}}}, f)
PYTEST
  OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
  assert_eq 1 "$RC"
  assert_contains "$OUT" "cannot defer required screenshot class: $display"
  OUT="$(LK_SUPPORTS_IPHONE=0 LK_SUPPORTS_IPAD=0 bash "$SUT" "$T" 2>&1)"; RC=$?
  assert_eq 0 "$RC" "the explicit supported-device overrides still apply"
done

it "deferral does not waive required medium iPhone screenshots"
printf '%s\n' '{"apple":{"en-US":{"deferredScreenshots":{"iPhone Duo":"No compatible runtime"}}}}' > "$T/.listing-kit/asset-plan.json"
rm "$SHOTS/medium.png"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" 'no iPhone Dynamic Island (medium display) screenshots'

summary
