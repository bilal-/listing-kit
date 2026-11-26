#!/usr/bin/env python3
"""Structural PNG/JPEG checks in pure Python, plus full pixel decoding via ImageMagick.

`image_info()` inspects stream structure (PNG chunk ordering, CRCs, row filter bytes,
and deflated scanline byte counts up to 64 MP; JPEG marker framing, DQT/DHT/DAC tables,
byte stuffing, restart markers, and EOI). It is a structural check, not a full pixel or
animation decoder. `decodes()` runs a full pixel decode via ImageMagick when installed,
treating warnings as errors.

CLI:    imginfo.py <file>...
        imginfo.py --decode <file>...
Default mode prints one tab-separated line per file:
    width  height  bit_depth  color_type  bytes  apple_class  path
`--decode` prints one tab-separated line per file:
    status  path          (status in ok / bad / unavailable)
color_type follows PNG numbering: 2 = RGB (no alpha), 6 = RGBA, 0 = grayscale,
4 = grayscale+alpha, 3 = palette; a PNG with a tRNS (transparency) chunk reports
e.g. "2+tRNS", so it never passes as "2". JPEGs report 2 (3 channels), 0 (1
channel), or 99 (CMYK/other). Unreadable or invalid files report "0 0 0 99".
apple_class is the App Store display class from apple-screenshot-sizes.tsv, or "-".

Also imported by build-review.sh and apple_assets.py.
"""
import os
import shutil
import struct
import subprocess
import sys
import zlib

UNKNOWN = (0, 0, 0, 99)
EXTENSIONS = (".png", ".jpg", ".jpeg")  # deliver/supply upload these (lower-case only on Linux)
SIZES_TSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apple-screenshot-sizes.tsv")
CHUNK = 65536
MAX_PIXELS = 64_000_000
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


def _png_passes(w, h, bpp, interlace):
    if interlace == 0:
        stride = 1 + (w * bpp + 7) // 8
        expected = h * stride
        return expected, [(expected, stride)]
    passes = []
    expected = 0
    for x0, dx, y0, dy in ADAM7:
        pw = (w - x0 + dx - 1) // dx if w > x0 else 0
        ph = (h - y0 + dy - 1) // dy if h > y0 else 0
        if pw > 0 and ph > 0:
            stride = 1 + (pw * bpp + 7) // 8
            expected += ph * stride
            passes.append((expected, stride))
    return expected, passes


def _png(f):
    d = f.read(33)
    if len(d) < 33 or d[:8] != b"\x89PNG\r\n\x1a\n" or d[8:16] != b"\x00\x00\x00\x0dIHDR":
        return UNKNOWN
    if zlib.crc32(d[12:29]) != struct.unpack(">I", d[29:33])[0]:
        return UNKNOWN
    w, h, depth, ct, comp, filt, interlace = struct.unpack(">IIBBBBB", d[16:29])
    if not (0 < w <= 0x7FFFFFFF and 0 < h <= 0x7FFFFFFF) or w * h > MAX_PIXELS:
        return UNKNOWN
    if comp != 0 or filt != 0 or interlace not in (0, 1):
        return UNKNOWN
    fmt = PNG_FORMATS.get(ct)
    if fmt is None or depth not in fmt[1]:
        return UNKNOWN
    expected, passes = _png_passes(w, h, fmt[0] * depth, interlace)

    trns = False
    saw_idat = False
    idat_done = False
    saw_trailing_idat = False
    saw_plte = False
    plte_entries = 0
    total = 0
    pass_idx = 0
    next_row = 0
    dec = zlib.decompressobj()

    def feed_scanlines(out):
        nonlocal total, pass_idx, next_row
        if not out:
            return True
        base = total
        end = base + len(out)
        if end > expected:
            return False
        while pass_idx < len(passes) and next_row < end:
            pass_end, stride = passes[pass_idx]
            limit = min(pass_end, end)
            if next_row < limit:
                sub = out[next_row - base : limit - base : stride]
                if max(sub) > 4:
                    return False
                next_row += len(sub) * stride
            if next_row >= pass_end:
                pass_idx += 1
        total = end
        return True

    while True:
        head = f.read(8)
        if len(head) < 8:
            return UNKNOWN
        length, kind = struct.unpack(">I4s", head)
        if length > 0x7FFFFFFF or not all(65 <= c <= 90 or 97 <= c <= 122 for c in kind):
            return UNKNOWN
        if kind != b"IDAT" and saw_idat:
            idat_done = True
        crc = zlib.crc32(kind)

        if kind == b"IDAT":
            if idat_done or saw_trailing_idat or (ct == 3 and not saw_plte):
                return UNKNOWN
            saw_idat = True
            rem = length
            while rem > 0:
                buf = f.read(min(CHUNK, rem))
                if not buf:
                    return UNKNOWN
                rem -= len(buf)
                crc = zlib.crc32(buf, crc)
                if not dec.eof:
                    data = buf
                    while data and not dec.eof:
                        out = dec.decompress(data, CHUNK)
                        if not feed_scanlines(out):
                            return UNKNOWN
                        data = dec.unconsumed_tail
                    if dec.eof:
                        if not feed_scanlines(dec.flush()) or total != expected:
                            return UNKNOWN
                        if dec.unused_data or rem > 0:
                            saw_trailing_idat = True
                else:
                    saw_trailing_idat = True
            tail = f.read(4)
            if len(tail) < 4 or struct.unpack(">I", tail)[0] != crc:
                return UNKNOWN
        elif kind == b"IEND":
            if length != 0:
                return UNKNOWN
            tail = f.read(4)
            if len(tail) < 4 or struct.unpack(">I", tail)[0] != crc:
                return UNKNOWN
            if not saw_idat or not dec.eof or total != expected:
                return UNKNOWN
            return w, h, depth, f"{ct}+tRNS" if trns else ct
        else:
            if kind == b"PLTE":
                max_plte = min(768, 3 * (1 << depth))
                if saw_idat or saw_plte or ct in (0, 4) or length < 3 or length > max_plte or length % 3 != 0:
                    return UNKNOWN
                saw_plte = True
                plte_entries = length // 3
            elif kind == b"tRNS":
                if saw_idat or trns or ct in (4, 6):
                    return UNKNOWN
                if (ct == 0 and length != 2) or (ct == 2 and length != 6):
                    return UNKNOWN
                if ct == 3 and (not saw_plte or length == 0 or length > plte_entries):
                    return UNKNOWN
                trns = True
            elif (kind[0] & 0x20) == 0:
                return UNKNOWN
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
    ff_run = 0
    while True:
        buf = f.read(CHUNK)
        if not buf:
            return None
        i = 0
        n = len(buf)
        while i < n:
            if ff_run == 0:
                j = buf.find(b"\xff", i)
                if j == -1:
                    has_data = True
                    break
                if j > i:
                    has_data = True
                ff_run = 1
                i = j + 1
            while i < n and buf[i] == 0xFF:
                ff_run += 1
                i += 1
            if i == n:
                break
            m = buf[i]
            i += 1
            if m == 0x00:
                if ff_run != 1:
                    return None
                has_data = True
                ff_run = 0
            elif 0xD0 <= m <= 0xD7:
                ff_run = 0
            else:
                if not has_data:
                    return None
                f.seek(i - n, os.SEEK_CUR)
                return m


