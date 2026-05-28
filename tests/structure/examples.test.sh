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

it "each Maestro flow declares an appId and an action"
flows=0
for f in "$APP/.listing-kit/flows/"*.yaml; do
  flows=$((flows + 1))
  if grep -q '^appId:' "$f" && grep -q 'openLink:' "$f"; then pass "${f##*/}"; else fail "malformed flow: $f"; fi
done
it "found the expected four flows"
assert_eq 4 "$flows"

it "committed example flows contain no inlined secrets"
OUT="$(bash "$SCRIPTS/lib/secret-scan.sh" "$APP/.listing-kit/flows" 2>&1)"; RC=$?
assert_eq 0 "$RC" "flows are secret-clean"

summary
