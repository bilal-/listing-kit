#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

# The committed install metadata must match what the generator
# produces from the current plugin.json. Catches "forgot to regenerate" drift.
SUT="$SCRIPTS/package/generate-manifests.sh"

new_tempdir T
mkdir -p "$T/.claude-plugin"
cp "$ROOT/.claude-plugin/plugin.json" "$T/.claude-plugin/plugin.json"
bash "$SUT" "$T" >/dev/null 2>&1

for generated in gemini-extension.json .claude-plugin/marketplace.json skills/listing-kit/VERSION; do
  it "$generated matches the generator"
  if diff -u "$ROOT/$generated" "$T/$generated"; then pass "$generated"; else fail "regenerate $generated"; fi
done

remove_fixture "$T"
summary
