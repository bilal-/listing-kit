#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/package/generate-manifests.sh"

# Run against an isolated root so the repo's committed manifests aren't touched.
new_tempdir T
mkdir -p "$T/.claude-plugin"
cp "$ROOT/.claude-plugin/plugin.json" "$T/.claude-plugin/plugin.json"

it "generates install metadata without writing agent instructions"
echo "Contributor instructions" > "$T/AGENTS.md"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_eq "Contributor instructions" "$(cat "$T/AGENTS.md")"
[ ! -e "$T/.kiro" ] && pass "no steering wrapper" || fail "unexpected .kiro"
assert_eq "listing-kit" "$(json_get "$T/gemini-extension.json" name)"
assert_not_contains "$(cat "$T/gemini-extension.json")" "contextFileName"

it "a description containing quotes and backslashes still yields valid JSON"
new_tempdir T3; mkdir -p "$T3/.claude-plugin"
printf '{"name":"listing-kit","version":"9.9.9","keywords":["test"],"author":{"name":"Example"},"description":"Say \\"hi\\" \\\\ ok"}' > "$T3/.claude-plugin/plugin.json"
bash "$SUT" "$T3" >/dev/null 2>&1
if json_valid "$T3/gemini-extension.json"; then pass "valid JSON"; else fail "invalid JSON"; fi
assert_eq 'Say "hi" \ ok' "$(json_get "$T3/gemini-extension.json" description)"
assert_eq "9.9.9" "$(cat "$T3/skills/listing-kit/VERSION")" "VERSION comes from the supplied plugin.json"
for field in description version keywords; do
  assert_eq "$(json_get "$T3/.claude-plugin/plugin.json" "$field")" "$(json_path "$T3/.claude-plugin/marketplace.json" "['plugins'][0]['$field']")" "marketplace entry inherits $field"
done
remove_fixture "$T3"

it "fails clearly when plugin.json is missing"
new_tempdir T2
OUT="$(bash "$SUT" "$T2" 2>&1)"; RC=$?
assert_eq 2 "$RC"
assert_contains "$OUT" "Missing"

remove_fixture "$T" "$T2"
summary
