#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/generate/feature-graphic.sh"

it "exits 2 with no args"
OUT="$(bash "$SUT" 2>&1)"; RC=$?
assert_eq 2 "$RC"

it "exits 2 when icon file is missing"
OUT="$(bash "$SUT" /no/such/icon.png /tmp/out.png 2>&1)"; RC=$?
assert_eq 2 "$RC"

# Real icon file for the remaining cases.
ICON="$(mktemp).png"; printf 'icon' > "$ICON"
OUTPNG="$(mktemp).png"; rm -f "$OUTPNG"

it "exits 3 and prompts a fallback when ImageMagick is absent"
new_stubdir   # empty stub dir → no magick/convert on PATH (absolute bash so it's still findable)
OUT="$(PATH="$STUB_BIN" "$BASH_BIN" "$SUT" "$ICON" "$OUTPNG" 2>&1)"; RC=$?
assert_eq 3 "$RC" "exit 3 signals 'prompt the user'"
assert_contains "$OUT" "FALLBACK"

it "composites a 1024x500 no-alpha graphic when ImageMagick is present"
new_stubdir; stub magick
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" "$ICON" "$OUTPNG" 2>&1)"; RC=$?
LOG="$(stub_log)"
assert_eq 0 "$RC" "exits 0 when generator available"
assert_contains "$LOG" "-size 1024x500"
assert_contains "$LOG" "-alpha remove"
assert_contains "$OUT" "Wrote feature graphic"

it "honors custom gradient colors"
new_stubdir; stub magick
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" "$ICON" "$OUTPNG" "#000000" "#ffffff" 2>&1)"; RC=$?
assert_contains "$(stub_log)" "gradient:#000000-#ffffff"

rm -f "$ICON" "$OUTPNG"
summary
