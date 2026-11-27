"""Contrast against a Chromium screenshot (8-bit, non-interlaced RGB/RGBA PNG)."""
from functools import lru_cache
import math
import struct
import zlib


def _row(kind, row, prev, channels):
    if kind == 0 or (kind == 2 and not any(row)):
        return row if kind == 0 else prev
    # Most template scanlines are flat colour. Avoid a Python loop across
    # thousands of identical pixels for the common Sub and Paeth encodings.
    if kind in (1, 4) and row[channels:] == bytes(len(row) - channels):
        if kind == 1:
            return row[:channels] * (len(row) // channels)
        if prev == prev[:channels] * (len(row) // channels):
            first = bytes((a + b) & 255 for a, b in zip(row[:channels], prev))
            return first * (len(row) // channels)
    if kind == 2:
        return bytes((a + b) & 255 for a, b in zip(row, prev))
    if kind not in (1, 3, 4):
        raise ValueError("invalid PNG row filter")
    out = bytearray(row)
    for i in range(len(out)):
        left = out[i - channels] if i >= channels else 0
        up = prev[i]
        if kind == 1:
            predict = left
        elif kind == 3:
            predict = (left + up) // 2
        else:
            corner = prev[i - channels] if i >= channels else 0
            p = left + up - corner
            a, b, c = abs(p - left), abs(p - up), abs(p - corner)
            predict = left if a <= b and a <= c else (up if b <= c else corner)
        out[i] = (out[i] + predict) & 255
    return bytes(out)


def _linear(channel):
    v = channel / 255
    return v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4


def _lum(rgb):
    return sum(w * _linear(c) for w, c in zip((.2126, .7152, .0722), rgb))


@lru_cache(maxsize=8192)
def _ratio(pixel, foreground):
    bg = pixel[:3]
    if len(pixel) == 4 and pixel[3] != 255:
        bg = tuple(c * pixel[3] / 255 + 255 - pixel[3] for c in bg)
    alpha = foreground[3]
    front = [a * alpha + b * (1 - alpha) for a, b in zip(foreground, bg)]
    lo, hi = sorted((_lum(bg), _lum(front)))
    return (hi + .05) / (lo + .05)


def contrast_boxes(png, size, boxes, check_time=None):
    """Return each box's lowest actual contrast, including intermediate luminances."""
    w, h, depth, ct, comp, filt, interlace = struct.unpack_from(">IIBBBBB", png, 16)
    if (png[:16] != b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR" or (w, h) != tuple(size) or
            (depth, comp, filt, interlace) != (8, 0, 0, 0) or ct not in (2, 6)):
        raise ValueError("unsupported background screenshot PNG")
    channels = 3 if ct == 2 else 4
    stride = w * channels
    result = [float("inf")] * len(boxes)
    regions = []
    for i, box in enumerate(boxes):
        l, t, r, b = box["rect"]
        if not box["empty"]:
            regions.append((i, max(0, math.floor(l)), max(0, math.floor(t)),
                            min(w, math.ceil(r)), min(h, math.ceil(b)), tuple(box["rgba"])))
    last = max((b for _, _, _, _, b, _ in regions), default=0)
    compressed = []
    at = 8
    while at < len(png):
        n, kind = struct.unpack_from(">I4s", png, at)
        if kind == b"IDAT":
            compressed.append(png[at+8:at+8+n])
        at += n + 12
    if not last:
        return result
    data = zlib.decompressobj().decompress(b"".join(compressed), last * (stride + 1))
    if len(data) != last * (stride + 1):
        raise ValueError("truncated background screenshot PNG")
    prev = bytes(stride)
    for y in range(last):
        if check_time and y % 16 == 0:
            check_time()
        pos = y * (stride + 1)
        prev = _row(data[pos], data[pos+1:pos+1+stride], prev, channels)
        for i, l, t, r, b, rgba in regions:
            if t <= y < b and l < r:
                part = prev[l*channels:r*channels]
                first = part[:channels]
                if part == first * (r - l):
                    ratio = _ratio(tuple(first), rgba)
                else:
                    colors = set(struct.iter_unpack("B" * channels, part))
                    ratio = min(_ratio(pixel, rgba) for pixel in colors)
                result[i] = min(result[i], ratio)
    return result
