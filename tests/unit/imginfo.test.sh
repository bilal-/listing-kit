#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/lib/imginfo.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

info4() { python3 "$SUT" "$1" | cut -f1-4; }
dec1()  { python3 "$SUT" --decode "$1" | cut -f1; }
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
    pass_spans = []
    for x0, dx, y0, dy in passes:
        pw = (w - x0 + dx - 1) // dx if w > x0 else 0
        ph = (h - y0 + dy - 1) // dy if h > y0 else 0
        if pw > 0 and ph > 0:
            stride = 1 + (pw * bpp + 7) // 8
            pass_spans.append((exp, ph, stride))
            exp += ph * stride
else:
    stride = 1 + (w * bpp + 7) // 8
    pass_spans = [(0, h, stride)]
    exp = h * stride

if mode == "short":
    raw = b"\x00" * max(0, exp - 1)
elif mode == "long":
    raw = b"\x00" * (exp + 1)
elif mode == "onebyte":
    raw = b"\x00"
elif mode == "filters04":
    buf = bytearray(exp)
    fval = 0
    for start, ph, st in pass_spans:
        for r in range(ph):
            buf[start + r * st] = fval % 5
            fval += 1
    raw = bytes(buf)
elif mode == "badfilter0":
    buf = bytearray(exp)
    buf[0] = 5
    raw = bytes(buf)
elif mode == "badfilter_last":
    buf = bytearray(exp)
    start, ph, st = pass_spans[-1]
    buf[start + (ph - 1) * st] = 5
    raw = bytes(buf)
else:
    raw = b"\x00" * exp

z = zlib.compress(raw, 1)
ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ct, 0, 0, interlace))
plte = chunk(b"PLTE", b"\x00\x00\x00") if ct == 3 else b""
trns = chunk(b"tRNS", b"\x00" * ({0: 2, 2: 6, 3: 1}.get(ct, 1))) if mode == "trns" else b""

