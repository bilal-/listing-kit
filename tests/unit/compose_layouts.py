"""Pixel-level layout contracts for the bundled marketing templates."""
from functools import partial
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zlib

KIT = Path(__file__).resolve().parents[2] / "skills/listing-kit"
sys.path.insert(0, str(KIT / "scripts/compose"))
sys.path.insert(0, str(KIT / "scripts/lib"))

import compose
import fontcheck
import imginfo
import pixels
import plan
import render

PHONE = (360, 720)
TABLET = (640, 480)
LANDSCAPE_PHONE = (640, 360)
SIZES = {
    "caption-top": (PHONE, TABLET),
    "caption-bottom": (PHONE, TABLET, (480, 480), (480, 496)),
    "full-bleed": (PHONE, TABLET, (480, 480)),
    "band": (PHONE, TABLET),
    "panel": (PHONE, TABLET),
    "feature": (LANDSCAPE_PHONE, (512, 250)),  # half-size Play graphic
    "header": (LANDSCAPE_PHONE, (672, 288)),  # Apple's 16:9 and 21:9
}
SHOTS = ("caption-top", "caption-bottom", "band", "full-bleed")
CAPTURE_SIZE = (180, 400)
FILL = bytes.fromhex("20b786")
RIM = bytes.fromhex("1868ca")
# Keep the red channel of both text colours and the background above the rim's
# red tolerance, so LCD-antialiased glyph edges cannot register as capture pixels.
PALETTE = {"background": ["#ffedca", "#c8d8f6"], "ink": "#481670", "detail": "#982b19"}
INTER = str(KIT / "assets/fonts/Inter.ttf")
ARABIC = "كل أفكارك هنا"
ARABIC_DETAIL = "أفكار كل يوم"


def png_bytes(size, colour_type, scanlines):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    header = struct.pack(">IIBBBBB", *size, 8, colour_type, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b""))


def monochrome_capture(channel):
    w, h = CAPTURE_SIZE
    scanline = b"\0" + bytes([channel]) * (3 * w)
    return png_bytes(CAPTURE_SIZE, 2, scanline * h)


def solid_capture(size):
    w, h = size
    rim = b"\0" + RIM * w
    middle = b"\0" + RIM * 3 + FILL * (w - 6) + RIM * 3
    return png_bytes(size, 2, rim * 3 + middle * (h - 6) + rim * 3)


def rgb_rows(png, size):
    w, h, depth, colour_type = imginfo._png(io.BytesIO(png))
    if (w, h) != size or depth != 8 or colour_type not in (2, 6):
        raise AssertionError(f"unexpected shipped PNG: {w}x{h}, depth {depth}, type {colour_type}")
    channels = {2: 3, 6: 4}[colour_type]
    data = bytearray()
    offset = 8
    while offset < len(png):
        length, tag = struct.unpack_from(">I4s", png, offset)
        if tag == b"IDAT":
            data.extend(png[offset + 8:offset + 8 + length])
        offset += 12 + length
    raw = zlib.decompress(data)
    row = bytes(w * channels)
    stride = len(row) + 1
    for offset in range(0, len(raw), stride):
        row = pixels._row(raw[offset], raw[offset + 1:offset + stride], row, channels)
        if channels == 4:
            if min(row[3::4]) != 255:
                raise AssertionError("shipped PNG contains transparent pixels")
            yield b"".join(rgb for rgb, in struct.iter_unpack("3sx", row))
        else:
            yield row


def near(sample, expected, tolerance=12):
    return max(abs(a - b) for a, b in zip(sample, expected)) <= tolerance


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


def system_fonts():
    # Fontconfig also knows about distro- and user-configured directories.
    try:
        files = subprocess.check_output(["fc-list", "--format=%{file}\\n"])
        yield from (Path(os.fsdecode(line)) for line in files.splitlines())
    except (OSError, subprocess.CalledProcessError):
        pass
    for root in ("/System/Library/Fonts", "/Library/Fonts", "~/Library/Fonts",
                 "/usr/share/fonts", "/usr/local/share/fonts", "~/.local/share/fonts", "~/.fonts"):
        yield from Path(root).expanduser().rglob("*")


def arabic_font():
    paths = {p for p in system_fonts() if p.suffix.lower() in (".ttf", ".otf")
             and "lastresort" not in str(p).casefold() and "symbol" not in p.name.casefold()}
    preferred = ("Arial.ttf", "DejaVuSans.ttf", "NotoSansArabic-Regular.ttf")
    needed = {ord(c) for c in ARABIC + ARABIC_DETAIL if not c.isspace()}
    for path in sorted(paths, key=lambda p: (p.name not in preferred, str(p))):
        try:
            if needed <= fontcheck.codepoints(path, include_format13=False):
                return str(path)
        except fontcheck.FontError:
            continue
    return None


