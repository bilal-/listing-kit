#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/package/generate-manifests.sh"

# Run against an isolated root so the repo's committed manifests aren't touched.
T="$(mktemp -d)"
mkdir -p "$T/.claude-plugin"
cp "$ROOT/.claude-plugin/plugin.json" "$T/.claude-plugin/plugin.json"

it "exits 0 and emits the non-Claude manifests + Kiro steering doc"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_file "$T/gemini-extension.json"
assert_file "$T/AGENTS.md"
assert_file "$T/.kiro/steering/listing-kit.md"

it "gemini-extension.json is valid JSON carrying the plugin name + skill path"
if json_valid "$T/gemini-extension.json"; then pass "valid JSON"; else fail "invalid JSON"; fi
assert_eq "listing-kit" "$(json_get "$T/gemini-extension.json" name)"
assert_eq "skills/listing-kit/SKILL.md" "$(json_get "$T/gemini-extension.json" contextFileName)"

it "AGENTS.md embeds version and points at the canonical skill"
AG="$(cat "$T/AGENTS.md")"
assert_contains "$AG" "v0.1.0"
assert_contains "$AG" "skills/listing-kit/SKILL.md"

it "Kiro steering doc embeds version and points at the canonical skill"
KI="$(cat "$T/.kiro/steering/listing-kit.md")"
assert_contains "$KI" "v0.1.0"
assert_contains "$KI" "skills/listing-kit/SKILL.md"
assert_contains "$KI" "inclusion: manual"

it "fails clearly when plugin.json is missing"
T2="$(mktemp -d)"
OUT="$(bash "$SUT" "$T2" 2>&1)"; RC=$?
assert_eq 2 "$RC"
assert_contains "$OUT" "Missing"

rm -rf "$T" "$T2"
summary
