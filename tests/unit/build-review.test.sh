#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/package/build-review.sh"
# FIXTURE, not the example as shipped: a copy plus a synthetic medium-size iPhone
# screenshot, so these tests have a valid tree to mutate. The example as committed is
# checked without any addition in tests/structure/examples.test.sh.
new_tempdir APP
cp -R "$ROOT/examples/expo-recipe-box/fastlane" "$ROOT/examples/expo-recipe-box/app.json" "$APP/"
fake_png "$APP/fastlane/screenshots/en-US/medium_01.png" 1206 2622

it "exits 2 when there is no fastlane tree"
new_tempdir T
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 2 "$RC"
remove_fixture "$T"

# Build the review page against the fixture copy (both stores present).
new_tempdir T; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
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
remove_fixture "$T"

it "shows a missing required field as 'missing' rather than inventing a value"
new_tempdir T; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
rm -f "$T/fastlane/metadata/en-US/support_url.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"
assert_contains "$(cat "$T/listing-review.html")" "missing"
remove_fixture "$T"

it "rebuilds from edited metadata txt files"
new_tempdir T; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
bash "$SUT" "$T" >/dev/null 2>&1
assert_not_contains "$(cat "$T/listing-review.html")" "Edited copy from txt"
printf 'Edited copy from txt\n' > "$T/fastlane/metadata/en-US/description.txt"
bash "$SUT" "$T" >/dev/null 2>&1
PAGE="$(cat "$T/listing-review.html")"
assert_contains "$PAGE" "Edited copy from txt"
assert_contains "$PAGE" "Generated "
assert_contains "$PAGE" "from fastlane metadata .txt files"
remove_fixture "$T"

it "non-locale metadata dirs (review_information/) are not shown as locales"
new_tempdir T; cp -R "$ROOT/examples/expo-recipe-box/fastlane" "$T/"
mkdir -p "$T/fastlane/metadata/review_information"
printf 'demo@example.test\n' > "$T/fastlane/metadata/review_information/email_address.txt"
bash "$SUT" "$T" >/dev/null 2>&1
assert_not_contains "$(cat "$T/listing-review.html")" "locale: review_information"
remove_fixture "$T"

it "keyword badge counts UTF-8 bytes, matching the validator"
new_tempdir T; cp -R "$ROOT/examples/expo-recipe-box/fastlane" "$T/"
python3 -c "import sys;open(sys.argv[1],'w',encoding='utf-8').write('料'*40)" "$T/fastlane/metadata/en-US/keywords.txt"
bash "$SUT" "$T" >/dev/null 2>&1
PAGE="$(cat "$T/listing-review.html")"
assert_contains "$PAGE" '<span class="b bad">120/100 bytes</span>'
remove_fixture "$T"

it "shows Play graphics from images/featureGraphic.png and images/icon.png"
new_tempdir T; cp -R "$APP/fastlane" "$T/"
bash "$SUT" "$T" >/dev/null 2>&1
PAGE="$(cat "$T/listing-review.html")"
assert_contains "$PAGE" "images/featureGraphic.png"
assert_contains "$PAGE" "Feature graphic 1024×500"
assert_contains "$PAGE" "images/icon.png"
remove_fixture "$T"

it "malformed URL hosts and ports fail validation without crashing the review"
for url in 'https://[::1' 'https://example.test:abc/help' 'https://example.test:70000/help'; do
  new_tempdir T; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
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
  remove_fixture "$T"
done

it "invalid UTF-8 in app-level copy fails validation and remains reviewable"
for stem in copyright primary_category; do
  new_tempdir T; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
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
  remove_fixture "$T"
done


it "stops before rendering a credential in a displayed field"
printf '%s%s\n' 'ghp_' '0123456789abcdefghijklmnopqrstuvwxyz' > "$APP/fastlane/metadata/en-US/description.txt"
echo 'previous safe page' > "$APP/listing-review.html"
OUT="$(bash "$SUT" "$APP" 2>&1)"; RC=$?
assert_ne 0 "$RC"
assert_contains "$OUT" 'description.txt'
assert_not_contains "$OUT" '0123456789abcdefghijklmnopqrstuvwxyz'
assert_eq 'previous safe page' "$(cat "$APP/listing-review.html")"

it "rejects credentials after NUL and in decoded plan strings before writing"
printf 'prefix\0AKIAIOSFODNN7EXAMPLE' > "$APP/fastlane/metadata/en-US/description.txt"
for kind in field plan; do
  if [ "$kind" = plan ]; then
    echo clean > "$APP/fastlane/metadata/en-US/description.txt"
    mkdir -p "$APP/.listing-kit"
    printf '%s\n' '{"apple":{"en-US":{"deferredScreenshots":{"iPhone Duo":"\u0041KIAIOSFODNN7EXAMPLE"}}}}' > "$APP/.listing-kit/asset-plan.json"
  fi
  echo 'previous page' > "$APP/listing-review.html"
  OUT="$(bash "$SUT" "$APP" 2>&1)"; RC=$?
  assert_eq 3 "$RC" "$kind blocks review generation"
  assert_eq 'previous page' "$(cat "$APP/listing-review.html" | head -c 14)"
  assert_not_contains "$OUT" 'AKIAIOSFODNN7EXAMPLE'