if mode == "split":
    mid = max(1, len(z) // 2)
    idats = chunk(b"IDAT", z[:mid]) + chunk(b"IDAT", z[mid:])
elif mode == "intervening_text":
    mid = max(1, len(z) // 2)
    idats = chunk(b"IDAT", z[:mid]) + chunk(b"tEXt", b"Comment\x00hi") + chunk(b"IDAT", z[mid:])
elif mode == "badzlib":
    idats = chunk(b"IDAT", b"\x78\x9c\xff\xff\xff\xff")
elif mode == "trunczlib":
    idats = chunk(b"IDAT", z[:-2])
elif mode == "pad4":
    idats = chunk(b"IDAT", z + b"\x00\x00\x00\x00")
elif mode == "trailzlib":
    idats = chunk(b"IDAT", z + b"EXTRA")
elif mode == "pad_nonfinal":
    idats = chunk(b"IDAT", z + b"\x00\x00\x00\x00") + chunk(b"IDAT", b"\x00")
elif mode == "pad_badcrc":
    d = z + b"\x00\x00\x00\x00"
    idats = struct.pack(">I", len(d)) + b"IDAT" + d + struct.pack(">I", (zlib.crc32(b"IDAT" + d) ^ 1))
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
for mode in onebyte short long noiend trunciend badzlib trunczlib noidat; do
  make_png "$TMP/$mode.png" 32 24 8 2 0 "$mode"
  assert_eq "$UNK" "$(info4 "$TMP/$mode.png")" "reject PNG mode=$mode"
done

it "tolerates padding at the end of the final IDAT while checking CRCs and rejecting non-final padding"
make_png "$TMP/pad4.png" 32 24 8 2 0 pad4
assert_eq "$(printf '32\t24\t8\t2')" "$(info4 "$TMP/pad4.png")" "4 padding bytes in final IDAT accepted"
make_png "$TMP/trailzlib.png" 32 24 8 2 0 trailzlib
assert_eq "$(printf '32\t24\t8\t2')" "$(info4 "$TMP/trailzlib.png")" "trailing bytes in final IDAT accepted"
make_png "$TMP/pad_nonfinal.png" 32 24 8 2 0 pad_nonfinal
assert_eq "$UNK" "$(info4 "$TMP/pad_nonfinal.png")" "padding before another IDAT rejected"
make_png "$TMP/pad_badcrc.png" 32 24 8 2 0 pad_badcrc
assert_eq "$UNK" "$(info4 "$TMP/pad_badcrc.png")" "corrupt CRC in padded final IDAT rejected"

it "validates PNG filter bytes (0-4) across every row and Adam7 pass"
make_png "$TMP/filters04.png" 17 19 8 2 0 filters04
assert_eq "$(printf '17\t19\t8\t2')" "$(info4 "$TMP/filters04.png")" "filters 0..4 accepted"
make_png "$TMP/filters04_adam.png" 17 19 8 2 1 filters04
assert_eq "$(printf '17\t19\t8\t2')" "$(info4 "$TMP/filters04_adam.png")" "Adam7 filters 0..4 accepted"
make_png "$TMP/badfilter0.png" 4 3 8 2 0 badfilter0
assert_eq "$UNK" "$(info4 "$TMP/badfilter0.png")" "invalid filter on first row rejected"
make_png "$TMP/badfilter_last.png" 4 3 8 2 0 badfilter_last
assert_eq "$UNK" "$(info4 "$TMP/badfilter_last.png")" "invalid filter on last row rejected"
make_png "$TMP/badfilter_adam.png" 5 7 8 2 1 badfilter_last
assert_eq "$UNK" "$(info4 "$TMP/badfilter_adam.png")" "invalid filter in final Adam7 pass rejected"

it "enforces consecutive IDATs and valid PLTE/tRNS/critical chunk placement"
make_png "$TMP/intervening_text.png" 4 3 8 2 0 intervening_text
assert_eq "$UNK" "$(info4 "$TMP/intervening_text.png")" "tEXt between IDAT chunks rejected"
python3 - "$TMP" <<'PY'
import os, struct, sys, zlib
td = sys.argv[1]
def chunk(k, d):
    return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))
sig = b"\x89PNG\r\n\x1a\n"
iend = chunk(b"IEND", b"")

def write_png(name, w, h, depth, ct, body_chunks):
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ct, 0, 0, 0))
    open(os.path.join(td, name), "wb").write(sig + ihdr + b"".join(body_chunks) + iend)

idat_rgb = chunk(b"IDAT", zlib.compress(b"\x00" * (2 * (1 + 2 * 3))))
idat_rgba = chunk(b"IDAT", zlib.compress(b"\x00" * (2 * (1 + 2 * 4))))
idat_ga = chunk(b"IDAT", zlib.compress(b"\x00" * (2 * (1 + 2 * 2))))
idat_gray = chunk(b"IDAT", zlib.compress(b"\x00" * (2 * (1 + 2 * 1))))
idat_idx1 = chunk(b"IDAT", zlib.compress(b"\x00" * (2 * (1 + 1))))