def _jpeg(f):
    if f.read(2) != b"\xff\xd8":
        return UNKNOWN
    frame = None
    sof_marker = None
    frame_comps = {}
    dqts = set()
    dc_dhts = set()
    ac_dhts = set()
    saw_dac = False
    saw_sos = False
    next_marker = None
    while True:
        if next_marker is not None:
            marker, next_marker = next_marker, None
        else:
            b = f.read(1)
            if b != b"\xff":
                return UNKNOWN
            while b == b"\xff":
                b = f.read(1)
            if not b:
                return UNKNOWN
            marker = b[0]
        if marker == 0xD9:
            return frame if (frame is not None and saw_sos) else UNKNOWN
        if marker == 0x01:
            continue
        if marker in (0x00, 0xC8, 0xD8) or 0xD0 <= marker <= 0xD7:
            return UNKNOWN
        seg = f.read(2)
        if len(seg) < 2:
            return UNKNOWN
        length = struct.unpack(">H", seg)[0]
        if length < 2:
            return UNKNOWN
        if marker == 0xDB:  # DQT
            d = f.read(length - 2)
            if len(d) != length - 2 or not d:
                return UNKNOWN
            pos = 0
            while pos < len(d):
                pq, tq = d[pos] >> 4, d[pos] & 0x0F
                pos += 1
                qlen = 64 * (pq + 1)
                if pq not in (0, 1) or tq > 3 or pos + qlen > len(d):
                    return UNKNOWN
                pos += qlen
                dqts.add(tq)
        elif marker == 0xC4:  # DHT
            d = f.read(length - 2)
            if len(d) != length - 2 or not d:
                return UNKNOWN
            pos = 0
            while pos < len(d):
                if pos + 17 > len(d):
                    return UNKNOWN
                tc, th = d[pos] >> 4, d[pos] & 0x0F
                vals = sum(d[pos + 1 : pos + 17])
                pos += 17
                if tc not in (0, 1) or th > 3 or vals > 256 or pos + vals > len(d):
                    return UNKNOWN
                pos += vals
                (dc_dhts if tc == 0 else ac_dhts).add(th)
        elif marker == 0xCC:  # DAC
            d = f.read(length - 2)
            if len(d) != length - 2 or not d or len(d) % 2 != 0:
                return UNKNOWN
            for pos in range(0, len(d), 2):
                tc, tb = d[pos] >> 4, d[pos] & 0x0F
                if tc not in (0, 1) or tb > 3:
                    return UNKNOWN
            saw_dac = True
        elif 0xC0 <= marker <= 0xCF:  # SOF0..SOF15 (excluding C4, C8, CC)
            if frame is not None:
                return UNKNOWN
            d = f.read(length - 2)
            if len(d) != length - 2 or len(d) < 6:
                return UNKNOWN
            precision, h, w, comps = struct.unpack(">BHHB", d[:6])
            if not w or not h or not comps or len(d) != 6 + 3 * comps:
                return UNKNOWN
            frame_comps = {}
            for idx in range(comps):
                ci, hv, tqi = d[6 + 3 * idx : 9 + 3 * idx]
                hs, vs = hv >> 4, hv & 0x0F
                if ci in frame_comps or not (1 <= hs <= 4 and 1 <= vs <= 4) or tqi > 3:
                    return UNKNOWN
                frame_comps[ci] = tqi
            sof_marker = marker
            frame = (w, h, precision, {3: 2, 1: 0}.get(comps, 99))
        elif marker == 0xDA:  # SOS
            if frame is None:
                return UNKNOWN
            hdr = f.read(length - 2)
            if len(hdr) != length - 2 or len(hdr) < 6:
                return UNKNOWN
            ns = hdr[0]
            if not (1 <= ns <= 4) or len(hdr) != 4 + 2 * ns:
                return UNKNOWN
            ss, se, ahal = hdr[-3], hdr[-2], hdr[-1]
            ah, al = ahal >> 4, ahal & 0x0F
            lossless = sof_marker in (0xC3, 0xC7, 0xCB, 0xCF)
            progressive = sof_marker in (0xC2, 0xC6, 0xCA, 0xCE)
            if not lossless:
                if progressive:
                    if ss > se or se > 63 or (ss == 0 and se != 0) or (ss > 0 and ns != 1):
                        return UNKNOWN
                elif ss != 0 or se != 63 or ah != 0 or al != 0:
                    return UNKNOWN
            seen_cs = set()
            for j in range(ns):
                cs = hdr[1 + 2 * j]
                td, ta = hdr[2 + 2 * j] >> 4, hdr[2 + 2 * j] & 0x0F
                if cs in seen_cs or cs not in frame_comps or td > 3 or ta > 3:
                    return UNKNOWN
                seen_cs.add(cs)
                if not lossless and frame_comps[cs] not in dqts:
                    return UNKNOWN
                if sof_marker <= 0xC7:
                    if lossless:
                        if td not in dc_dhts:
                            return UNKNOWN
                    else:
                        if ss == 0 and ah == 0 and td not in dc_dhts:
                            return UNKNOWN
                        if se > 0 and ta not in ac_dhts:
                            return UNKNOWN
                elif not saw_dac:
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