done

it "shows a validation error instead of copying a field containing NUL"
rm "$APP/.listing-kit/asset-plan.json"
printf 'malformed field prefix\0suffix' > "$APP/fastlane/metadata/en-US/description.txt"
bash "$SUT" "$APP" >/dev/null || fail "ordinary malformed copy prevented review"
if grep -aq 'malformed field prefix' "$APP/listing-review.html"; then fail "copied invalid field"; else pass; fi
assert_contains "$(cat "$APP/listing-review.html")" 'contains NUL'

it "manual validation and build include ignored listing inputs and report unsafe names while continuing"
new_tempdir T
cp -R "$APP/fastlane" "$T/"
git -C "$T" init -q
printf '**/fastlane/screenshots\nfastlane/metadata/en-US/\n.listing-kit/private/\n' > "$T/.gitignore"
mkdir -p "$T/.listing-kit/private"
for name in AuthKey_ABC.p8 upload.keystore secrets.local local.json; do
  echo 'AKIAIOSFODNN7EXAMPLE' > "$T/.listing-kit/private/$name"
done
echo 'Clean description' > "$T/fastlane/metadata/en-US/description.txt"
echo 'Ignored marketing message' > "$T/fastlane/metadata/en-US/subtitle.txt"
fake_png "$T/fastlane/screenshots/en-US/ignored.png" 1206 2622
OUT="$(bash "$SCRIPTS/validate/validate-listing.sh" "$T" 2>&1)"; assert_eq 0 "$?" "valid ignored screenshots and metadata pass validation"
assert_contains "$OUT" 'iPhone Dynamic Island (medium display) screenshots present'
unsafe=AKIAIOSFODNN7EXAMPLE
fake_png "$T/fastlane/screenshots/en-US/$unsafe.png" 1206 2622
OUT="$(bash "$SCRIPTS/validate/validate-listing.sh" "$T" 2>&1)"; assert_eq 1 "$?"
assert_contains "$OUT" '[redacted path]'
assert_contains "$OUT" 'LISTING HAS FAILURES'
OUT="$(bash "$SUT" "$T" 2>&1)"; assert_eq 0 "$?"
PAGE="$(cat "$T/listing-review.html")"
assert_contains "$PAGE" '[redacted path]'
assert_contains "$PAGE" 'LISTING HAS FAILURES'
assert_not_contains "$PAGE" "$unsafe"
assert_contains "$PAGE" 'Ignored marketing message'
assert_contains "$PAGE" ignored.png
assert_not_contains "$PAGE" AuthKey_ABC
rm "$T/fastlane/screenshots/en-US/$unsafe.png"
# The extra file never appears on the page. Only a full scan can catch it.
leak="$T/fastlane/metadata/en-US/notes.txt"
echo "$unsafe" > "$leak"
OUT="$(bash "$SCRIPTS/lib/secret-scan.sh" "$T/fastlane" 2>&1)"; assert_eq 1 "$?" "scanner checks ignored directories"
OUT="$(bash "$SCRIPTS/validate/validate-listing.sh" "$T" 2>&1)"; assert_eq 1 "$?" "manual validator scans ignored content"
assert_contains "$OUT" 'notes.txt'
echo 'previous page' > "$T/listing-review.html"
OUT="$(bash "$SUT" "$T" 2>&1)"; assert_eq 3 "$?" "builder blocks secrets in ignored content"
assert_eq 'previous page' "$(cat "$T/listing-review.html")"
rm "$leak"
mkdir -p "$T/fastlane/metadata/review_information"
echo abc > "$T/fastlane/metadata/review_information/demo_password.txt"
OUT="$(bash "$SCRIPTS/validate/validate-listing.sh" "$T" 2>&1)"; assert_eq 1 "$?"
assert_contains "$OUT" 'App Store Connect'
OUT="$(bash "$SUT" "$T" 2>&1)"; assert_eq 0 "$?"
assert_contains "$(cat "$T/listing-review.html")" 'App Store Connect'
it "reports the real app root when a private file requires a filtered copy"
new_tempdir T
new_tempdir scratch
app="$T/my app"
mkdir -p "$app/fastlane/metadata/en-US" "$app/.listing-kit"
touch "$app/.listing-kit/secrets.local"
echo 'Description' > "$app/fastlane/metadata/en-US/description.txt"
OUT="$(cd "$app" && TMPDIR="$scratch" bash "$SCRIPTS/validate/validate-listing.sh" . 2>&1)"; assert_eq 1 "$?"
assert_contains "$OUT" "validating: $app"
assert_contains "$OUT" "REQUIRED file missing ($app/fastlane/metadata/en-US/name.txt)"
assert_not_contains "$OUT" "$scratch/"
OUT="$(cd "$app" && TMPDIR="$scratch" bash "$SUT" . 2>&1)"; assert_eq 0 "$?"
assert_contains "$OUT" "Wrote $app/listing-review.html"
assert_contains "$OUT" "Open it in a browser: $app/listing-review.html"
assert_not_contains "$OUT" "$scratch/"
PAGE="$(cat "$app/listing-review.html")"
assert_contains "$PAGE" "REQUIRED file missing ($app/fastlane/metadata/en-US/name.txt)"
assert_not_contains "$PAGE" "$scratch/"

