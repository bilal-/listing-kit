#!/usr/bin/env python3
"""Image facts for listing validation, verified directly from PNG/JPEG streams (no ImageMagick).

CLI:    imginfo.py <file>...
Prints one tab-separated line per file:
    width  height  bit_depth  color_type  bytes  apple_class  path
color_type follows PNG numbering: 2 = RGB (no alpha), 6 = RGBA, 0 = grayscale,
4 = grayscale+alpha, 3 = palette; a PNG with a tRNS (transparency) chunk reports
e.g. "2+tRNS", so it never passes as "2". JPEGs report 2 (3 channels), 0 (1
channel), or 99 (CMYK/other). Unreadable or unknown files report "0 0 0 99". apple_class is
the App Store display class from apple-screenshot-sizes.tsv, or "-".

Also imported by build-review.sh for image_info() and apple_class().
"""
import os
import struct
import sys
import zlib

UNKNOWN = (0, 0, 0, 99)
EXTENSIONS = (".png", ".jpg", ".jpeg")  # deliver/supply upload these (lower-case only on Linux)
SIZES_TSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apple-screenshot-sizes.tsv")
CHUNK = 65536
PNG_FORMATS = {
    0: (1, (1, 2, 4, 8, 16)),
    2: (3, (8, 16)),
    3: (1, (1, 2, 4, 8)),
    4: (2, (8, 16)),
    6: (4, (8, 16)),
}
ADAM7 = (
    (0, 8, 0, 8), (4, 8, 0, 8), (0, 4, 4, 8),
    (2, 4, 0, 4), (0, 2, 2, 4), (1, 2, 0, 2), (0, 1, 1, 2),
)


