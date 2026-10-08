#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
SUT="$SCRIPTS/capture/capture-ios.sh"
TMP="$(mktemp -d)"
new_stubdir
export CAPTURE_FIXTURE="$TMP/source.png" CAPTURE_VARIATION=0.1
fake_png "$CAPTURE_FIXTURE" 1398 2034
cat > "$STUB_BIN/xcrun" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$CAPTURE_CALLS"
for last; do :; done
cp "$CAPTURE_FIXTURE" "$last"
SH
cat > "$STUB_BIN/magick" <<'SH'
#!/usr/bin/env bash
for last; do :; done
if [ "$last" = info: ]; then
  printf '%s' "$CAPTURE_VARIATION"
else
  [ "${CAPTURE_NORMALIZE_FAIL:-0}" = 0 ] || exit 1
  cp "$CAPTURE_FIXTURE" "${last#PNG24:}"
fi
SH
chmod +x "$STUB_BIN/xcrun" "$STUB_BIN/magick"
export CAPTURE_CALLS="$TMP/calls"
run_capture() { PATH="$STUB_BIN:$PATH" bash "$SUT" "$@"; }

it 'requires an explicit device, display and native size'
OUT="$(run_capture booted primary 1398x2034 "$TMP/out.png" 2>&1)"; RC=$?
assert_eq 2 "$RC"
OUT="$(run_capture UDID '' 1398x2034 "$TMP/out.png" 2>&1)"; RC=$?
assert_eq 2 "$RC"
OUT="$(run_capture UDID primary invalid "$TMP/out.png" 2>&1)"; RC=$?
assert_eq 2 "$RC"

it 'captures the exact display and preserves native geometry'
OUT="$(run_capture UDID primary 1398x2034 "$TMP/out.png" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$(cat "$CAPTURE_CALLS")" 'simctl io UDID screenshot --type=png --display primary'
assert_file "$TMP/out.png"

it 'rejects wrong dimensions without replacing an existing asset'
printf 'previous asset' > "$TMP/out.png"
OUT="$(run_capture UDID primary-1 2007x2853 "$TMP/out.png" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" 'does not match planned'
assert_eq 'previous asset' "$(cat "$TMP/out.png")"

it 'rejects a black or solid inactive display without replacing an asset'
export CAPTURE_VARIATION=0
OUT="$(run_capture UDID primary 1398x2034 "$TMP/out.png" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" 'Blank or solid capture'
assert_eq 'previous asset' "$(cat "$TMP/out.png")"

it 'preserves an existing asset when normalization fails'
export CAPTURE_VARIATION=0.1 CAPTURE_NORMALIZE_FAIL=1
OUT="$(run_capture UDID primary 1398x2034 "$TMP/out.png" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_eq 'previous asset' "$(cat "$TMP/out.png")"
unset CAPTURE_NORMALIZE_FAIL

it 'cleans temporary capture directories after success and failure'
assert_eq 0 "$(find "$TMP" -name '.listing-capture.*' | wc -l | tr -d ' ')"
rm -r "$TMP"
summary
