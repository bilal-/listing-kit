#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
it "published store tables match the bundled rules"
python3 -I -B "$SCRIPTS/specs/render.py" --check
assert_eq 0 "$?"
it "guides and stack references do not maintain separate store dimensions"
# Device and simulator identifiers are not dimensions. No pixel-size exceptions are needed.
files=("$SKILL_DIR/SKILL.md" "$ROOT/docs/GUIDE.md" "$ROOT/docs/ARCHITECTURE.md" "$ROOT/CONTRIBUTING.md"
       "$SKILL_DIR"/references/stacks/*.md "$SKILL_DIR/references/metadata/fastlane-layout.md"
       "$SKILL_DIR"/references/stores/*.md)
matches="$(awk '/<!-- rules:begin / {generated=1} /<!-- rules:end / {generated=0; next}
               !generated {print FILENAME ":" FNR ":" $0}' "${files[@]}" | grep -E '[0-9]{3,}[x×][0-9]{3,}' || true)"
assert_eq "" "$matches"
summary
