#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/lib/imginfo.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

info4() { python3 "$SUT" "$1" | cut -f1-4; }
UNK="$(printf '0\t0\t0\t99')"

# Helper to build exact test PNGs (supports multi-IDAT, Adam7, arbitrary raw bytes).
make_png() {
  python3 - "$@" <<'PY'
import struct, sys, zlib

path, w, h, depth, ct, interlace, mode = (
    sys.argv[1], int(sys.argv[2]), int(sys.argv[3]),
    int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), sys.argv[7]
)
def chunk(k, d):
    return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))

ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ct, 3)
bpp = ch * depth
if interlace == 1:
    passes = [(0,8,0,8),(4,8,0,8),(0,4,4,8),(2,4,0,4),(0,2,2,4),(1,2,0,2),(0,1,1,2)]
    exp = 0
    for x0, dx, y0, dy in passes:
        pw = (w - x0 + dx - 1) // dx if w > x0 else 0
        ph = (h - y0 + dy - 1) // dy if h > y0 else 0
        if pw > 0 and ph > 0:
            exp += ph * (1 + (pw * bpp + 7) // 8)
else:
    exp = h * (1 + (w * bpp + 7) // 8)

if mode == "short":
    raw = b"\x00" * max(0, exp - 1)
elif mode == "long":
    raw = b"\x00" * (exp + 1)
elif mode == "onebyte":
    raw = b"\x00"
else:
    raw = b"\x00" * exp

z = zlib.compress(raw, 1)
ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ct, 0, 0, interlace))
plte = chunk(b"PLTE", b"\x00\x00\x00") if ct == 3 else b""
trns = chunk(b"tRNS", b"\x00" * ({0: 2, 2: 6, 3: 1}.get(ct, 1))) if mode == "trns" else b""

if mode == "split":
    mid = max(1, len(z) // 2)
    idats = chunk(b"IDAT", z[:mid]) + chunk(b"IDAT", z[mid:])
elif mode == "badzlib":
    idats = chunk(b"IDAT", b"\x78\x9c\xff\xff\xff\xff")
elif mode == "trunczlib":
    idats = chunk(b"IDAT", z[:-2])
elif mode == "trailzlib":
    idats = chunk(b"IDAT", z + b"EXTRA")
elif mode == "noidat":
    idats = b""
else:
    idats = chunk(b"IDAT", z)

iend = b"" if mode == "noiend" else (chunk(b"IEND", b"")[:-2] if mode == "trunciend" else chunk(b"IEND", b""))
data = b"\x89PNG\r\n\x1a\n" + ihdr + plte + trns + idats + iend
if mode == "41byte":
    data = b"\x89PNG\r\n\x1a\n" + ihdr + struct.pack(">I4s", 100, b"IDAT")
open(path, "wb").write(data)
PY
}

it "rejects a 41-byte truncated PNG (IHDR + IDAT header only)"
make_png "$TMP/trunc41.png" 1206 2622 8 2 0 41byte
assert_eq 41 "$(wc -c < "$TMP/trunc41.png" | tr -d ' ')" "fixture is 41 bytes"
assert_eq "$UNK" "$(info4 "$TMP/trunc41.png")"

it "rejects PNGs with wrong decompressed byte counts or missing IEND"
for mode in onebyte short long noiend trunciend badzlib trunczlib trailzlib noidat; do
  make_png "$TMP/$mode.png" 32 24 8 2 0 "$mode"
  assert_eq "$UNK" "$(info4 "$TMP/$mode.png")" "reject PNG mode=$mode"
done

it "accepts valid PNGs across color types 0,2,3,4,6 and bit depths"
for spec in "0 1" "0 2" "0 4" "0 8" "0 16" "2 8" "2 16" "3 1" "3 2" "3 4" "3 8" "4 8" "4 16" "6 8" "6 16"; do
  set -- $spec
  ct="$1"; depth="$2"
  make_png "$TMP/ct_${ct}_${depth}.png" 19 13 "$depth" "$ct" 0 ok
  assert_eq "$(printf '19\t13\t%s\t%s' "$depth" "$ct")" "$(info4 "$TMP/ct_${ct}_${depth}.png")" "valid ct=$ct depth=$depth"
done