# tRNS on ct=6 and ct=4
write_png("trns_ct6.png", 2, 2, 8, 6, [chunk(b"tRNS", b"\x00\x00"), idat_rgba])
write_png("trns_ct4.png", 2, 2, 8, 4, [chunk(b"tRNS", b"\x00\x00"), idat_ga])
# wrong tRNS length for ct=0 (must be 2) and ct=2 (must be 6)
write_png("trns_ct0_len.png", 2, 2, 8, 0, [chunk(b"tRNS", b"\x00\x00\x00\x00\x00\x00"), idat_gray])
write_png("trns_ct2_len.png", 2, 2, 8, 2, [chunk(b"tRNS", b"\x00\x00"), idat_rgb])
# tRNS before PLTE and tRNS exceeding PLTE entry count on ct=3
write_png("trns_before_plte.png", 2, 2, 1, 3, [chunk(b"tRNS", b"\x00"), chunk(b"PLTE", b"\x00\x00\x00"), idat_idx1])
write_png("trns_over_plte.png", 2, 2, 1, 3, [chunk(b"PLTE", b"\x00\x00\x00"), chunk(b"tRNS", b"\x00\x00"), idat_idx1])
# PLTE on ct=0, PLTE after IDAT, tRNS after IDAT, PLTE > 2^depth on ct=3, unknown critical chunk
write_png("plte_ct0.png", 2, 2, 8, 0, [chunk(b"PLTE", b"\x00\x00\x00"), idat_gray])
write_png("rgb_trns_before_plte.png", 2, 2, 8, 2, [chunk(b"tRNS", bytes(6)), chunk(b"PLTE", bytes(3)), idat_rgb])
write_png("animated.png", 2, 2, 8, 2, [chunk(b"acTL", struct.pack(">II", 1, 0)), idat_rgb])
write_png("plte_after_idat.png", 2, 2, 8, 2, [idat_rgb, chunk(b"PLTE", b"\x00\x00\x00")])
write_png("trns_after_idat.png", 2, 2, 8, 2, [idat_rgb, chunk(b"tRNS", b"\x00" * 6)])
write_png("plte_over_depth.png", 2, 2, 1, 3, [chunk(b"PLTE", b"\x00\x00\x00" * 3), idat_idx1])
write_png("unknown_crit.png", 2, 2, 8, 2, [chunk(b"ABCD", b"x"), idat_rgb])
PY
for f in trns_ct6 trns_ct4 trns_ct0_len trns_ct2_len trns_before_plte trns_over_plte \
         rgb_trns_before_plte plte_ct0 plte_after_idat trns_after_idat plte_over_depth unknown_crit; do
  assert_eq "$UNK" "$(info4 "$TMP/$f.png")" "reject $f"
done

it "reports animated PNGs as unsuitable for a static listing"
assert_eq "$UNK" "$(info4 "$TMP/animated.png")"
assert_contains "$(python3 "$SUT" --validate "$TMP/animated.png")" "animated PNG"

it "refuses PNGs exceeding the 64-megapixel cap before inflating"
python3 - "$TMP" <<'PY'
import os, struct, sys, zlib
td = sys.argv[1]
def chunk(k, d):
    return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))
sig = b"\x89PNG\r\n\x1a\n"
def make_1bit(name, w, h):
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 1, 0, 0, 0, 0))
    comp = zlib.compressobj(1)
    row = b"\x00" * (1 + (w + 7) // 8)
    blk = row * 64
    z = bytearray()
    for _ in range(h // 64):
        z.extend(comp.compress(blk))
    if h % 64:
        z.extend(comp.compress(row * (h % 64)))
    z.extend(comp.flush())
    open(os.path.join(td, name), "wb").write(sig + ihdr + chunk(b"IDAT", bytes(z)) + chunk(b"IEND", b""))

# 8001 * 8000 = 64,008,000 > 64,000,000 (valid zlib stream, so only pixel cap rejects it)
make_1bit("over64mp.png", 8001, 8000)
# 8000 * 8000 = 64,000,000 (exact 64MP boundary is accepted)
make_1bit("exact64mp.png", 8000, 8000)
PY
assert_eq "$UNK" "$(info4 "$TMP/over64mp.png")" "8001x8000 (>64MP) rejected"
assert_eq "$(printf '8000\t8000\t1\t0')" "$(info4 "$TMP/exact64mp.png")" "8000x8000 (exact 64MP) accepted"
NO_INFLATE="$(python3 - "$SCRIPTS/lib" <<'PY'
import io, struct, sys, zlib
sys.path.insert(0, sys.argv[1])
import imginfo
ihdr = struct.pack(">IIBBBBB", 50000, 50000, 16, 6, 0, 0, 0)
head = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
class GuardStream:
    def __init__(self, b): self.b = b; self.done = False
    def read(self, n=-1):
        if self.done: raise RuntimeError("read past IHDR on >64MP image")
        self.done = True
        return self.b[:n]
print("\t".join(map(str, imginfo._png(GuardStream(head)))))
PY
2>&1)"
assert_eq "$UNK" "$NO_INFLATE" "stops immediately after IHDR without reading IDAT"

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

it "validates JPEG marker framing, DQT/DHT/DAC tables, byte stuffing, restart markers, and SOF/SOS lengths"
python3 - "$TMP" <<'PY'
import os, struct, sys
td = sys.argv[1]
def seg(m, d): return b"\xff" + bytes([m]) + struct.pack(">H", len(d) + 2) + d
dqt0 = seg(0xDB, b"\x00" + b"\x10" * 64)
dqt1 = seg(0xDB, b"\x01" + b"\x10" * 64)
dht_dc0 = seg(0xC4, b"\x00\x01" + b"\x00" * 15 + b"\x00")
dht_ac0 = seg(0xC4, b"\x10\x01" + b"\x00" * 15 + b"\x00")
dht0 = dht_dc0 + dht_ac0

sof = b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, 500, 1024, 3) + b"\x01\x11\x00\x02\x11\x00\x03\x11\x00"
sos = b"\xff\xda" + struct.pack(">HB", 12, 3) + b"\x01\x00\x02\x00\x03\x00\x00\x3f\x00"
sof2 = b"\xff\xc2" + struct.pack(">HBHHB", 11, 8, 200, 300, 1) + b"\x01\x11\x00"
sos_dc = b"\xff\xda" + struct.pack(">HB", 8, 1) + b"\x01\x00\x00\x00\x00"
sos_ac = b"\xff\xda" + struct.pack(">HB", 8, 1) + b"\x01\x00\x01\x3f\x00"