class ArabicFontFinder(unittest.TestCase):
    def test_fontconfig_candidates_without_arial(self):
        def font(cmap_format, platform=3, encoding=10):
            # One group spanning Arabic. Format 12 maps successive glyph IDs,
            # whereas format 13 maps every character to the same glyph.
            group = struct.pack(">III", 0x0600, 0x06ff, 1)
            sub = struct.pack(">HHIII", cmap_format, 0, 28, 0, 1) + group
            cmap = struct.pack(">HHHHI", 0, 1, platform, encoding, 12) + sub
            return struct.pack(">IHHHH4sIII", 65536, 1, 0, 0, 0, b"cmap", 0, 28, len(cmap)) + cmap

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, data in (("LaStReSoRt.otf", font(12)), ("Fallback.otf", font(13)),
                               ("Icons.ttf", font(12, 3, 0)), ("Symbols.ttf", font(12))):
                (root / name).write_bytes(data)
            with mock.patch.object(Path, "rglob", return_value=[]), mock.patch.object(
                    subprocess, "check_output", side_effect=lambda args: b"\n".join(
                        os.fsencode(p) for p in root.iterdir())):
                self.assertIsNone(arabic_font())
                face = root / "SFArabic.ttf"
                face.write_bytes(font(12))
                self.assertEqual(arabic_font(), str(face))


class FontBrowser(render.cdp.Browser):
    """Inspect actual glyph providers while the rendered document is still open."""
    inspect_fonts = False

    def call(self, method, params=None, session=None, on_event=None):
        if self.inspect_fonts and method == "Page.captureScreenshot":
            self.inspect_fonts = False

            query = partial(super().call, session=session, on_event=on_event)
            query("DOM.enable")
            query("CSS.enable")
            root = query("DOM.getDocument")["root"]["nodeId"]
            selector = '[data-check="text"]:not(:empty)'
            nodes = query("DOM.querySelectorAll", {"nodeId": root, "selector": selector})["nodeIds"]
            self.glyph_fonts = [query("CSS.getPlatformFontsForNode", {"nodeId": node})["fonts"]
                                for node in nodes]
        return super().call(method, params, session, on_event)


class LayoutRenderer(render.cdp.Renderer):
    def render(self, assets, width, height, *, probe, **kwargs):
        # Collect nominal font sizes and the caption band's lower edge in the
        # same document that produces the PNG, before compose consumes the probe.
        probe = f"""Object.assign({probe}, {{
            frame: document.querySelector('.device')?.getBoundingClientRect().toJSON(),
            bandBottom: document.querySelector('.band')?.getBoundingClientRect().bottom,
            detailRects: Array.from(document.querySelectorAll('.detail, .rows dt')).flatMap(el => {{
                const range = document.createRange();
                range.selectNodeContents(el);
                return Array.from(range.getClientRects(), r => [r.left, r.top, r.right, r.bottom]);
            }})
        }})"""
        png, info = super().render(assets, width, height, probe=probe, **kwargs)
        self.boxes = {box["sample"]: box for box in info["text"] if not box["empty"]}
        self.detail_rects = info["detailRects"]
        self.frame = info.get("frame")
        self.band_bottom = info.get("bandBottom")
        return png, info


def bands(spans, max_gap=0):
    result = []
    for y, _, _ in spans:
        if result and y - result[-1][1] <= max_gap + 1:
            result[-1] = (result[-1][0], y)
        else:
            result.append((y, y))
    return result


