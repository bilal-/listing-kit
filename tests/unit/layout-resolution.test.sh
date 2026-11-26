#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir area
it "store paths across listing commands and the staged commit hook"
python3 -I -B "$(dirname "${BASH_SOURCE[0]}")/layout_resolution.py" "$area" "$SKILL_DIR"
assert_eq 0 "$?"
summary