it "accepts multi-IDAT PNGs and marks tRNS transparency"
make_png "$TMP/split.png" 40 30 8 2 0 split
assert_eq "$(printf '40\t30\t8\t2')" "$(info4 "$TMP/split.png")" "multi-IDAT"
make_png "$TMP/trns3.png" 15 10 4 3 0 trns
assert_eq "$(printf '15\t10\t4\t3+tRNS')" "$(info4 "$TMP/trns3.png")" "palette+tRNS"

it "validates Adam7 interlaced PNGs (including small sizes with empty passes)"
for dims in "1 1" "3 3" "5 7" "17 23" "64 48"; do
  set -- $dims
  make_png "$TMP/adam_${1}x${2}.png" "$1" "$2" 8 2 1 ok
  assert_eq "$(printf '%s\t%s\t8\t2' "$1" "$2")" "$(info4 "$TMP/adam_${1}x${2}.png")" "Adam7 ${1}x${2} RGB8"
done
make_png "$TMP/adam_1bit.png" 13 9 1 0 1 ok
assert_eq "$(printf '13\t9\t1\t0')" "$(info4 "$TMP/adam_1bit.png")" "Adam7 1-bit gray"
make_png "$TMP/adam_short.png" 17 23 8 2 1 short
assert_eq "$UNK" "$(info4 "$TMP/adam_short.png")" "Adam7 1 byte short rejected"
make_png "$TMP/adam_long.png" 17 23 8 2 1 long
assert_eq "$UNK" "$(info4 "$TMP/adam_long.png")" "Adam7 1 byte extra rejected"

it "rejects JPEGs missing SOS or missing EOI, and accepts complete JPEGs"
python3 - "$TMP" <<'PY'
import os, struct, sys
td = sys.argv[1]
sof = b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, 500, 1024, 3) + b"\x01\x11\x00\x02\x11\x00\x03\x11\x00"
sos = b"\xff\xda" + struct.pack(">HB", 12, 3) + b"\x01\x00\x02\x00\x03\x00\x00\x3f\x00"
# 1. No SOS (SOI + SOF0 + EOI)
open(os.path.join(td, "nosos.jpg"), "wb").write(b"\xff\xd8" + sof + b"\xff\xd9")
# 2. No EOI (SOI + SOF0 + SOS + scan data, truncated)
open(os.path.join(td, "noeoi.jpg"), "wb").write(b"\xff\xd8" + sof + sos + b"\x12\x34\xff\x00\x56")
# 3. Empty scan (SOS immediately followed by EOI)
open(os.path.join(td, "emptyscan.jpg"), "wb").write(b"\xff\xd8" + sof + sos + b"\xff\xd9")
# 4. SOS before SOF
open(os.path.join(td, "sosfirst.jpg"), "wb").write(b"\xff\xd8" + sos + b"\x00\xff\xd9")
# 5. Valid baseline JPEG with stuffed 0xFF00 and RST0 marker inside scan
open(os.path.join(td, "valid.jpg"), "wb").write(b"\xff\xd8" + sof + sos + b"\x12\xff\x00\xff\xd0\x34\xff\xd9")
# 6. Valid progressive JPEG (SOF2 + two SOS scans + EOI)
sof2 = b"\xff\xc2" + struct.pack(">HBHHB", 11, 8, 200, 300, 1) + b"\x01\x11\x00"
sos1 = b"\xff\xda" + struct.pack(">HB", 8, 1) + b"\x01\x00\x00\x00\x00"
open(os.path.join(td, "prog.jpg"), "wb").write(b"\xff\xd8" + sof2 + sos1 + b"\xaa" + sos1 + b"\xbb\xff\xd9")
PY

assert_eq "$UNK" "$(info4 "$TMP/nosos.jpg")" "JPEG without SOS rejected"
assert_eq "$UNK" "$(info4 "$TMP/noeoi.jpg")" "JPEG without EOI rejected"
assert_eq "$UNK" "$(info4 "$TMP/emptyscan.jpg")" "JPEG with empty scan rejected"
assert_eq "$UNK" "$(info4 "$TMP/sosfirst.jpg")" "JPEG with SOS before SOF rejected"
assert_eq "$(printf '1024\t500\t8\t2')" "$(info4 "$TMP/valid.jpg")" "valid JPEG with byte stuffing + RST"
assert_eq "$(printf '300\t200\t8\t0')" "$(info4 "$TMP/prog.jpg")" "valid progressive grayscale JPEG"
assert_eq "$UNK" "$(info4 "$TMP/missing.png")" "missing file reports UNKNOWN"

summary
