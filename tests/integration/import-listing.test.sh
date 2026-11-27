#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir app
(cd "$app" && python3 "$ROOT/tests/integration/import_listing.py" "$SKILL_DIR") && pass "existing listing import workflows" || fail "import workflows"
summary