# Negative cases: missing SOS, missing EOI, empty scan, SOS first
open(os.path.join(td, "nosos.jpg"), "wb").write(b"\xff\xd8" + dqt0 + dht0 + sof + b"\xff\xd9")
open(os.path.join(td, "noeoi.jpg"), "wb").write(b"\xff\xd8" + dqt0 + dht0 + sof + sos + b"\x12\x34\xff\x00\x56")
open(os.path.join(td, "emptyscan.jpg"), "wb").write(b"\xff\xd8" + dqt0 + dht0 + sof + sos + b"\xff\xd9")
open(os.path.join(td, "sosfirst.jpg"), "wb").write(b"\xff\xd8" + dqt0 + dht0 + sos + b"\x00\xff\xd9")

# Retained Codex 1 negative fixtures: SOF+SOS without DQT/DHT
open(os.path.join(td, "notables_base.jpg"), "wb").write(b"\xff\xd8" + sof + sos + b"\x12\xff\x00\xff\xd0\x34\xff\xd9")
open(os.path.join(td, "notables_prog.jpg"), "wb").write(b"\xff\xd8" + sof2 + sos_dc + b"\xaa" + sos_dc + b"\xbb\xff\xd9")
# Missing DHT only, missing DQT only, mismatched DQT id, mismatched DHT id
open(os.path.join(td, "nodht.jpg"), "wb").write(b"\xff\xd8" + dqt0 + sof + sos + b"\x00\xff\xd9")
open(os.path.join(td, "nodqt.jpg"), "wb").write(b"\xff\xd8" + dht0 + sof + sos + b"\x00\xff\xd9")
open(os.path.join(td, "wrongdqt.jpg"), "wb").write(b"\xff\xd8" + dqt1 + dht0 + sof + sos + b"\x00\xff\xd9")
sos_ta1 = b"\xff\xda" + struct.pack(">HB", 12, 3) + b"\x01\x01\x02\x00\x03\x00\x00\x3f\x00"
open(os.path.join(td, "wrongdht.jpg"), "wb").write(b"\xff\xd8" + dqt0 + dht0 + sof + sos_ta1 + b"\x00\xff\xd9")
# Arithmetic SOF9 with default or explicit conditioning tables
sof9 = seg(0xC9, struct.pack(">BHHB", 8, 40, 60, 1) + b"\x01\x11\x00")
sos9 = seg(0xDA, b"\x01\x01\x00\x00\x3f\x00")
dac = seg(0xCC, b"\x00\x01\x10\x05")
open(os.path.join(td, "arith_nodac.jpg"), "wb").write(b"\xff\xd8" + dqt0 + sof9 + sos9 + b"\x00\xff\xd9")
open(os.path.join(td, "arith_ok.jpg"), "wb").write(b"\xff\xd8" + dqt0 + dac + sof9 + sos9 + b"\x00\xff\xd9")