def _im_decode_cmd(target):
    if os.environ.get("LK_NO_IMAGEMAGICK"):
        return None
    magick = shutil.which("magick")
    if magick:
        return [magick, "-regard-warnings", target, "null:"]
    convert = shutil.which("convert")
    if convert:
        return [convert, "-regard-warnings", target, "null:"]
    identify = shutil.which("identify")
    if identify:
        return [identify, "-regard-warnings", "-verbose", target]
    return None


def decodes(path):
    """Full pixel decode via ImageMagick ('ok', 'bad', or 'unavailable'); warnings are errors."""
    target = os.path.abspath(path)
    cmd = _im_decode_cmd(target)
    if cmd is None:
        return "unavailable"
    if not os.path.isfile(target):
        return "bad"
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except OSError:
        return "bad"
    if res.returncode != 0 or res.stderr.strip():
        return "bad"
    return "ok"


def decode_many(paths):
    """Decode each path ('ok'/'bad'/'unavailable'), batching multi-file checks into one IM run."""
    if not paths:
        return []
    if len(paths) == 1:
        return [decodes(paths[0])]
    if os.environ.get("LK_NO_IMAGEMAGICK"):
        return ["unavailable"] * len(paths)
    magick = shutil.which("magick")
    convert = None if magick else shutil.which("convert")
    identify = None if (magick or convert) else shutil.which("identify")
    if not (magick or convert or identify):
        return ["unavailable"] * len(paths)
    targets = [os.path.abspath(p) for p in paths]
    if all(os.path.isfile(t) for t in targets):
        if magick:
            cmd = [magick, "-regard-warnings"] + targets + ["null:"]
        elif convert:
            cmd = [convert, "-regard-warnings"] + targets + ["null:"]
        else:
            cmd = [identify, "-regard-warnings", "-verbose"] + targets
        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if res.returncode == 0 and not res.stderr.strip():
                return ["ok"] * len(paths)
        except OSError:
            pass
    return [decodes(p) for p in paths]


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
    if len(sys.argv) > 1 and sys.argv[1] == "--decode":
        paths = sys.argv[2:]
        for p, st in zip(paths, decode_many(paths)):
            print("\t".join((st, p)))
    elif len(sys.argv) > 1 and sys.argv[1] == "--validate":
        paths = sys.argv[2:]
        for p, st in zip(paths, decode_many(paths)):
            w, h, depth, ct = image_info(p)
            size = os.path.getsize(p) if os.path.exists(p) else 0
            print("\t".join(map(str, (w, h, depth, ct, size, apple_class(w, h) or "-", st, p))))
    else:
        for p in sys.argv[1:]:
            w, h, depth, ct = image_info(p)
            size = os.path.getsize(p) if os.path.exists(p) else 0
            print("\t".join(map(str, (w, h, depth, ct, size, apple_class(w, h) or "-", p))))
