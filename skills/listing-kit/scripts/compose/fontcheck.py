#!/usr/bin/env python3
"""Which characters a font file can draw, read from its character map (cmap).

Why: on a machine with no system font for a script, a browser draws empty boxes
from the custom font and reports no fallback. So the composer checks every caption
against the declared fonts before rendering. Standard library only; .ttf, .otf and
.ttc (first face). .woff/.woff2 are refused (they need decompression).

CLI: fontcheck.py "<text>" <font>...   -> prints characters none of the fonts has; exit 1 if any
"""
import struct
import sys
import unicodedata


class FontError(Exception):
    pass


def _tables(data):
    tag = data[:4]
    if tag in (b"wOFF", b"wOF2"):
        raise FontError("WOFF fonts are not supported; use the .ttf or .otf file")
    offset = 0
    if tag == b"ttcf":
        offset = struct.unpack(">I", data[12:16])[0]
        tag = data[offset:offset + 4]
    if tag not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        raise FontError("not a TrueType or OpenType font")
    count = struct.unpack(">H", data[offset + 4:offset + 6])[0]
    out = {}
    for i in range(count):
        rec = data[offset + 12 + 16 * i:offset + 28 + 16 * i]
        if len(rec) < 16:
            raise FontError("truncated font")
        name, _, off, length = struct.unpack(">4sIII", rec)
        out[name] = (off, length)
    return out


def _format4(sub):
    seg = struct.unpack(">H", sub[6:8])[0] // 2
    ends = struct.unpack(">%dH" % seg, sub[14:14 + 2 * seg])
    base = 16 + 2 * seg
    starts = struct.unpack(">%dH" % seg, sub[base:base + 2 * seg])
    deltas = struct.unpack(">%dh" % seg, sub[base + 2 * seg:base + 4 * seg])
    ro_at = base + 4 * seg
    offsets = struct.unpack(">%dH" % seg, sub[ro_at:ro_at + 2 * seg])
    found = set()
    for i in range(seg):
        for c in range(starts[i], ends[i] + 1):
            if c == 0xFFFF:
                continue
            if offsets[i] == 0:
                gid = (c + deltas[i]) & 0xFFFF
            else:
                at = ro_at + 2 * i + offsets[i] + 2 * (c - starts[i])
                if at + 2 > len(sub):
                    continue
                gid = struct.unpack(">H", sub[at:at + 2])[0]
                if gid:
                    gid = (gid + deltas[i]) & 0xFFFF
            if gid:
                found.add(c)
    return found


def _format12(sub):
    n = struct.unpack(">I", sub[12:16])[0]
    found = set()
    for i in range(n):
        start, end, gid = struct.unpack(">III", sub[16 + 12 * i:28 + 12 * i])
        if end - start > 0x110000:
            raise FontError("implausible character range")
        found.update(c for c in range(start, end + 1) if gid + (c - start))
    return found


def codepoints(path):
    """The set of Unicode code points the font maps to a glyph."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        raise FontError("cannot read font %s: %s" % (path, e))
    try:
        tables = _tables(data)
        if b"cmap" not in tables:
            raise FontError("font has no character map")
        off, length = tables[b"cmap"]
        cmap = data[off:off + length]
        n = struct.unpack(">H", cmap[2:4])[0]
        best = {}
        for i in range(n):
            plat, enc, sub_off = struct.unpack(">HHI", cmap[4 + 8 * i:12 + 8 * i])
            fmt = struct.unpack(">H", cmap[sub_off:sub_off + 2])[0]
            unicode_table = plat == 0 or (plat == 3 and enc in (1, 10))
            if unicode_table and fmt in (4, 12):
                best[fmt] = cmap[sub_off:]
        if 12 in best:
            return _format12(best[12])
        if 4 in best:
            return _format4(best[4])
        raise FontError("font has no Unicode character map this reader understands")
    except struct.error:
        raise FontError("truncated or damaged font: %s" % path)


def _needs_glyph(ch):
    # Spaces and invisible formatting characters draw nothing; skip them.
    return not (ch.isspace() or unicodedata.category(ch) in ("Cf", "Cc", "Mn", "Me"))


def missing(text, font_paths):
    """Characters in text that none of the fonts can draw, in first-seen order."""
    sets = [codepoints(p) for p in font_paths]
    out = []
    for ch in text:
        if _needs_glyph(ch) and ch not in out and not any(ord(ch) in s for s in sets):
            out.append(ch)
    return out


def describe(ch):
    return "%s (U+%04X %s)" % (ch, ord(ch), unicodedata.name(ch, "unnamed"))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.stderr.write(__doc__)
        sys.exit(2)
    try:
        gone = missing(sys.argv[1], sys.argv[2:])
    except FontError as e:
        sys.stderr.write("fontcheck: %s\n" % e)
        sys.exit(2)
    for ch in gone:
        print(describe(ch))
    sys.exit(1 if gone else 0)
