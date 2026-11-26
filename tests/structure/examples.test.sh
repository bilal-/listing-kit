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

# The example is validated as committed (a snapshot of HEAD when this is a git
# checkout, so an untracked local capture cannot change the answer), with no fixture
# added, and examples/README.md must say what the validator says.
it "examples/README.md tells the truth about the example's validation state"
SNAP="$(mktemp -d)"; [ -n "$SNAP" ] && [ -d "$SNAP" ] || { fail "mktemp failed"; summary; exit 1; }
if git -C "$ROOT" rev-parse --verify -q HEAD >/dev/null 2>&1 \
   && git -C "$ROOT" archive HEAD examples/expo-recipe-box 2>/dev/null | tar -x -C "$SNAP" 2>/dev/null \
   && [ -d "$SNAP/examples/expo-recipe-box/fastlane" ]; then
  EX="$SNAP/examples/expo-recipe-box"
else
  EX="$APP"
fi
# Detection overrides in the caller's environment must not change what is checked.
OUT="$(env -u LK_SUPPORTS_IPHONE -u LK_SUPPORTS_IPAD bash "$SCRIPTS/validate/validate-listing.sh" "$EX" 2>&1)"; RC=$?
rm -rf "$SNAP"
README="$(cat "$ROOT/examples/README.md")"
ROWS="$(grep -c '^| \[`expo-recipe-box`\](expo-recipe-box) |' "$ROOT/examples/README.md")"
assert_eq 1 "$ROWS" "one status row for the example"
STATUS="$(grep '^| \[`expo-recipe-box`\](expo-recipe-box) |' "$ROOT/examples/README.md")"
FAILS="$(printf '%s\n' "$OUT" | sed -n 's/^.* · \([0-9][0-9]*\) failures\{0,1\} .*$/\1/p' | tail -1)"
if [ "$RC" = 0 ]; then
  assert_contains "$STATUS" "passes validation" "example validates, so the row must say so"
  for stale in "needs recapture" "missing medium set" "predate Apple" "Recapture it" "historical listing output"; do
    assert_not_contains "$README" "$stale" "nothing in the README may still call the example stale"
  done
else
  assert_eq 1 "$RC" "the validator ran and reported failures (not a usage error)"
  assert_contains "$STATUS" "needs recapture" "example fails validation, so the row must say so"
  assert_contains "$STATUS" "medium" "the row names what is missing"
  assert_not_contains "$STATUS" "passes validation" "the row must not also claim it passes"
  assert_contains "$OUT" "no iPhone Dynamic Island (medium display) screenshots" "the known failure is the missing medium iPhone set"
  assert_eq 1 "$FAILS" "exactly one failure"
fi

summary
