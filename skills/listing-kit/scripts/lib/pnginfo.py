#!/usr/bin/env python3
"""PNG facts for listing validation, read from the IHDR chunk (no ImageMagick).

CLI:    pnginfo.py <file>...
Prints one tab-separated line per file:
    width  height  bit_depth  color_type  bytes  apple_class  path
color_type 2 = RGB (no alpha), 6 = RGBA; a non-PNG reports "0 0 0 99". apple_class
is the App Store display class from apple-screenshot-sizes.tsv, or "-".

Also imported by build-review.sh for png_info() and apple_class().
"""
import os
import struct
import sys

NOT_PNG = (0, 0, 0, 99)
SIZES_TSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apple-screenshot-sizes.tsv")


def png_info(path):
    """(width, height, bit_depth, color_type); NOT_PNG if unreadable or not a PNG."""
    try:
        with open(path, "rb") as f:
            d = f.read(26)
    except OSError:
        return NOT_PNG
    if len(d) < 26 or d[:8] != b"\x89PNG\r\n\x1a\n":
        return NOT_PNG
    w, h = struct.unpack(">II", d[16:24])
    return w, h, d[24], d[25]


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
        w, h, depth, ct = png_info(p)
        size = os.path.getsize(p) if os.path.exists(p) else 0
        print("\t".join(map(str, (w, h, depth, ct, size, apple_class(w, h) or "-", p))))
