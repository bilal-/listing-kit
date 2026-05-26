#!/usr/bin/env bash
# Generator: emit per-AI-platform install manifests from the canonical skill so
# they never drift. EMIT-ONLY (v1) — writes files, does not install anything.
#
# Reads .claude-plugin/plugin.json (the source of truth for name/version/desc)
# and writes, at the repo root:
#   - gemini-extension.json   (Gemini CLI)
#   - AGENTS.md               (Codex / Copilot CLI discovery)
#
# The Claude Code manifests (.claude-plugin/{plugin,marketplace}.json) are the
# hand-maintained source and are NOT regenerated here.
#
# Usage: generate-manifests.sh [<repo-root>]
set -euo pipefail

root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)}"
plugin_json="$root/.claude-plugin/plugin.json"
skill_md="skills/listing-kit/SKILL.md"

[ -f "$plugin_json" ] || { echo "Missing $plugin_json" >&2; exit 2; }

# Read fields from plugin.json (python3 preferred, jq fallback).
read_field() {
  local key="$1"
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import json,sys;print(json.load(open('$plugin_json')).get('$key',''))"
  elif command -v jq >/dev/null 2>&1; then
    jq -r ".$key // \"\"" "$plugin_json"
  else
    echo "Need python3 or jq to read $plugin_json" >&2; exit 2
  fi
}

name="$(read_field name)"
version="$(read_field version)"
description="$(read_field description)"

# --- Gemini CLI extension ---
cat > "$root/gemini-extension.json" <<EOF
{
  "name": "$name",
  "version": "$version",
  "description": "$description",
  "contextFileName": "$skill_md"
}
EOF
echo "wrote gemini-extension.json"

# --- Codex / Copilot CLI discovery ---
cat > "$root/AGENTS.md" <<EOF
# Agents & skills in this repo

## $name (v$version)

$description

**Skill instructions:** [\`$skill_md\`]($skill_md)

To use under Codex or Copilot CLI, load the skill file above as context, then
follow its pipeline. All work is plain shell-outs; see
\`skills/listing-kit/references/platforms/tool-mapping.md\` for tool-name
equivalents on your platform.
EOF
echo "wrote AGENTS.md"

echo "Done. (Emit-only: no install performed.)"
