#!/usr/bin/env bash
# Generator: emit per-AI-platform install manifests from the canonical skill so
# they never drift. EMIT-ONLY (v1) — writes files, does not install anything.
#
# Reads .claude-plugin/plugin.json (the source of truth for name/version/desc)
# and writes, at the repo root:
#   - gemini-extension.json          (Gemini CLI)
#   - AGENTS.md                      (Codex / Copilot CLI discovery)
#   - .kiro/steering/listing-kit.md  (Kiro steering-doc wrapper — best-effort)
#
# The Claude Code manifests (.claude-plugin/{plugin,marketplace}.json) are the
# hand-maintained source and are NOT regenerated here.
#
# Usage: generate-manifests.sh [<repo-root>]
set -euo pipefail

root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)}"
plugin_json="$root/.claude-plugin/plugin.json"

[ -f "$plugin_json" ] || { echo "Missing $plugin_json" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "Need python3 to read $plugin_json" >&2; exit 2; }

read_field() { python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2],""))' "$plugin_json" "$1"; }

name="$(read_field name)"
version="$(read_field version)"
description="$(read_field description)"
skill_md="skills/$name/SKILL.md"

# --- Gemini CLI extension (json.dumps so quotes etc. in the description stay valid) ---
python3 - "$root/gemini-extension.json" "$name" "$version" "$description" "$skill_md" <<'PY'
import json, sys
out, name, version, description, context = sys.argv[1:6]
with open(out, "w", encoding="utf-8") as f:
    json.dump({"name": name, "version": version, "description": description,
               "contextFileName": context}, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
echo "wrote gemini-extension.json"

# --- Codex / Copilot CLI discovery ---
cat > "$root/AGENTS.md" <<EOF
# Agents & skills in this repo

## $name (v$version)

$description

**Skill instructions:** [\`$skill_md\`]($skill_md)

Codex installs it as a plugin (\`codex plugin marketplace add bilal-/listing-kit\`,
then \`codex plugin add listing-kit@listing-kit\`). Under Copilot CLI, load the
skill file above as context, then follow its pipeline. All work is plain shell-outs; see
\`skills/$name/references/platforms/tool-mapping.md\` for tool-name
equivalents on your platform.
EOF
echo "wrote AGENTS.md"

# --- Kiro steering doc (best-effort: Kiro has no confirmed plugin installer) ---
mkdir -p "$root/.kiro/steering"
cat > "$root/.kiro/steering/$name.md" <<EOF
---
inclusion: manual
---

# $name (v$version)

$description

This is a Kiro **steering-doc wrapper**. Kiro has no confirmed plugin/skill
installer, so load the canonical skill below as context and follow its pipeline.

**Skill instructions:** [\`$skill_md\`](../../$skill_md)

All work is plain shell-outs; see
\`skills/$name/references/platforms/tool-mapping.md\` for tool-name
equivalents on your platform.
EOF
echo "wrote .kiro/steering/$name.md"

echo "Done. (Emit-only: no install performed.)"
