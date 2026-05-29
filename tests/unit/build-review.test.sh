#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/package/build-review.sh"
APP="$ROOT/examples/expo-recipe-box"

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
assert_contains "$PAGE" 'iPhone 6.9'                   # device-class grouping (note: " is HTML-escaped)
assert_not_contains "$PAGE" 'iPhone 6.9"'   # the " must be HTML-escaped (&quot;), never literal
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

summary
