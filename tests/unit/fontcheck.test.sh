#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/compose/fontcheck.py"
T="$(mktemp -d)"; [ -n "$T" ] && [ -d "$T" ] || { echo "mktemp failed" >&2; exit 1; }
trap 'rm -rf "$T"' EXIT

# A minimal font holding only a character map: format 4 (A-Z, a-z, digits) or
# format 12 (adds one character outside the basic plane).
python3 - "$T" <<'PY'
import struct, sys, os
def font(sub, tag=b"\x00\x01\x00\x00"):
    cmap = struct.pack(">HH", 0, 1) + struct.pack(">HHI", 3, 10 if sub[1] == 12 else 1, 12) + sub
    return tag + struct.pack(">HHHH", 1, 16, 0, 0) + struct.pack(">4sIII", b"cmap", 0, 28, len(cmap)) + cmap
def fmt4(ranges):
    ranges = ranges + [(0xFFFF, 0xFFFF)]
    n = len(ranges)
    ends = b"".join(struct.pack(">H", e) for _, e in ranges)
    starts = b"".join(struct.pack(">H", s) for s, _ in ranges)
    deltas = b"".join(struct.pack(">h", 1 if s != 0xFFFF else 1) for s, _ in ranges)
    offs = struct.pack(">%dH" % n, *([0] * n))
    body = struct.pack(">HHHH", n * 2, 0, 0, 0) + ends + b"\0\0" + starts + deltas + offs
    return struct.pack(">HHH", 4, 6 + len(body), 0) + body
def fmt12(groups):
    body = b"".join(struct.pack(">III", s, e, 1) for s, e in groups)
    return struct.pack(">HHIII", 12, 0, 16 + len(body), 0, len(groups)) + body
latin = [(0x30, 0x39), (0x41, 0x5A), (0x61, 0x7A)]
open(os.path.join(sys.argv[1], "latin.ttf"), "wb").write(font(fmt4(latin)))
open(os.path.join(sys.argv[1], "emoji.otf"), "wb").write(font(fmt12([(0x1F600, 0x1F600), (0xB7, 0xB7)]), b"OTTO"))
open(os.path.join(sys.argv[1], "web.woff2"), "wb").write(b"wOF2" + b"\0" * 40)
open(os.path.join(sys.argv[1], "cut.ttf"), "wb").write(font(fmt4(latin))[:40])
PY

it "text fully covered by the font passes with no output"
OUT="$(python3 "$SUT" "Every agent one list 42" "$T/latin.ttf")"; RC=$?
assert_eq 0 "$RC" "exit 0"
assert_eq "" "$OUT" "nothing missing"

it "a character the font lacks is named with its code point, and the exit code is 1"
OUT="$(python3 "$SUT" "Fast · simple" "$T/latin.ttf")"; RC=$?
assert_eq 1 "$RC" "exit 1"
assert_contains "$OUT" "U+00B7 MIDDLE DOT"
assert_eq 1 "$(printf '%s\n' "$OUT" | wc -l | tr -d ' ')" "each missing character is listed once"

it "a later font in the list supplies what the first lacks, including outside the basic plane"
OUT="$(python3 "$SUT" "Fast · simple 😀" "$T/latin.ttf" "$T/emoji.otf")"; RC=$?
assert_eq 0 "$RC" "exit 0 with the fallback font"
OUT="$(python3 "$SUT" "😀" "$T/latin.ttf")"; assert_contains "$OUT" "U+1F600"

it "spaces and invisible formatting characters need no glyph"
OUT="$(python3 "$SUT" "$(printf 'a b\tc\xe2\x80\x8fd')" "$T/latin.ttf")"; RC=$?
assert_eq 0 "$RC" "exit 0"

it "text in a script the font lacks reports every distinct character"
OUT="$(python3 "$SUT" "すべて" "$T/latin.ttf")"
assert_eq 3 "$(printf '%s\n' "$OUT" | wc -l | tr -d ' ')" "three characters"

it "WOFF, truncated and non-font files are refused with exit 2, not treated as empty fonts"
OUT="$(python3 "$SUT" "a" "$T/web.woff2" 2>&1)"; assert_eq 2 "$?" "woff2"; assert_contains "$OUT" "WOFF"
python3 "$SUT" "a" "$T/cut.ttf" >/dev/null 2>&1; assert_eq 2 "$?" "truncated"
python3 "$SUT" "a" "$ROOT/README.md" >/dev/null 2>&1; assert_eq 2 "$?" "not a font"
python3 "$SUT" "a" "$T/absent.ttf" >/dev/null 2>&1; assert_eq 2 "$?" "missing file"

summary