def _png_expected_bytes(w, h, bpp, interlace):
    if interlace == 0:
        return h * (1 + (w * bpp + 7) // 8)
    total = 0
    for x0, dx, y0, dy in ADAM7:
        pw = (w - x0 + dx - 1) // dx if w > x0 else 0
        ph = (h - y0 + dy - 1) // dy if h > y0 else 0
        if pw > 0 and ph > 0:
            total += ph * (1 + (pw * bpp + 7) // 8)
    return total


def _png(f):
    d = f.read(33)
    if len(d) < 33 or d[:8] != b"\x89PNG\r\n\x1a\n" or d[8:16] != b"\x00\x00\x00\x0dIHDR":
        return UNKNOWN
    if zlib.crc32(d[12:29]) != struct.unpack(">I", d[29:33])[0]:
        return UNKNOWN
    w, h, depth, ct, comp, filt, interlace = struct.unpack(">IIBBBBB", d[16:29])
    if not (0 < w <= 0x7FFFFFFF and 0 < h <= 0x7FFFFFFF):
        return UNKNOWN
    if comp != 0 or filt != 0 or interlace not in (0, 1):
        return UNKNOWN
    fmt = PNG_FORMATS.get(ct)
    if fmt is None or depth not in fmt[1]:
        return UNKNOWN
    expected = _png_expected_bytes(w, h, fmt[0] * depth, interlace)

    trns = False
    saw_idat = False
    saw_plte = False
    total = 0
    dec = zlib.decompressobj()

    while True:
        head = f.read(8)
        if len(head) < 8:
            return UNKNOWN
        length, kind = struct.unpack(">I4s", head)
        if length > 0x7FFFFFFF:
            return UNKNOWN
        crc = zlib.crc32(kind)

        if kind == b"IDAT":
            saw_idat = True
            rem = length
            while rem > 0:
                buf = f.read(min(CHUNK, rem))
                if not buf:
                    return UNKNOWN
                rem -= len(buf)
                crc = zlib.crc32(buf, crc)
                data = buf
                while data:
                    out = dec.decompress(data, CHUNK)
                    total += len(out)
                    if total > expected or dec.unused_data:
                        return UNKNOWN
                    data = dec.unconsumed_tail
            tail = f.read(4)
            if len(tail) < 4 or struct.unpack(">I", tail)[0] != crc:
                return UNKNOWN
        elif kind == b"IEND":
            if length != 0:
                return UNKNOWN
            tail = f.read(4)
            if len(tail) < 4 or struct.unpack(">I", tail)[0] != crc:
                return UNKNOWN
            total += len(dec.flush())
            if (not saw_idat or (ct == 3 and not saw_plte)
                    or not dec.eof or dec.unused_data or total != expected):
                return UNKNOWN
            return w, h, depth, f"{ct}+tRNS" if trns else ct
        else:
            if kind == b"tRNS":
                trns = True
            elif kind == b"PLTE":
                if length == 0 or length > 768 or length % 3 != 0:
                    return UNKNOWN
                saw_plte = True
            rem = length
            while rem > 0:
                buf = f.read(min(CHUNK, rem))
                if not buf:
                    return UNKNOWN
                rem -= len(buf)
                crc = zlib.crc32(buf, crc)
            tail = f.read(4)
            if len(tail) < 4 or struct.unpack(">I", tail)[0] != crc:
                return UNKNOWN


def _scan_entropy(f):
    """Advance past JPEG entropy-coded scan data and return the next marker byte, or None."""
    has_data = False
    carry_ff = False
    while True:
        buf = f.read(CHUNK)
        if not buf:
            return None
        i = 0
        n = len(buf)
        if carry_ff:
            while i < n and buf[i] == 0xFF:
                i += 1
            if i == n:
                continue
            carry_ff = False
            m = buf[i]
            i += 1
            if m == 0x00 or 0xD0 <= m <= 0xD7:
                has_data = True
            else:
                if not has_data:
                    return None
                f.seek(i - n, os.SEEK_CUR)
                return m
        while i < n:
            j = buf.find(b"\xff", i)
            if j == -1:
                has_data = True
                break
            if j > i:
                has_data = True
            k = j + 1
            while k < n and buf[k] == 0xFF:
                k += 1
            if k == n:
                carry_ff = True
                break
            m = buf[k]
            i = k + 1
            if m == 0x00 or 0xD0 <= m <= 0xD7:
                has_data = True
            else:
                if not has_data:
                    return None
                f.seek(i - n, os.SEEK_CUR)
                return m


def _jpeg(f):
    if f.read(2) != b"\xff\xd8":
        return UNKNOWN
    frame = None
    saw_sos = False
    next_marker = None
    while True:
        if next_marker is not None:
            marker, next_marker = next_marker, None
        else:
            b = f.read(1)
            while b and b != b"\xff":
                b = f.read(1)
            while b == b"\xff":
                b = f.read(1)
            if not b:
                return UNKNOWN
            marker = b[0]
        if marker == 0xD9:
            return frame if (frame is not None and saw_sos) else UNKNOWN
        if marker in (0x00, 0xD8):
            return UNKNOWN
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:  # standalone markers, no length
            continue
        seg = f.read(2)
        if len(seg) < 2:
            return UNKNOWN
        length = struct.unpack(">H", seg)[0]
        if length < 2:
            return UNKNOWN
        # SOF0..SOF15 carry the frame size, except DHT (C4), JPG (C8), DAC (CC).
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            d = f.read(length - 2)
            if len(d) < length - 2 or len(d) < 6:
                return UNKNOWN
            precision, h, w, comps = struct.unpack(">BHHB", d[:6])
            if not w or not h or not comps or len(d) < 6 + 3 * comps:
                return UNKNOWN
            frame = (w, h, precision, {3: 2, 1: 0}.get(comps, 99))
        elif marker == 0xDA:
            if frame is None:
                return UNKNOWN
            hdr = f.read(length - 2)
            if len(hdr) < length - 2 or len(hdr) < 4:
                return UNKNOWN
            next_marker = _scan_entropy(f)
            if next_marker is None:
                return UNKNOWN
            saw_sos = True
        else:
            f.seek(length - 2, os.SEEK_CUR)


def image_info(path):
    """(width, height, bit_depth, color_type) for a PNG or JPEG; UNKNOWN otherwise."""
    try:
        with open(path, "rb") as f:
            sig = f.read(2)
            f.seek(0)
            return _jpeg(f) if sig == b"\xff\xd8" else _png(f)
    except (OSError, struct.error, zlib.error):
        return UNKNOWN


def is_image(path):
    return path.lower().endswith(EXTENSIONS)


def _load_apple_sizes():
    sizes = {}
    with open(SIZES_TSV, encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            dims, label = line.rstrip("\n").split("\t")
            w, h = (int(x) for x in dims.split("x"))
            sizes[(min(w, h), max(w, h))] = label
    return sizes


APPLE_SIZES = _load_apple_sizes()


def apple_class(w, h):
    """App Store display class for a screenshot size (either orientation), or None."""
    return APPLE_SIZES.get((min(w, h), max(w, h)))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        w, h, depth, ct = image_info(p)
        size = os.path.getsize(p) if os.path.exists(p) else 0
        print("\t".join(map(str, (w, h, depth, ct, size, apple_class(w, h) or "-", p))))
