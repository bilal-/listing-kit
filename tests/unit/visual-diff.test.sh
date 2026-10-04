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
assert_contains "$OUT" "byte-compare only" "notes the fallback"
assert_contains "$OUT" "01.png" "lists screens"
assert_contains "$OUT" "1 unchanged" "counts unchanged"
assert_contains "$OUT" "1 changed" "counts changed"
assert_contains "$OUT" "1 added" "counts added"
assert_contains "$OUT" "1 removed" "counts removed"

# --- ImageMagick 6 (separate compare/identify binaries, no `magick`) ---
it "uses ImageMagick 6 compare/identify when magick is absent"
new_stubdir
cat > "$STUB_BIN/identify" <<'EOF'
#!/usr/bin/env bash
echo "identify $*" >> "$(dirname "$0")/.calls"
printf '10x10'
EOF
cat > "$STUB_BIN/compare" <<'EOF'
#!/usr/bin/env bash
echo "compare $*" >> "$(dirname "$0")/.calls"
case "$*" in *02.png*) echo "42" >&2;; *) echo "0" >&2;; esac
EOF
chmod +x "$STUB_BIN/identify" "$STUB_BIN/compare"
OUT="$(PATH="$STUB_BIN:/usr/bin:/bin" "$BASH_BIN" "$SUT" "$P" "$C" 2>&1)"; RC=$?
assert_eq 0 "$RC" "exits 0"
assert_not_contains "$OUT" "byte-compare only" "pixel mode, not the fallback"
assert_contains "$OUT" "02.png (42 px differ)" "reports the pixel count"
assert_contains "$(stub_log)" "identify -format" "dimensions come from identify"
assert_not_contains "$OUT" "magick" "never calls magick"
rm -rf "$STUB_BIN"

rm -rf "$P" "$C"
summary
