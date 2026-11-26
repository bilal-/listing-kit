"""Pixel-level layout contracts for the bundled marketing templates."""
import io
import itertools
from pathlib import Path
import struct
import sys
import unittest
import zlib

KIT = Path(__file__).resolve().parents[2] / "skills/listing-kit"
sys.path.insert(0, str(KIT / "scripts/compose"))
sys.path.insert(0, str(KIT / "scripts/lib"))

import fontcheck
import imginfo
import pixels
import render

PHONE = (360, 720)
TABLET = (640, 480)
LANDSCAPE_PHONE = (640, 360)
SIZES = {
    "caption-top": (PHONE, TABLET),
    "band": (PHONE, TABLET),
    "panel": (PHONE, TABLET),
    "feature": (LANDSCAPE_PHONE, (512, 250)),  # half-size Play graphic
    "header": (LANDSCAPE_PHONE, (672, 288)),  # Apple's 16:9 and 21:9
}
SHOTS = ("caption-top", "band")
CAPTURE_SIZE = (180, 400)
FILL = bytes.fromhex("20b786")
RIM = bytes.fromhex("1868ca")
PALETTE = {"background": ["#ffedca", "#c8d8f6"], "ink": "#401542", "detail": "#982b19"}
INTER = str(KIT / "assets/fonts/Inter.ttf")
ARABIC = "كل أفكارك هنا"


def solid_capture():
    # A narrow rim lets us see all four source edges even when band fits flush
    # with the bottom of the canvas. The interior is one uninterrupted colour.
    w, h = CAPTURE_SIZE
    rim = b"\0" + RIM * w
    middle = b"\0" + RIM * 3 + FILL * (w - 6) + RIM * 3

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rim * 3 + middle * (h - 6) + rim * 3)) + chunk(b"IEND", b""))


def rgb_rows(png, width):
    data = bytearray()
    offset = 8
    while offset < len(png):
        length, tag = struct.unpack_from(">I4s", png, offset)
        if tag == b"IDAT":
            data.extend(png[offset + 8:offset + 8 + length])
        offset += 12 + length
    raw = zlib.decompress(data)
    stride = 3 * width + 1
    row = bytes(stride - 1)
    for offset in range(0, len(raw), stride):
        row = pixels._row(raw[offset], raw[offset + 1:offset + stride], row, 3)
        yield row


def colour_spans(rows, colour, tolerance=0):
    """Inclusive x extents on every scanline containing this colour."""
    reds, greens, blues = [range(c - tolerance, c + tolerance + 1) for c in colour]
    spans = []
    for y, row in enumerate(rows):
        xs = [x for x, (r, g, b) in enumerate(struct.iter_unpack("BBB", row))
              if r in reds and g in greens and b in blues]
        if xs:
            spans.append((y, xs[0], xs[-1]))
    return spans


def arabic_font():
    roots = [Path(p) for p in ("/System/Library/Fonts", "/Library/Fonts", "/usr/share/fonts",
                               "/usr/local/share/fonts", "~/.local/share/fonts", "~/Library/Fonts")]
    paths = [p for root in roots for p in root.expanduser().rglob("*")
             if p.suffix.lower() in (".ttf", ".otf")]
    preferred = ("Arial.ttf", "DejaVuSans.ttf", "NotoSansArabic-Regular.ttf")
    for path in sorted(paths, key=lambda p: (p.name not in preferred, str(p))):
        try:
            if not fontcheck.missing(ARABIC, [path]):
                return str(path)
        except fontcheck.FontError:
            continue
    return None


