#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir app
new_stubdir
stub magick
unset LK_NO_IMAGEMAGICK
export PATH="$STUB_BIN:$PATH" LK_SUPPORTS_IPHONE=1 LK_SUPPORTS_IPAD=0
meta="$app/fastlane/metadata"
mkdir -p "$meta"
cp -R "$ROOT/examples/expo-recipe-box/fastlane/metadata/en-US" "$meta/"
cp "$ROOT"/examples/expo-recipe-box/fastlane/metadata/*.txt "$meta/"
fake_png "$app/fastlane/screenshots/en-US/one.png" 1206 2622
expected="$SUITE_ROOT/expected.txt"
actual="$SUITE_ROOT/actual.txt"
cat > "$expected" <<EOF
Secret scan clean: no detected credentials.
  ✓ secret scan: clean
listing-kit validating: $app
store rules verified on 2026-11-26
== Apple App Store ==
  NOTE: Use --verbose for optional fields and platform evidence.
  locale en-US:
  ✓ name: 23/30 chars
  ✓ subtitle: 28/30 chars
  ✓ promotional_text: 85/170 chars
  ✓ description: 671/4000 chars
  ✓ keywords: 79/100 bytes
  ✓ support_url: https://github.com/bilal-/listing-kit/issues
  ✓ marketing_url: https://github.com/bilal-/listing-kit
  ✓ privacy_url: https://github.com/bilal-/listing-kit/blob/main/examples/expo-recipe-box/PRIVACY.md
  ✓ release_notes: 40/4000 chars
  screenshots en-US:
  ✓ iPhone Dynamic Island (medium display) screenshots present (1)
  ✓ copyright: set
  ✓ primary_category: set
  ! no asset-plan.json: store minimums checked; requested extra sets/headers cannot be confirmed
── 13 passed · 1 warnings · 0 failures ──
LISTING VALID
EOF
it "legacy validate matches the pre-listing.json transcript byte for byte"
"$SKILL_DIR/bin/listing-kit" validate "$app" --as-of 2026-11-26 > "$actual"
diff -u "$expected" "$actual" && pass || fail "legacy transcript changed"
it "a malformed legacy plan is reported at the end of the Apple section"
mkdir -p "$app/.listing-kit"
echo malformed > "$app/.listing-kit/asset-plan.json"
"$SKILL_DIR/bin/listing-kit" validate "$app" --as-of 2026-11-26 > "$actual"
assert_contains "$(cat "$actual")" $'✓ primary_category: set\n  ✗ asset-plan.json: Expecting value'
it "a filtered legacy review retains its Apple tab for a malformed asset plan"
git init -q "$app"
remove_fixture "$app/fastlane"
mkdir -p "$meta"
cp -R "$ROOT/examples/expo-recipe-box/fastlane/metadata/android" "$meta/"
printf '.listing-kit/local.json\n' > "$app/.gitignore"
echo '{}' > "$app/.listing-kit/local.json"
"$SKILL_DIR/bin/listing-kit" review "$app" >/dev/null
assert_contains "$(cat "$app/listing-review.html")" 'data-p="iOS"'
summary