@unittest.skipUnless(compose.magick(), "no ImageMagick to flatten rendered PNGs")
class Layouts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.browser = FontBrowser()
        cls.addClassCleanup(cls.browser.close)
        cls.renderer = LayoutRenderer(cls.browser)
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.root = Path(tmp.name)

    def job(self, template, size, caption="Today", locale="en-US", fonts=(INTER,),
            capture_size=CAPTURE_SIZE, fit="contain", app_name=None, logo=None):
        style = {"palette": PALETTE, "bezel": {"color": "#305669"}, "fit": fit,
                 "fonts": {"headline": fonts, "detail": fonts}, "logo": logo}
        rec = {"outputPath": "result.png", "template": template, "size": size, "style": style,
               "appName": app_name, "storeCode": locale, "kind": "screenshot", "slotId": template}
        detail = ARABIC_DETAIL if locale == "ar" else "Notes"
        if template in SHOTS:
            raw = self.root / "raw.png"
            raw.write_bytes(solid_capture(capture_size))
            rec.update(rawPath=raw.name, styleMode="framed")
            title_key = "caption"
        else:
            rec["kind"] = "graphic" if template != "panel" else "screenshot"
            title_key = "headline"
        rec["text"] = {title_key: {"value": caption}, "detail": {"value": detail}}
        if template == "panel":
            value = "كل يوم" if locale == "ar" else "Idea"
            rec["text"] = {"panel": {"headline": {"value": caption},
                                     "rows": [{"label": {"value": detail}, "text": {"value": value}}]}}
        return compose.Job(self.root, rec, input_roots={Path(font): Path(font).parent for font in fonts})

    def build_rows(self, job, *, inspect_fonts=False):
        self.browser.inspect_fonts = inspect_fonts
        png = compose.build(job, self.renderer)
        self.assertEqual(job.problems, [])
        if self.browser.inspect_fonts:
            self.fail("screenshot was never captured")
        return list(rgb_rows(png, job.rec["size"]))

    def assert_capture(self, rows, size, template, source_size=CAPTURE_SIZE, fit="contain"):
        w, h = size
        rim = colour_spans(rows, RIM, tolerance=16)
        self.assertTrue(rim, "missing capture rim")
        top, bottom = rim[0][0], rim[-1][0]
        left, right = min(s[1] for s in rim), max(s[2] for s in rim)
        width, height = right - left + 1, bottom - top + 1
        self.assertGreater(width, min(size) // 4, "capture missing or collapsed")
        self.assertGreater(top, 0)
        self.assertAlmostEqual((left + right) / 2, (w - 1) / 2, delta=2)
        if fit == "contain":
            if template in ("caption-top", "caption-bottom"):
                self.assertTrue(left > 0 and right < w - 1 and bottom < h - 1, "frame outside canvas")
            # Compare the shorter axis in pixels so the rounding budget works at any aspect ratio.
            if source_size[0] < source_size[1]:
                self.assertAlmostEqual(width, height * source_size[0] / source_size[1], delta=3)
            else:
                self.assertAlmostEqual(height, width * source_size[1] / source_size[0], delta=3)
        else:
            self.assertEqual(bottom, h - 1, "cropped capture should run past the bottom")
            # Cover spans the canvas. Bleed has a bezel inside 84% of the padded stage.
            u = min(size) / 100
            expected_width = w if fit == "cover" else .84 * (w - 12 * u) - 2 * int(1.2 * u)
            self.assertAlmostEqual(width, expected_width, delta=3)

        def matches(x, y, colour):
            return near(rows[y][3 * x:3 * x + 3], colour, 16)

        corner = round(.05 * min(size)) if template in ("caption-top", "caption-bottom") else 0
        # Along each straight edge, allow a pixel of inward snapping at the boundary.
        horizontal = [(top, 1), (bottom, -1)] if fit == "contain" else [(top, 1)]
        for y, inward in horizontal:
            xs = range(left + corner, right - corner + 1)
            hits = sum(matches(x, y, RIM) or matches(x, y + inward, RIM) for x in xs)
            self.assertGreaterEqual(hits, .97 * len(xs), f"broken capture rim at y={y}")
        for x, inward in ((left, 1), (right, -1)):
            ys = range(top + corner, bottom - corner + 1)
            hits = sum(matches(x, y, RIM) or matches(x + inward, y, RIM) for y in ys)
            self.assertGreaterEqual(hits, .97 * len(ys), f"broken capture rim at x={x}")

        inset = round(3 * width / source_size[0]) + 3  # source rim plus resampling
        for y in range(top + inset, bottom - inset + 1, 3):
            dx = max(corner, inset) if min(y - top, bottom - y) < corner else inset
            for x in range(left + dx, right - dx + 1, 3):
                self.assertTrue(matches(x, y, FILL), f"capture interior obscured at {(x, y)}")
        if fit != "contain":
            for x in range(left + inset, right - inset + 1, 3):
                self.assertTrue(matches(x, bottom, FILL), "capture should continue below canvas")
        return top

    def check_layout(self, template, size, caption, locale, fonts, lines):
        job = self.job(template, size, caption, locale, fonts)
        rows = self.build_rows(job, inspect_fonts=True)
        w, h = size
        if template != "full-bleed":
            for row, hex_colour in zip((rows[0], rows[-1]), PALETTE["background"]):
                for sample in (row[:3], row[-3:]):
                    self.assertTrue(near(sample, bytes.fromhex(hex_colour[1:]), 5), "wrong corner colour")

        ink = colour_spans(rows, bytes.fromhex(PALETTE["ink"][1:]), tolerance=45)
        secondary = colour_spans(rows, bytes.fromhex(PALETTE["detail"][1:]), tolerance=60)
        self.assertTrue(ink and secondary, "missing headline, detail or row label")
        for y, left, right in ink + secondary:
            self.assertTrue(0 < left <= right < w - 1 and 0 < y < h - 1, "text touches canvas edge")

        px = self.renderer.boxes[caption]["px"]
        # Arabic dots can be detached from the body of a glyph.
        gap = round(.14 * px) if locale == "ar" else 0
        headline = bands(ink, gap)
        if template == "panel":
            self.assertEqual(len(headline), lines + 1, "missing headline line or panel row value")
            value_top, value_bottom = headline.pop()
            self.assertGreater(value_top, secondary[-1][0], "row value overlaps label")
            value = job.text["rows"][0][1]
            self.assert_line_height(value_top, value_bottom, self.renderer.boxes[value]["px"], cap_only=value == "Idea")
            if locale == "ar":
                self.assertGreater(min(left for _, left, _ in secondary), w / 2, "expected RTL row")

        self.assertEqual(len(headline), lines, "wrong number of headline lines")
        self.assertLess(headline[-1][1], secondary[0][0], "headline overlaps detail or row label")
        for top, bottom in headline:
            self.assert_line_height(top, bottom, px)
        detail = job.text["rows"][0][0] if template == "panel" else job.text["detail"]
        self.assert_detail_ink(secondary, detail)
        if template == "caption-bottom":
            # Measure the mirrored device from the caption side using the same rim checks.
            device_bottom = h - 1 - self.assert_capture(rows[::-1], size, template)
            self.assertLess(device_bottom, headline[0][0])
        elif template == "full-bleed":
            self.assertGreater(headline[0][0], h / 2)
        elif template in SHOTS:
            self.assertLess(secondary[-1][0], self.assert_capture(rows, size, template))
        else:
            self.assertTrue(h * .15 < headline[0][0] <= headline[-1][1] < h * .85,
                            "headline outside central caption area")
        self.assertTrue(self.browser.glyph_fonts)
        for providers in self.browser.glyph_fonts:
            drawn = [f for f in providers if f["glyphCount"]]
            self.assertTrue(drawn and all(f["isCustomFont"] and
                            "lastresort" not in f["familyName"].replace(" ", "").lower()
                            for f in drawn), f"glyphs outside the supplied fonts: {drawn}")

    def assert_detail_ink(self, spans, detail):
        box = self.renderer.boxes[detail]
        left, top, right, bottom = box["rect"]
        px = box["px"]
        # Accents and antialiased edges can extend beyond the CSS box.
        bearing = 1 + .3 * px
        self.assertTrue(all(left - bearing <= x0 <= x1 <= right + bearing
                            and top - bearing <= y <= bottom + bearing for y, x0, x1 in spans),
                        "detail ink outside its box")
        # A gap in thresholded ink can be a glyph feature or LCD antialiasing.
        # Check the visible height and both ends of each laid-out text fragment.
        self.assertTrue(self.renderer.detail_rects, "missing detail text")
        for left, top, right, bottom in self.renderer.detail_rects:
            line = [(y, x0, x1) for y, x0, x1 in spans if top <= y + .5 < bottom]
            self.assertTrue(line, "missing detail or label line")
            self.assert_line_height(line[0][0], line[-1][0], px, cap_only=detail == "Notes")
            self.assertAlmostEqual(min(x0 for _, x0, _ in line), left, delta=bearing)
            self.assertAlmostEqual(max(x1 for _, _, x1 in line) + 1, right, delta=bearing)

    def assert_line_height(self, top, bottom, px, *, cap_only=False):
        # Small Inter labels without descenders can lose edge rows to antialiasing.
        minimum = round((.60 if cap_only else .70) * px) - 2
        self.assertGreaterEqual(bottom - top + 1, minimum, f"sliced text line at y={top}")

    def check_all(self, locale, fonts):
        for template, sizes in SIZES.items():
            long_caption = {
                "caption-top": "Save all your favourite ideas in one place",
                "caption-bottom": "Save all your favourite ideas in one place",
                "full-bleed": "Save all your favourite ideas in one place",
                "band": "Keep your ideas together wherever you happen to be",
            }.get(template, "A place for every idea worth keeping")
            captions = [(ARABIC, 1)] if locale == "ar" else [("Today", 1), (long_caption, 2)]
            for size in sizes:
                for caption, lines in captions:
                    with self.subTest(template=template, size=size, caption=caption):
                        self.check_layout(template, size, caption, locale, fonts, lines)

    def test_wide_capture_starts_at_band(self):
        source = (400, 180)
        job = self.job("band", PHONE, capture_size=source)
        top = self.assert_capture(self.build_rows(job), PHONE, "band", source)
        self.assertAlmostEqual(top, self.renderer.band_bottom, delta=2,
                               msg="gap between caption band and wide capture")

    def test_full_bleed_edges(self):
        for size in SIZES["full-bleed"]:
            with self.subTest(size=size):
                job = self.job("full-bleed", size)
                w = size[0]
                edges = []
                for channel in (255, 0):
                    Path(job.raw).write_bytes(monochrome_capture(channel))
                    rows = self.build_rows(job)
                    edges.append(rows[0] + rows[-1] + b"".join(row[:3] + row[-3:] for row in rows))
                # Every edge pixel should change with the capture, even underneath the scrim.
                self.assertTrue(all(a > b for a, b in zip(*edges)))
                self.assertGreater(edges[0][0] - edges[1][0], edges[0][3 * w] - edges[1][3 * w])


    def test_full_bleed_contrast_depends_on_capture(self):
        for channel in (0, 255):
            with self.subTest(channel=channel):
                job = self.job("full-bleed", PHONE)
                job.style["palette"] = {"background": ["#00000040"], "ink": "#ffffff", "detail": "#ffffff"}
                Path(job.raw).write_bytes(monochrome_capture(channel))
                compose.build(job, self.renderer)
                if channel == 0:
                    self.assertEqual(job.problems, [])
                else:
                    self.assertEqual(len(job.problems), 2, job.problems)
                    for sample in ("Today", "Notes"):
                        self.assertTrue(any("contrast" in p and sample in p for p in job.problems), job.problems)

    def test_full_bleed_preserves_capture_aspect(self):
        # A centered 30x20 marker survives object-fit:cover on all three canvases.
        w, h = CAPTURE_SIZE
        plain = b"\0" + FILL * w
        margin = FILL * ((w - 30) // 2)
        marker = b"\0" + margin + RIM * 30 + margin
        side = plain * ((h - 20) // 2)
        capture = png_bytes(CAPTURE_SIZE, 2, side + marker * 20 + side)
        for size in SIZES["full-bleed"]:
            with self.subTest(size=size):
                job = self.job("full-bleed", size)
                Path(job.raw).write_bytes(capture)
                spans = colour_spans(self.build_rows(job), RIM, tolerance=16)
                self.assertTrue(spans, "missing marker")
                width = max(right - left + 1 for _, left, right in spans)
                self.assertAlmostEqual(width, 30 * max(size[0] / w, size[1] / h), delta=3)
                self.assertAlmostEqual(len(spans), width * 20 / 30, delta=2)

    def test_caption_bottom_cover_stays_in_stage(self):
        for size in SIZES["caption-bottom"] + (LANDSCAPE_PHONE,):
            with self.subTest(size=size):
                self.build_rows(self.job("caption-bottom", size, fit="cover"))
                frame = self.renderer.frame
                self.assertGreater(frame["top"], 0)
                self.assertGreater(frame["left"], 0)
                self.assertLess(frame["right"], size[0])
                self.assertLess(frame["bottom"], self.renderer.boxes["Today"]["rect"][1])
                self.assertAlmostEqual(frame["width"], size[0] - .12 * min(size), delta=2)

    def test_landscape_caption_bottom_inherits_cover(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            listing = root / plan.LISTING
            listing.parent.mkdir()
            listing.write_text(json.dumps({
                "format": 2, "app": "example.tablet", "locales": ["en-US"],
                "style": {"mode": "framed", "fit": "cover", "palette": PALETTE,
                          "fonts": {"default": {"headline": ["bundled:Inter"], "detail": ["bundled:Inter"]}}},
                "targets": [{"id": "ipad", "store": "apple", "slot": "ipad-13", "state": "active",
                             "size": [2752, 2064], "template": "caption-bottom"}],
                "screens": [{"id": "one", "flow": "one.yaml", "caption": {"en-US": "Today"}}],
            }))
            (root / "one.yaml").touch()
            manifest, templates, inputs = plan.compose_inputs(root)
            record, = manifest["outputs"]
            job = compose.Job(root, record, templates, inputs)
            self.assertEqual((job.template, job.fit()), ("caption-bottom", "cover"))
            raw = Path(job.raw)
            raw.parent.mkdir(parents=True)
            raw.write_bytes(solid_capture((1290, 2796)))
            compose.build(job, self.renderer)
            self.assertEqual(job.problems, [])
            self.assertGreater(self.renderer.frame["top"], 0)
            self.assertLess(self.renderer.frame["bottom"], self.renderer.boxes["Today"]["rect"][1])

    def test_empty_brand(self):
        for template in ("header", "feature", "panel"):
            with self.subTest(template=template):
                size = SIZES[template][0]
                self.build_rows(self.job(template, size))
                boxes = self.renderer.boxes
                last = "Idea" if template == "panel" else "Notes"
                centre = (boxes["Today"]["rect"][1] + boxes[last]["rect"][3]) / 2
                self.assertAlmostEqual(centre, size[1] / 2, delta=2, msg="empty brand displaces text")

    def test_header_brand(self):
        logo = self.root / "brand.png"
        logo.write_bytes(solid_capture((96, 40)))
        for image in (None, logo.name):
            with self.subTest(logo=image):
                rows = self.build_rows(self.job("header", LANDSCAPE_PHONE, app_name="Acorn", logo=image))
                above_title = rows[:int(self.renderer.boxes["Today"]["rect"][1])]
                if image:
                    self.assertTrue(colour_spans(above_title, FILL, tolerance=12), "logo missing")
                else:
                    self.assertIn("Acorn", self.renderer.boxes)
                    self.assertTrue(colour_spans(above_title, bytes.fromhex(PALETTE["ink"][1:]), 30),
                                    "brand name missing")

    def test_cropped_fits(self):
        for template, fit in (("band", "cover"), ("caption-top", "bleed"), ("caption-bottom", "bleed")):
            with self.subTest(template=template, fit=fit):
                rows = self.build_rows(self.job(template, TABLET, fit=fit))
                self.assert_capture(rows[::-1] if template == "caption-bottom" else rows, TABLET, template, fit=fit)

    def test_caption_bottom_bleed_measures_top_cut(self):
        for size in SIZES["caption-bottom"]:
            with self.subTest(size=size):
                job = self.job("caption-bottom", size, fit="bleed")
                rim = colour_spans(self.build_rows(job), RIM, tolerance=16)
                self.assertTrue(rim, "missing device")
                width = max(right - left + 1 for _, left, right in rim)
                height = rim[-1][0] - rim[0][0] + 1
                self.assertLess(rim[-1][0], self.renderer.boxes["Today"]["rect"][1])
                cut = max(0, 1 - height / (width * CAPTURE_SIZE[1] / CAPTURE_SIZE[0]))
                if size == TABLET:
                    self.assertEqual(rim[0][0], 0)
                    self.assertGreater(cut, .5)
                self.assertAlmostEqual(job.report["bleedCut"], cut, delta=.01)

    def test_build_flattens_rgba(self):
        # Exercise the browser RGBA path even on Chromium builds that always emit RGB.
        job = self.job("feature", (2, 1))
        raw = png_bytes((2, 1), 6, b"\0" + FILL + b"\xff" + RIM + b"\0")
        with mock.patch.object(render, "render", return_value=(raw, {"problems": []})):
            rows = self.build_rows(job)
        self.assertTrue(near(rows[0][:3], FILL, 3))
        self.assertTrue(near(rows[0][3:], b"\xff" * 3, 3), "transparent pixel did not flatten to white")

    def test_inter(self):
        self.assertEqual(set(SIZES), {p.stem for p in (KIT / "templates").glob("*.html")})
        self.check_all("en-US", [INTER])

    def test_arabic(self):
        fallback = arabic_font()
        if not fallback:
            self.skipTest("no system TTF/OTF with Arabic glyphs for all layout text")
        self.check_all("ar", [INTER, fallback])


if __name__ == "__main__":
    result = unittest.main(exit=False).result
    for case, reason in result.skipped:
        print(f"  skipped: {reason} ({case.id()})")
    required_skips = result.skipped and os.environ.get("LK_REQUIRE_RENDER") == "1"
    sys.exit(0 if result.wasSuccessful() and not required_skips else 1)