class Layouts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.browser, cls.renderer = render.open_browser()
        cls.addClassCleanup(cls.browser.close)
        cls.raw = solid_capture()

    def assert_capture(self, rows, size, template):
        w, h = size
        rim = colour_spans(rows, RIM, tolerance=4)
        self.assertTrue(rim, "missing capture rim")
        top, bottom = rim[0][0], rim[-1][0]
        left, right = min(s[1] for s in rim), max(s[2] for s in rim)
        self.assertTrue(0 < left < right < w - 1 and top > 0, "capture reaches a side or top edge")
        if template == "caption-top":
            self.assertLess(bottom, h - 1, "framed capture reaches bottom edge")
        width, height = right - left + 1, bottom - top + 1
        self.assertGreater(width, min(size) // 4, "capture is missing or collapsed")
        self.assertAlmostEqual(width / height / (CAPTURE_SIZE[0] / CAPTURE_SIZE[1]), 1, delta=.01)
        cx, cy = (left + right) // 2, (top + bottom) // 2
        for x, y in ((left, cy), (right, cy), (cx, top), (cx, bottom)):
            sample = rows[y][3 * x:3 * x + 3]
            self.assertLessEqual(max(abs(a - b) for a, b in zip(sample, RIM)), 4,
                                 "capture edge missing at %s on %sx%s" % ((x, y), w, h))

        # Skip the rounded bezel corners and the resampled rim; check every
        # other interior pixel, including holes that leave the bounds intact.
        inset = max(2, round(4 * width / CAPTURE_SIZE[0]))
        corner = round(.06 * min(size))
        for y in range(top + inset, bottom - inset + 1):
            dx = max(inset, corner) if min(y - top, bottom - y) < corner else inset
            start, end = left + dx, right + 1 - dx
            self.assertTrue(rows[y][3 * start:3 * end] == FILL * (end - start),
                            "capture interior obscured on row %d" % y)
        return top

    def check_layout(self, template, size, caption, locale, fonts, lines):
        w, h = size
        shot = template in SHOTS
        text = {"caption" if shot else "headline": caption}
        detail = "هنا" if locale == "ar" else "Notes"
        if template == "panel":
            text["rows"] = [(detail, detail)]
        else:
            text["detail"] = detail
        png, report = render.render(
            self.renderer, template, size, locale,
            {"palette": PALETTE, "bezel": {"color": "#305669"}},
            {"headline": fonts, "detail": fonts}, text,
            raw=self.raw if shot else None, shot_size=CAPTURE_SIZE if shot else None)
        self.assertEqual(imginfo._png(io.BytesIO(png)), (w, h, 8, 2), "expected opaque RGB")
        rows = list(rgb_rows(png, w))
        for row, hex_colour in zip((rows[0], rows[-1]), PALETTE["background"]):
            expected = bytes.fromhex(hex_colour[1:])
            for sample in (row[:3], row[-3:]):
                self.assertLessEqual(max(abs(a - b) for a, b in zip(sample, expected)), 5,
                                     "corner %s differs from %s" % (sample.hex(), hex_colour))

        ink = colour_spans(rows, bytes.fromhex(PALETTE["ink"][1:]), tolerance=12)
        self.assertTrue(ink, "no caption ink")
        self.assertTrue(all(0 < left <= right < w - 1 for _, left, right in ink), "ink touches a side")
        self.assertTrue(0 < ink[0][0] <= ink[-1][0] < h - 1, "ink touches top or bottom")
        secondary = colour_spans(rows, bytes.fromhex(PALETTE["detail"][1:]), tolerance=40)
        self.assertTrue(secondary, "missing detail or panel row label")
        if template == "panel":
            # The row value shares the headline ink. Its differently coloured
            # label separates them and follows the document's writing direction.
            self.assertTrue(ink[-1][0] > secondary[-1][0], "missing panel row value")
            if locale == "ar":
                self.assertGreater(min(left for _, left, _ in secondary), w / 2, "expected RTL row")
            ink = [span for span in ink if span[0] < secondary[0][0]]
            self.assertTrue(ink, "missing panel headline above the row label")
        top, bottom = ink[0][0], ink[-1][0]
        self.assertLess(bottom, secondary[0][0], "headline overlaps detail or row label")
        if shot:
            capture_top = self.assert_capture(rows, size, template)
            self.assertLess(secondary[-1][0], capture_top, "caption must fit above the capture")
        else:
            self.assertTrue(h * .15 < top <= bottom < h * .85, "headline outside the central caption area")
        if lines:
            # Latin glyphs in these captions occupy consecutive scanlines per line.
            bands = itertools.groupby(enumerate(ink), lambda item: item[1][0] - item[0])
            self.assertEqual(sum(1 for _ in bands), lines, "wrong number of visible lines")
        self.assertEqual(report["problems"], [])

    def check_all(self, locale, fonts):
        for template, sizes in SIZES.items():
            long_caption = {
                "caption-top": "Save all your favourite ideas in one place",
                "band": "Keep your ideas together wherever you happen to be",
            }.get(template, "A place for every idea worth keeping")
            captions = [(ARABIC, None)] if locale == "ar" else [("Today", 1), (long_caption, 2)]
            for size in sizes:
                for caption, lines in captions:
                    with self.subTest(template=template, size=size, caption=caption):
                        self.check_layout(template, size, caption, locale, fonts, lines)

    def test_inter(self):
        self.assertEqual(set(SIZES), {p.stem for p in (KIT / "templates").glob("*.html")})
        self.check_all("en-US", [INTER])

    def test_arabic(self):
        fallback = arabic_font()
        if not fallback:
            self.skipTest("no system TTF/OTF covers the Arabic caption")
        self.check_all("ar", [INTER, fallback])


if __name__ == "__main__":
    result = unittest.main(exit=False).result
    for case, reason in result.skipped:
        print(f"  skipped: {reason} ({case.id()})")
    sys.exit(0 if result.wasSuccessful() else 1)
