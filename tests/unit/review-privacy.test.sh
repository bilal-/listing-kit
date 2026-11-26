#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
it "protects App Review data across store downloads and listing commands"
if (cd "$SUITE_ROOT" && python3 -IB "$ROOT/tests/unit/review_privacy.py"); then pass; else fail; fi
summary