# Gemini 1: non-0xFF garbage between markers
open(os.path.join(td, "garbage.jpg"), "wb").write(b"\xff\xd8CORRUPT" + dqt0 + dht0 + sof + sos + b"\x01\xff\xd9")

# Gemini 2: illegal 0xFF 0xFF 0x00 stuffing (inline and across 65536 CHUNK boundary) and RST-only empty scan
open(os.path.join(td, "ff_ff_00.jpg"), "wb").write(b"\xff\xd8" + dqt0 + dht0 + sof + sos + b"\x12\xff\xff\x00\xff\xd9")
prefix = b"\xff\xd8" + dqt0 + dht0 + sof + sos
pad_len = 65536 - (len(prefix) % 65536) - 1
open(os.path.join(td, "ff_ff_00_chunk.jpg"), "wb").write(prefix + b"\x12" * pad_len + b"\xff\xff\x00\xff\xd9")
open(os.path.join(td, "rst_only.jpg"), "wb").write(b"\xff\xd8" + dqt0 + dht0 + sof + sos + b"\xff\xd0\xff\xd9")

# Gemini 3: bad SOF length (extra byte) and bad SOS length (Ns=0, or Ns=3 with length=8)
bad_sof = seg(0xC0, struct.pack(">BHHB", 8, 500, 1024, 3) + b"\x01\x11\x00\x02\x11\x00\x03\x11\x00\x99")
open(os.path.join(td, "badsof_len.jpg"), "wb").write(b"\xff\xd8" + dqt0 + dht0 + bad_sof + sos + b"\x01\xff\xd9")
bad_sos_ns0 = b"\xff\xda\x00\x06\x00\x00\x3f\x00"
open(os.path.join(td, "badsos_ns0.jpg"), "wb").write(b"\xff\xd8" + dqt0 + dht0 + sof + bad_sos_ns0 + b"\x01\xff\xd9")
bad_sos_trunc = b"\xff\xda\x00\x08\x03\x01\x00\x00\x3f\x00"
open(os.path.join(td, "badsos_trunc.jpg"), "wb").write(b"\xff\xd8" + dqt0 + dht0 + sof + bad_sos_trunc + b"\x01\xff\xd9")

# Positive cases: valid baseline with stuffed 0xFF00 and fill-prefixed RST0, and progressive with per-scan DHT
open(os.path.join(td, "valid_rst.jpg"), "wb").write(
    b"\xff\xd8" + dqt0 + dht0 + sof + sos + b"\x12\xff\x00\xff\xff\xd0\x34\xff\xd9"
)
open(os.path.join(td, "prog_ok.jpg"), "wb").write(
    b"\xff\xd8" + dqt0 + sof2 + dht_dc0 + sos_dc + b"\xaa" + dht_ac0 + sos_ac + b"\xbb\xff\xd9"
)
PY

for bad in nosos noeoi emptyscan sosfirst notables_base notables_prog nodht nodqt wrongdqt wrongdht \
           garbage ff_ff_00 ff_ff_00_chunk rst_only badsof_len badsos_ns0 badsos_trunc; do
  assert_eq "$UNK" "$(info4 "$TMP/$bad.jpg")" "reject JPEG $bad"
