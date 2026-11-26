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


def _groups(sub, constant):
    n = struct.unpack(">I", sub[12:16])[0]
    found = set()
    for i in range(n):
        start, end, gid = struct.unpack(">III", sub[16 + 12 * i:28 + 12 * i])
        if not start <= end <= 0x10ffff:
            raise FontError("implausible character range")
        if constant:
            if gid:
                found.update(range(start, end + 1))
        else:
            found.update(range(start + (gid == 0), end + 1))
    return found


def _variations(sub):
    """Map selector to (default bases, bases with a nonzero variant glyph)."""
    count = struct.unpack_from(">I", sub, 6)[0]
    variants = {}
    for i in range(count):
        pos = 10 + 11 * i
        selector = int.from_bytes(sub[pos:pos + 3], "big")
        default, other = struct.unpack_from(">II", sub, pos + 3)
        bases, glyphs = set(), set()
        for offset, stride in ((default, 4), (other, 5)):
            if not offset:
                continue
            rows = struct.unpack_from(">I", sub, offset)[0]
            for j in range(rows):
                at = offset + 4 + j * stride
                base = int.from_bytes(sub[at:at + 3], "big")
                if stride == 4:
                    extra = struct.unpack_from("B", sub, at + 3)[0]
                    bases.update(range(base, base + extra + 1))
                elif struct.unpack_from(">H", sub, at + 3)[0]:
                    glyphs.add(base)
        variants[selector] = (bases, glyphs)
    return variants


def _coverage(path, *, include_format13=True):
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
        points, variants = set(), {}
        understood = False
        for i in range(n):
            plat, enc, sub_off = struct.unpack(">HHI", cmap[4 + 8 * i:12 + 8 * i])
            fmt = struct.unpack(">H", cmap[sub_off:sub_off + 2])[0]
            unicode_table = plat == 0 or (plat == 3 and enc in (1, 10))
            if not unicode_table:
                continue
            sub = cmap[sub_off:]
            if fmt == 14:
                variants.update(_variations(sub))
            if fmt in (4, 12) or (fmt == 13 and include_format13):
                understood = True
                points.update(_format4(sub) if fmt == 4 else _groups(sub, fmt == 13))
        if understood:
            return points, variants
        raise FontError("font has no Unicode character map this reader understands")
    except struct.error:
        raise FontError("truncated or damaged font: %s" % path)


def codepoints(path, *, include_format13=True):
    """Return mapped code points, optionally excluding many-to-one (format 13) cmaps."""
    return _coverage(path, include_format13=include_format13)[0]


def _needs_glyph(ch):
    # Spaces and invisible formatting characters draw nothing; skip them.
    return not (ch.isspace() or unicodedata.category(ch) in ("Cf", "Cc"))


def _selector(cp):
    return 0xfe00 <= cp <= 0xfe0f or 0xe0100 <= cp <= 0xe01ef or cp in (0x180b, 0x180c, 0x180d, 0x180f)


def _variant(base, selector, points, variants):
    if not variants:
        return base in points and selector in points
    defaults, specific = variants.get(selector, ((), ()))
    return base in specific or (base in defaults and base in points)


def missing(text, font_paths):
    """Characters (or selectors of unsupported sequences) in first-seen order."""
    fonts = [_coverage(p) for p in font_paths]
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        cp = ord(ch)
        i += 1
        supported = any(cp in points for points, _ in fonts)
        if i < len(text) and _selector(ord(text[i])):
            selector = ord(text[i])
            if any(_variant(cp, selector, points, variants) for points, variants in fonts):
                i += 1
                continue
            if not supported and _needs_glyph(ch) and ch not in out:
                out.append(ch)
            ch, supported = text[i], False
            i += 1
        if not supported and _needs_glyph(ch) and ch not in out:
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
