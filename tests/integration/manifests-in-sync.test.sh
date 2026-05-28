#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

# The committed AGENTS.md / gemini-extension.json must match what the generator
# produces from the current plugin.json. Catches "forgot to regenerate" drift.
SUT="$SCRIPTS/package/generate-manifests.sh"

T="$(mktemp -d)"
mkdir -p "$T/.claude-plugin"
cp "$ROOT/.claude-plugin/plugin.json" "$T/.claude-plugin/plugin.json"
bash "$SUT" "$T" >/dev/null 2>&1

it "committed gemini-extension.json is in sync with the generator"
if diff -u "$ROOT/gemini-extension.json" "$T/gemini-extension.json" >/dev/null; then
  pass "in sync"
else
  fail "stale — run: bash skills/listing-kit/scripts/package/generate-manifests.sh"
fi

it "committed AGENTS.md is in sync with the generator"
if diff -u "$ROOT/AGENTS.md" "$T/AGENTS.md" >/dev/null; then
  pass "in sync"
else
  fail "stale — run: bash skills/listing-kit/scripts/package/generate-manifests.sh"
fi

it "committed .kiro/steering/listing-kit.md is in sync with the generator"
if diff -u "$ROOT/.kiro/steering/listing-kit.md" "$T/.kiro/steering/listing-kit.md" >/dev/null; then
  pass "in sync"
else
  fail "stale — run: bash skills/listing-kit/scripts/package/generate-manifests.sh"
fi

rm -rf "$T"
summary
