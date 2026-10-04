#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/capture/normalize-screenshot.sh"
IMGINFO="$SCRIPTS/lib/imginfo.py"

# Header-only PNG (imginfo reads the header only): png <path> <w> <h> [colortype=6]
png() { python3 - "$@" <<'PY'
import struct, sys, zlib
p, w, h = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
ct = int(sys.argv[4]) if len(sys.argv) > 4 else 6
ihdr = struct.pack(">IIBBBBB", w, h, 8, ct, 0, 0, 0)
open(p, "wb").write(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr
                    + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr)))
PY
}

TMP="$(mktemp -d)"

it "exits 2 with no args"
OUT="$(bash "$SUT" 2>&1)"; RC=$?
assert_eq 2 "$RC"

it "exits 2 on an unknown mode"
png "$TMP/in.png" 1080 1920
OUT="$(bash "$SUT" "$TMP/in.png" "$TMP/out.png" --bogus 2>&1)"; RC=$?
assert_eq 2 "$RC"

it "exits 3 when ImageMagick is absent"
new_stubdir
OUT="$(PATH="$STUB_BIN" "$BASH_BIN" "$SUT" "$TMP/in.png" "$TMP/out.png" 2>&1)"; RC=$?
assert_eq 3 "$RC"
assert_contains "$OUT" "install"

it "flattens alpha to 8-bit RGB"
new_stubdir; stub magick
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" "$TMP/in.png" "$TMP/out.png" 2>&1)"; RC=$?
LOG="$(stub_log)"
assert_eq 0 "$RC"
assert_contains "$LOG" "-alpha remove -alpha off" "removes alpha"
assert_contains "$LOG" "-depth 8" "forces 8-bit depth"
assert_contains "$LOG" "PNG24:$TMP/out.png" "writes PNG24"
assert_not_contains "$LOG" "-crop" "no crop without --play"

it "--play crops a tall capture to 9:16 from the top"
png "$TMP/tall.png" 1080 2400
new_stubdir; stub magick
PATH="$STUB_BIN:$PATH" bash "$SUT" "$TMP/tall.png" "$TMP/out.png" --play >/dev/null 2>&1
assert_contains "$(stub_log)" "-crop 1080x1920+0+0 +repage"

it "--play crops a wide capture to 16:9"
png "$TMP/wide.png" 2400 1080
new_stubdir; stub magick
PATH="$STUB_BIN:$PATH" bash "$SUT" "$TMP/wide.png" "$TMP/out.png" --play >/dev/null 2>&1
assert_contains "$(stub_log)" "-crop 1920x1080+0+0 +repage"

it "--play leaves a 9:16 capture uncropped"
new_stubdir; stub magick
PATH="$STUB_BIN:$PATH" bash "$SUT" "$TMP/in.png" "$TMP/out.png" --play >/dev/null 2>&1
assert_not_contains "$(stub_log)" "-crop"

# End-to-end with real ImageMagick, when the machine has it.
if command -v magick >/dev/null 2>&1; then
  it "real ImageMagick: RGBA 1080x2400 becomes RGB 1080x1920"
  magick -size 1080x2400 xc:'rgba(255,0,0,0.5)' "PNG32:$TMP/rgba.png"
  bash "$SUT" "$TMP/rgba.png" "$TMP/real.png" --play >/dev/null 2>&1
  INFO="$(python3 "$IMGINFO" "$TMP/real.png" | cut -f1-4)"
  assert_eq "$(printf '1080\t1920\t8\t2')" "$INFO"
fi

it "--play on a non-image fails instead of skipping the crop"
printf 'junk' > "$TMP/junk.png"
new_stubdir; stub magick
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" "$TMP/junk.png" "$TMP/out.png" --play 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "Not a PNG/JPEG"
assert_eq "" "$(stub_log)" "ImageMagick never ran"

summary
