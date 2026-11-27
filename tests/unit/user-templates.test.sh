#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
it "repo templates resolve, validate, render and preview through the composer"
if python3 "$ROOT/tests/unit/app_template_cases.py"; then pass; else fail; fi
summary