it "produces a review page with #p-empty saying Nothing to validate when fastlane/ has no store listing"
new_tempdir T; mkdir -p "$T/fastlane"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_file "$T/listing-review.html"
PAGE="$(cat "$T/listing-review.html")"
assert_contains "$PAGE" '<section class="panel on" id="p-empty"><p class="muted">Nothing to validate'
assert_not_contains "$PAGE" "LISTING VALID"
rm -rf "$T"

it "ignores an unrelated fastlane/metadata/README.md on a Play-only listing"
new_tempdir T; cp -R "$APP/fastlane" "$T/"
rm -rf "$T"/fastlane/screenshots "$T"/fastlane/metadata/en-US "$T"/fastlane/metadata/*.txt
printf '# Metadata notes\n' > "$T/fastlane/metadata/README.md"
mkdir -p "$T/fastlane/metadata/notes" "$T/fastlane/screenshots/notes"
touch "$T/fastlane/metadata/notes/README.md" "$T/fastlane/screenshots/notes/README.md"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
PAGE="$(cat "$T/listing-review.html")"
assert_contains "$PAGE" 'data-p="Android"'
assert_not_contains "$PAGE" 'data-p="iOS"'
rm -rf "$T"

it "agrees with validate-listing.sh when fastlane/ is empty and asset-plan.json is malformed"
new_tempdir T; mkdir -p "$T/fastlane" "$T/.listing-kit"
printf '{invalid\n' > "$T/.listing-kit/asset-plan.json"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
PAGE="$(cat "$T/listing-review.html")"
assert_contains "$PAGE" '== Apple App Store =='
assert_contains "$PAGE" 'id="p-iOS"'
assert_not_contains "$PAGE" 'id="p-empty"'
rm -rf "$T"

it "shows escaped crash output and accepts only matching terminal verdicts"
new_tempdir SHIM_ROOT
SHIM="$SHIM_ROOT/scripts"
mkdir -p "$SHIM"
cp -R "$SKILL_DIR/specs" "$SHIM_ROOT/"
cp -R "$SCRIPTS/package" "$SCRIPTS/lib" "$SHIM/"
mkdir -p "$SHIM/validate"
new_tempdir T; mkdir -p "$T/fastlane"
for spec in '1|unexpected <exception>' '2|LISTING HAS FAILURES' '0|LISTING VALID\nLISTING HAS FAILURES' '1|LISTING VALID' '0|LISTING VALID\nTraceback' '1|RuntimeError: nothing to validate handler failed' '1|nothing to validate'; do
  printf 'printf "%%b\\n" "%s"\nexit %s\n' "${spec#*|}" "${spec%%|*}" > "$SHIM/validate/validate-listing.sh"
  OUT="$(bash "$SHIM/package/build-review.sh" "$T" 2>&1)"; RC=$?
  assert_eq 1 "$RC" "crash or mismatched terminal verdict fails build-review"
  PAGE="$(cat "$T/listing-review.html" 2>/dev/null)"
  assert_contains "$PAGE" "validator crashed"
  case "$spec" in *exception*) assert_contains "$PAGE" "unexpected &lt;exception&gt;";; esac
done
for spec in '1|LISTING HAS FAILURES' '0|LISTING VALID'; do
  printf 'echo "%s"\nexit %s\n' "${spec#*|}" "${spec%%|*}" > "$SHIM/validate/validate-listing.sh"
  OUT="$(bash "$SHIM/package/build-review.sh" "$T" 2>&1)"; RC=$?
  assert_eq 0 "$RC" "accept matching terminal verdict $spec"
  assert_not_contains "$(cat "$T/listing-review.html")" 'validator crashed'
done
remove_fixture "$T" "$SHIM_ROOT"

it "renders Apple review panels when only metadata/default/ or app-level copy is present"
new_tempdir T; mkdir -p "$T/fastlane/metadata/default"
printf 'Default Name\n' > "$T/fastlane/metadata/default/name.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$(cat "$T/listing-review.html")" "Default Name"
rm -rf "$T"

new_tempdir T; mkdir -p "$T/fastlane/metadata"
printf '2026 Studio\n' > "$T/fastlane/metadata/copyright.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$(cat "$T/listing-review.html")" "2026 Studio"
rm -rf "$T"

summary
