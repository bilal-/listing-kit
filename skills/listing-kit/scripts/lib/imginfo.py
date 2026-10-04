#!/usr/bin/env python3
"""Image facts for listing validation, read from file headers (no ImageMagick).

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

UNKNOWN = (0, 0, 0, 99)
EXTENSIONS = (".png", ".jpg", ".jpeg")  # deliver/supply upload these (lower-case only on Linux)
SIZES_TSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apple-screenshot-sizes.tsv")


def _png(f):
    d = f.read(33)
    if len(d) < 33 or d[:8] != b"\x89PNG\r\n\x1a\n" or d[8:16] != b"\x00\x00\x00\x0dIHDR":
        return UNKNOWN
    w, h = struct.unpack(">II", d[16:24])
    if not w or not h:
        return UNKNOWN
    depth, ct = d[24], d[25]
    # Walk chunks to the image data. A tRNS chunk adds transparency to RGB/gray;
    # a file that ends (or hits IEND) before any IDAT is truncated, not an image.
    trns = False
    while True:
        head = f.read(8)
        if len(head) < 8:
            return UNKNOWN
        length, kind = struct.unpack(">I4s", head)
        if kind == b"tRNS":
            trns = True
        elif kind == b"IDAT":
            return w, h, depth, f"{ct}+tRNS" if trns else ct
        elif kind == b"IEND":
            return UNKNOWN
        f.seek(length + 4, os.SEEK_CUR)  # data + CRC


def _jpeg(f):
    if f.read(2) != b"\xff\xd8":
        return UNKNOWN
    while True:
        b = f.read(1)
        while b and b != b"\xff":
            b = f.read(1)
        while b == b"\xff":
            b = f.read(1)
        if not b:
            return UNKNOWN
        marker = b[0]
        if marker in (0x01, *range(0xD0, 0xDA)):  # standalone markers, no length
            continue
        seg = f.read(2)
        if len(seg) < 2:
            return UNKNOWN
        length = struct.unpack(">H", seg)[0]
        # SOF0..SOF15 carry the frame size, except DHT (C4), JPG (C8), DAC (CC).
        if length < 2:
            return UNKNOWN
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            d = f.read(length - 2)
            if len(d) < 6:
                return UNKNOWN
            precision, h, w, comps = struct.unpack(">BHHB", d[:6])
            if not w or not h or not comps or len(d) < 6 + 3 * comps:
                return UNKNOWN
            return w, h, precision, {3: 2, 1: 0}.get(comps, 99)
        f.seek(length - 2, os.SEEK_CUR)


def image_info(path):
    """(width, height, bit_depth, color_type) for a PNG or JPEG; UNKNOWN otherwise."""
    try:
        with open(path, "rb") as f:
            sig = f.read(2)
            f.seek(0)
            return _jpeg(f) if sig == b"\xff\xd8" else _png(f)
    except (OSError, struct.error):
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
