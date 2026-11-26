#!/usr/bin/env bash
# Regenerate the install metadata from the canonical Claude plugin manifest.
set -euo pipefail
root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)}"
plugin_json="$root/.claude-plugin/plugin.json"
[ -f "$plugin_json" ] || { echo "Missing $plugin_json" >&2; exit 2; }
command -v python3 >/dev/null || { echo "Need python3 to read $plugin_json" >&2; exit 2; }

python3 - "$root" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
plugin = json.loads((root / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
identity = {key: plugin[key] for key in ("name", "version", "description")}
name = plugin["name"]

def write(path, content):
    dest = root / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content + "\n", encoding="utf-8")
    print("wrote", path)

def write_json(path, data):
    write(path, json.dumps(data, indent=2, ensure_ascii=False))

write(Path("skills") / name / "VERSION", plugin["version"])
write_json("gemini-extension.json", identity)
entry = dict(identity, category="productivity", source="./",
             keywords=plugin["keywords"])
for key in ("author", "homepage", "license"):
    if key in plugin:
        entry[key] = plugin[key]
write_json(".claude-plugin/marketplace.json", {
    "$schema": "https://json.schemastore.org/claude-code-marketplace.json",
    "name": name, "description": plugin["description"], "owner": plugin["author"],
    "plugins": [entry],
})
PY
