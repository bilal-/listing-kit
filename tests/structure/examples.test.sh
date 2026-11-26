#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

APP="$ROOT/examples/expo-recipe-box"

it "example app.json is valid JSON and registers the recipebox scheme"
assert_file "$APP/app.json"
if json_valid "$APP/app.json"; then pass "valid JSON"; else fail "invalid app.json"; fi
assert_eq "recipebox" "$(json_path "$APP/app.json" "['expo']['scheme']")" "expo.scheme"

it "expo-router is the entry point"
assert_eq "expo-router/entry" "$(json_get "$APP/package.json" main)" "package.json main"

it "all four screens exist"
for f in index.tsx "recipe/[id].tsx" shopping.tsx settings.tsx; do
  assert_file "$APP/app/$f"
done

it "each Maestro flow declares an appId, launches clean, and asserts content"
flows=0
for f in "$APP/.listing-kit/flows/"*.yaml; do
  flows=$((flows + 1))
  if grep -q '^appId:' "$f" && grep -q 'clearState: true' "$f" && grep -q 'assertVisible:' "$f"; then pass "${f##*/}"; else fail "malformed flow: $f"; fi
done
it "found the expected four flows"
assert_eq 4 "$flows"

it "committed example flows contain no inlined secrets"
OUT="$(bash "$SCRIPTS/lib/secret-scan.sh" "$APP/.listing-kit/flows" 2>&1)"; RC=$?
assert_eq 0 "$RC" "flows are secret-clean"

# The example is validated exactly as committed, with no fixture added, and the
# examples README must say the same thing the validator says.
it "examples/README.md tells the truth about the example's validation state"
# Detection overrides in the caller's environment must not change what is checked.
OUT="$(env -u LK_SUPPORTS_IPHONE -u LK_SUPPORTS_IPAD bash "$SCRIPTS/validate/validate-listing.sh" "$APP" 2>&1)"; RC=$?
# The status lives in exactly one place: the table row that links to the example.
ROWS="$(grep -c '^| \[`expo-recipe-box`\](expo-recipe-box) |' "$ROOT/examples/README.md")"
assert_eq 1 "$ROWS" "one status row for the example"
STATUS="$(grep '^| \[`expo-recipe-box`\](expo-recipe-box) |' "$ROOT/examples/README.md")"
FAILS="$(printf '%s\n' "$OUT" | sed -n 's/.* \([0-9][0-9]*\) failures.*/\1/p' | tail -1)"
if [ "$RC" = 0 ]; then
  assert_contains "$STATUS" "passes validation" "example validates, so the row must say so"
  assert_not_contains "$(cat "$ROOT/examples/README.md")" "needs recapture" "nothing in the README may still call it stale"
else
  assert_contains "$STATUS" "needs recapture" "example fails validation, so the row must say so"
  assert_contains "$OUT" "no iPhone Dynamic Island (medium display) screenshots" "the known failure is the missing medium iPhone set"
  assert_eq 1 "$FAILS" "exactly one failure"
fi

summary
