#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir T
cp -R "$ROOT/examples/expo-recipe-box/fastlane" "$ROOT/examples/expo-recipe-box/app.json" "$T/"
mkdir -p "$T/.listing-kit"
cat > "$T/.listing-kit/specs.override.json" <<'JSON'
{"stores":{"apple":{"screenshots":{"slots":[{"id":"future","label":"Future Display","sizes":[[321,654]],"min":1,"max":3,"framing":"allowed","lifecycle":"active","upload":"fastlane","required":{"rule":"always"}}]},"fields":[{"stem":"name","limit":4}],"graphics":[{"id":"header-16x9","size":[321,123],"formats":["jpeg"],"label":"Future header","required":{"rule":"always"}}]},"play":{"screenshots":{"slots":[{"id":"phone","folder":"customShots","label":"Custom phone"}]}}}}
JSON
fake_png "$T/fastlane/screenshots/en-US/future.png" 321 654
fake_jpeg "$T/store-assets/apple/en-US/banner.jpg" 321 123
mv "$T/fastlane/metadata/android/en-US/images/phoneScreenshots" "$T/fastlane/metadata/android/en-US/images/customShots"
printf '%s' '{"apple":{"en-US":{"screenshots":{"Future Display":1}}}}' > "$T/.listing-kit/asset-plan.json"
it "the validator and review use an app override for slots, headers, fields and Play folders"
OUT="$(bash "$SCRIPTS/validate/validate-listing.sh" "$T" 2>&1)"
assert_contains "$OUT" "specs.override.json"
assert_contains "$OUT" "Future Display: 1 of 1 screenshots"
assert_contains "$OUT" "name: 23/4 chars OVER LIMIT"
assert_contains "$OUT" "321x123 RGB/no-alpha"
bash "$SCRIPTS/package/build-review.sh" "$T" >/dev/null
PAGE="$(cat "$T/listing-review.html")"
assert_contains "$PAGE" "Future Display <span"
assert_contains "$PAGE" "Custom phone <span"
assert_contains "$PAGE" ">23/4</span>"
assert_contains "$PAGE" "Future header 321×123"
mv "$T/store-assets/apple/en-US/banner.jpg" "$T/saved-header.jpg"
OUT="$(bash "$SCRIPTS/validate/validate-listing.sh" "$T" 2>&1)"
assert_contains "$OUT" "Future header MISSING"
it "render and drift check use the same merged rules on a temporary copy"
cp -R "$SKILL_DIR/specs" "$SKILL_DIR/references/stores" "$T/"
render(){ python3 -I -B "$SCRIPTS/specs/render.py" --app-root "$T" --rules "$T/specs/stores.json" --docs "$T/stores" "$@"; }
render --check >/dev/null; assert_eq 1 "$?"
render && render --check; assert_eq 0 "$?"
assert_contains "$(cat "$T/stores/apple-app-store.md")" "321×654"
assert_contains "$(cat "$T/stores/apple-app-store.md")" "4 chars"
summary
