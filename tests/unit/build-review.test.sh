#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/package/build-review.sh"
# Keep historical example captures unchanged; add a synthetic medium-size test fixture.
APP="$(mktemp -d)"
cp -R "$ROOT/examples/expo-recipe-box/fastlane" "$ROOT/examples/expo-recipe-box/app.json" "$APP/"
fake_png "$APP/fastlane/screenshots/en-US/medium_01.png" 1206 2622
trap 'rm -rf "$APP"' EXIT

it "exits 2 when there is no fastlane tree"
T="$(mktemp -d)"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 2 "$RC"
rm -rf "$T"

# Build the review page against the committed example (both stores present).
T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
it "exits 0 and writes listing-review.html at the app root"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_file "$T/listing-review.html"
PAGE="$(cat "$T/listing-review.html")"

it "renders the iOS/Android toggle and copy buttons"
assert_contains "$PAGE" 'data-p="iOS"'
assert_contains "$PAGE" 'data-p="Android"'
assert_contains "$PAGE" 'onclick="cp(this)"'          # copy button

it "renders char counts, screenshots, and graphics"
assert_contains "$PAGE" '23/30'                        # name: "Recipe Box: Cook & Shop"
assert_contains "$PAGE" 'fastlane/screenshots/en-US/'  # relative screenshot link (iOS)
assert_contains "$PAGE" 'phoneScreenshots'             # android screenshot link
assert_contains "$PAGE" 'iPhone Dynamic Island (large display)' # device-class grouping
assert_contains "$PAGE" 'iPad 13&quot;' # class labels are HTML-escaped
assert_contains "$PAGE" 'Feature graphic'              # generated graphic

it "embeds the validator output"
assert_contains "$PAGE" 'LISTING VALID'                # embedded validator banner

it "is read-only — does not create or modify anything under fastlane/"
before="$(cd "$T" && find fastlane -type f -exec cksum {} \; | sort)"   # cksum is POSIX (both CI OSes)
bash "$SUT" "$T" >/dev/null 2>&1
after="$(cd "$T" && find fastlane -type f -exec cksum {} \; | sort)"
assert_eq "$before" "$after" "fastlane tree unchanged"
rm -rf "$T"

it "shows a missing required field as 'missing' rather than inventing a value"
T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
rm -f "$T/fastlane/metadata/en-US/support_url.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"
assert_contains "$(cat "$T/listing-review.html")" "missing"
rm -rf "$T"

it "rebuilds from edited metadata txt files"
T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
bash "$SUT" "$T" >/dev/null 2>&1
assert_not_contains "$(cat "$T/listing-review.html")" "Edited copy from txt"
printf 'Edited copy from txt\n' > "$T/fastlane/metadata/en-US/description.txt"
bash "$SUT" "$T" >/dev/null 2>&1
PAGE="$(cat "$T/listing-review.html")"
assert_contains "$PAGE" "Edited copy from txt"
assert_contains "$PAGE" "Generated "
assert_contains "$PAGE" "from fastlane metadata .txt files"
rm -rf "$T"

it "non-locale metadata dirs (review_information/) are not shown as locales"
T="$(mktemp -d)"; cp -R "$ROOT/examples/expo-recipe-box/fastlane" "$T/"
mkdir -p "$T/fastlane/metadata/review_information"
printf 'demo@example.test\n' > "$T/fastlane/metadata/review_information/email_address.txt"
bash "$SUT" "$T" >/dev/null 2>&1
assert_not_contains "$(cat "$T/listing-review.html")" "locale: review_information"
rm -rf "$T"

it "keyword badge counts UTF-8 bytes, matching the validator"
T="$(mktemp -d)"; cp -R "$ROOT/examples/expo-recipe-box/fastlane" "$T/"
python3 -c "import sys;open(sys.argv[1],'w',encoding='utf-8').write('料'*40)" "$T/fastlane/metadata/en-US/keywords.txt"
bash "$SUT" "$T" >/dev/null 2>&1
PAGE="$(cat "$T/listing-review.html")"
assert_contains "$PAGE" '<span class="b bad">120/100 bytes</span>'
rm -rf "$T"

it "shows Play graphics from images/featureGraphic.png and images/icon.png"
T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"
bash "$SUT" "$T" >/dev/null 2>&1
PAGE="$(cat "$T/listing-review.html")"
assert_contains "$PAGE" "images/featureGraphic.png"
assert_contains "$PAGE" "Feature graphic 1024×500"
assert_contains "$PAGE" "images/icon.png"
rm -rf "$T"

it "malformed URL hosts and ports fail validation without crashing the review"
for url in 'https://[::1' 'https://example.test:abc/help' 'https://example.test:70000/help'; do
  T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
  printf '%s\n' "$url" > "$T/fastlane/metadata/en-US/support_url.txt"
  OUT="$(bash "$SCRIPTS/validate/validate-listing.sh" "$T" 2>&1)"; RC=$?
  assert_eq 1 "$RC"
  assert_contains "$OUT" 'support_url: not a single http(s) URL'
  assert_not_contains "$OUT" Traceback
  OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
  assert_eq 0 "$RC"
  assert_not_contains "$OUT" Traceback
  if [ -f "$T/listing-review.html" ]; then
    assert_contains "$(cat "$T/listing-review.html")" '<span class="b bad">check</span>'
  else
    fail 'review page was not generated for invalid URL'
  fi
  rm -rf "$T"
done

it "invalid UTF-8 in app-level copy fails validation and remains reviewable"
for stem in copyright primary_category; do
  T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
  printf 'Caf\xe9\n' > "$T/fastlane/metadata/$stem.txt"
  OUT="$(bash "$SCRIPTS/validate/validate-listing.sh" "$T" 2>&1)"; RC=$?
  assert_eq 1 "$RC"
  assert_contains "$OUT" "$stem: not valid UTF-8"
  OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
  assert_eq 0 "$RC"
  assert_not_contains "$OUT" Traceback
  if [ -f "$T/listing-review.html" ]; then
    assert_contains "$(cat "$T/listing-review.html")" '<span class="b bad">not valid UTF-8</span>'
  else
    fail 'review page was not generated for invalid app-level copy'
  fi
  rm -rf "$T"
done

summary