done
assert_eq "$(printf '1024\t500\t8\t2')" "$(info4 "$TMP/valid_rst.jpg")" "valid JPEG with byte stuffing + fill RST0"
assert_eq "$(printf '300\t200\t8\t0')" "$(info4 "$TMP/prog_ok.jpg")" "valid progressive JPEG with per-scan DHT"
assert_eq "$(printf '60\t40\t8\t0')" "$(info4 "$TMP/arith_ok.jpg")" "arithmetic JPEG with DQT + DAC"
assert_eq "$(printf '60\t40\t8\t0')" "$(info4 "$TMP/arith_nodac.jpg")" "arithmetic JPEG with default tables"
assert_eq "65535" "$(python3 - "$TMP/ff_ff_00_chunk.jpg" <<'PYOFFSET'
import sys
data = open(sys.argv[1], "rb").read()
sos = data.index(b"\xff\xda") + 2
start = sos + int.from_bytes(data[sos:sos + 2], "big")
print(data.index(b"\xff\xff\x00", start) - start)
PYOFFSET
)" "first FF is the last byte in the first entropy read"
assert_eq "$UNK" "$(info4 "$TMP/missing.png")" "missing file reports UNKNOWN"

it "fake_jpeg pads unused final bits with 1s per T.81 on odd MCU counts"
fake_jpeg "$TMP/one_mcu.jpg" 1 1
assert_eq "$(printf '1\t1\t8\t2')" "$(info4 "$TMP/one_mcu.jpg")" "1x1 fake_jpeg recognized"
TAIL_HEX="$(python3 -c 'import sys;print(open(sys.argv[1],"rb").read()[-4:].hex())' "$TMP/one_mcu.jpg")"
assert_eq "000fffd9" "$TAIL_HEX" "12-bit 1x1 scan ends in 00 0f before EOI"

it "decodes() and --decode report ok / bad / unavailable via ImageMagick stubs and real tool"
fake_png "$TMP/good.png" 16 16
assert_eq "unavailable" "$(LK_NO_IMAGEMAGICK=1 dec1 "$TMP/good.png")" "LK_NO_IMAGEMAGICK returns unavailable"

# Empty PATH stub (only python3 symlinked so no magick/convert/identify exists)
PY_BIN="$(command -v python3)"
NOIM_BIN="$(mktemp -d)"; STUB_DIRS+=("$NOIM_BIN")
ln -s "$PY_BIN" "$NOIM_BIN/python3"
assert_eq "unavailable" "$(PATH="$NOIM_BIN" "$PY_BIN" "$SUT" --decode "$TMP/good.png" | cut -f1)" "PATH without IM returns unavailable"

# Stub magick: ok on exit 0, bad on exit 1, bad when warning emitted on stderr with exit 0
new_stubdir
ln -s "$PY_BIN" "$STUB_BIN/python3"
cat > "$STUB_BIN/magick" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *warn.png*) echo "Corrupt JPEG data: premature end of data segment" >&2; exit 0;;
  *bad.png*) exit 1;;
  *) exit 0;;
esac
EOF
chmod +x "$STUB_BIN/magick"
cp "$TMP/good.png" "$TMP/warn.png"; cp "$TMP/good.png" "$TMP/bad.png"
DEC_MULTI="$(PATH="$STUB_BIN:/bin:/usr/bin" "$PY_BIN" "$SUT" --decode "$TMP/good.png" "$TMP/warn.png" "$TMP/bad.png")"
assert_contains "$DEC_MULTI" "$(printf 'ok\t%s' "$TMP/good.png")" "magick stub ok"
assert_contains "$DEC_MULTI" "$(printf 'bad\t%s' "$TMP/warn.png")" "magick warning treated as bad"
assert_contains "$DEC_MULTI" "$(printf 'bad\t%s' "$TMP/bad.png")" "magick exit 1 treated as bad"

IM6_BIN="$(mktemp -d)"; STUB_DIRS+=("$IM6_BIN")
cp "$TMP/good.png" "$TMP/good two.png"
for decoder in convert identify; do
  cat > "$IM6_BIN/$decoder" <<'EOF'
