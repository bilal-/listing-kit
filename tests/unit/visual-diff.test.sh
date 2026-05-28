#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/validate/visual-diff.sh"

it "exits 2 with no args"
OUT="$(bash "$SUT" 2>&1)"; RC=$?
assert_eq 2 "$RC"

it "exits 2 when a directory is missing"
TMP="$(mktemp -d)"
OUT="$(bash "$SUT" /no/such/dir "$TMP" 2>&1)"; RC=$?
assert_eq 2 "$RC"
rm -rf "$TMP"

# --- byte-compare fallback (LK_NO_IMAGEMAGICK) — deterministic, CI-safe ---
# Forces the fallback regardless of whether ImageMagick is installed on the runner.
P="$(mktemp -d)"; C="$(mktemp -d)"
printf 'AAAA' > "$P/01.png"; printf 'AAAA' > "$C/01.png"   # unchanged
printf 'AAAA' > "$P/02.png"; printf 'BBBB' > "$C/02.png"   # changed (bytes differ)
printf 'X'    > "$P/03.png"                                # removed (prev only)
printf 'Y'    > "$C/04.png"                                # added   (cur only)

it "falls back to byte-compare and classifies every screen when ImageMagick is absent"
OUT="$(LK_NO_IMAGEMAGICK=1 bash "$SUT" "$P" "$C" 2>&1)"; RC=$?
assert_eq 0 "$RC" "informational — always exits 0"
assert_contains "$OUT" "byte-compare only"
assert_contains "$OUT" "01.png"
assert_contains "$OUT" "1 unchanged"
assert_contains "$OUT" "1 changed"
assert_contains "$OUT" "1 added"
assert_contains "$OUT" "1 removed"

rm -rf "$P" "$C"
summary