#!/bin/sh
printf '%s\n' "$@" >> "$ARG_LOG"
EOF
  chmod +x "$IM6_BIN/$decoder"
  ARG_LOG="$TMP/args" PATH="$IM6_BIN" "$PY_BIN" "$SUT" --decode "$TMP/good.png" "$TMP/good two.png" > "$TMP/status"
  assert_eq "$(printf 'ok\t%s\nok\t%s' "$TMP/good.png" "$TMP/good two.png")" "$(cat "$TMP/status")"
  if [ "$decoder" = convert ]; then
    expected="$(printf '%s\n' "$TMP/good.png" "$TMP/good two.png" 'null:')"
  else
    expected="$(printf '%s\n' -verbose "$TMP/good.png" "$TMP/good two.png")"
  fi
  assert_eq "$expected" "$(cat "$TMP/args")" "$decoder fully decodes both files in one command"
  rm "$TMP/args" "$IM6_BIN/$decoder"
done

it "bounds decoder invocations by file and pixel count, bisecting only failed batches"
cat > "$IM6_BIN/magick" <<'EOF'
#!/bin/sh
count=0
rc=0
for arg do
  case "$arg" in *.png|*.jpg) count=$((count+1));; esac
  case "$arg" in */bad.png) rc=1;; esac
done
echo "$count" >> "$ARG_LOG"
exit "$rc"
EOF
chmod +x "$IM6_BIN/magick"
batch_sizes(){
  : > "$TMP/sizes"
  ARG_LOG="$TMP/sizes" PATH="$IM6_BIN" "$PY_BIN" "$SUT" --decode "$@" > "$TMP/status"
  paste -sd, "$TMP/sizes"
}
args=()
for ((i=0;i<17;i++)); do args+=("$TMP/good.png"); done
assert_eq '16,1' "$(batch_sizes "${args[@]}")" "16-file cap"
fake_jpeg "$TMP/large.jpg" 8000 8000
assert_eq '3,1' "$(batch_sizes "$TMP/large.jpg" "$TMP/large.jpg" "$TMP/large.jpg" "$TMP/large.jpg")" "200 MP cap"
args[0]="$TMP/bad.png"
assert_eq '8,4,2,1,1,2,4' "$(batch_sizes "${args[@]:0:8}")" "bisect eight files with one failure"
assert_eq 1 "$(grep -c '^bad' "$TMP/status")" "isolate only the bad file"

if command -v magick >/dev/null 2>&1 || command -v convert >/dev/null 2>&1; then
  assert_eq "ok" "$(dec1 "$TMP/good.png")" "real IM decodes fake_png"
  assert_eq "ok" "$(dec1 "$TMP/one_mcu.jpg")" "real IM decodes 1x1 fake_jpeg"
  assert_eq "ok" "$(dec1 "$TMP/pad4.png")" "real IM fully decodes padded final IDAT"
  # Structurally framed 64x64 JPEG whose 1-byte scan triggers Corrupt JPEG data warning
  python3 - "$TMP/short_scan.jpg" <<'PY'
import struct, sys
def seg(m, d): return b"\xff" + bytes([m]) + struct.pack(">H", len(d) + 2) + d
dqt = seg(0xDB, b"\x00" + b"\x10" * 64)
sof = seg(0xC0, struct.pack(">BHHB", 8, 64, 64, 3) + b"\x01\x22\x00\x02\x11\x00\x03\x11\x00")
dht = seg(0xC4, b"\x00\x01" + b"\x00" * 15 + b"\x00") + seg(0xC4, b"\x10\x01" + b"\x00" * 15 + b"\x00")
sos = seg(0xDA, b"\x03\x01\x00\x02\x00\x03\x00\x00\x3f\x00")
open(sys.argv[1], "wb").write(b"\xff\xd8" + dqt + sof + dht + sos + b"\x01\xff\xd9")
PY
  assert_eq "$(printf '64\t64\t8\t2')" "$(info4 "$TMP/short_scan.jpg")" "structural check reads framed header"
  assert_eq "bad" "$(dec1 "$TMP/short_scan.jpg")" "real IM rejects premature end of JPEG scan"
fi

summary
