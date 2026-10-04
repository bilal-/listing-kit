#!/usr/bin/env python3
"""Builds every file in brand/ from the geometry below.

    python3 brand/tools/build.py

Needs fontTools (pip install fonttools) and rsvg-convert (brew install librsvg /
apt install librsvg2-bin). The wordmark is Archivo, outlined to paths so no font
ships with the logos; the font is downloaded once from google/fonts at a pinned
commit and cached in brand/tools/.cache/.
"""
import os
import subprocess
import urllib.request

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.dirname(HERE)

# ---- colour ----
INK = "#132235"  # screen outline and wordmark, on light
PAPER = "#FFFFFF"  # screen fill
NIGHT = "#0B121B"  # dark background
FOG = "#E6EDF3"  # outline and wordmark, on dark
PROOF = "#D6006F"  # crop marks, on light
PROOF_DARK = "#FF4FA3"  # crop marks, on dark
TABLE = "#F3F6F9"  # light background

# ---- the mark: a phone screen between two crop marks, on a 32-unit grid ----
SCREEN = dict(x=11, y=6, w=10, h=20, r=2.2, stroke=2)
CROPS = "M3 9V3h6M29 23v6h-6"
CROP_STROKE = 2.4


def mark(outline, fill, crop, x=0, y=0, scale=1.0):
    s = SCREEN
    return (
        f'<g transform="translate({x} {y}) scale({scale})">'
        f'<rect x="{s["x"]}" y="{s["y"]}" width="{s["w"]}" height="{s["h"]}" rx="{s["r"]}" '
        f'fill="{fill}" stroke="{outline}" stroke-width="{s["stroke"]}"/>'
        f'<path d="{CROPS}" fill="none" stroke="{crop}" stroke-width="{CROP_STROKE}" '
        f'stroke-linecap="square"/></g>'
    )


# ---- the wordmark: "listing-kit" in Archivo Bold, width 112 ----
FONT_URL = (
    "https://raw.githubusercontent.com/google/fonts/"
    "6c70c829f09ea345d3590406693220ea35c6553f/ofl/archivo/Archivo%5Bwdth%2Cwght%5D.ttf"
)


def wordmark_path(text="listing-kit", size=24.0):
    """Outlined text as one SVG path, baseline at y=0, plus its advance width."""
    cache = os.path.join(HERE, ".cache")
    os.makedirs(cache, exist_ok=True)
    ttf = os.path.join(cache, "Archivo-variable.ttf")
    if not os.path.exists(ttf):
        urllib.request.urlretrieve(FONT_URL, ttf)
    font = instantiateVariableFont(TTFont(ttf), {"wght": 700, "wdth": 112})
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    scale = size / font["head"].unitsPerEm
    pen, x = SVGPathPen(glyphs), 0.0
    for ch in text:
        name = cmap[ord(ch)]
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, 0)))
        x += glyphs[name].width * scale
    return pen.getCommands(), x


def svg(w, h, body, bg=None):
    rect = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">{rect}{body}</svg>\n'


def write(rel, content):
    path = os.path.join(BRAND, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return path


def png(svg_path, out_rel, width=None, height=None):
    """Rasterize; give a width or a height and the other follows the aspect ratio."""
    out = os.path.join(BRAND, out_rel)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    size = (["-w", str(width)] if width else []) + (["-h", str(height)] if height else [])
    args = ["rsvg-convert", *size, svg_path, "-o", out]
    subprocess.run(args, check=True)


def main():
    word, word_w = wordmark_path()
    variants = {
        "on-light": (INK, PAPER, PROOF),
        "on-dark": (FOG, NIGHT, PROOF_DARK),
        "black": ("#000000", "#FFFFFF", "#000000"),
        "white": ("#FFFFFF", "none", "#FFFFFF"),
    }
    files = []
    for name, (outline, fill, crop) in variants.items():
        # Symbol alone.
        files.append(write(f"svg/mark-{name}.svg", svg(32, 32, mark(outline, fill, crop))))
        # Horizontal: mark + wordmark, wordmark cap height aligned to the screen.
        h = 32
        body = mark(outline, fill, crop) + f'<path transform="translate(40 23.6)" d="{word}" fill="{outline}"/>'
        files.append(write(f"svg/horizontal-{name}.svg", svg(round(40 + word_w + 2), h, body)))

    # PNG logos, 128px and 256px high.
    for name in variants:
        for scale, suffix in ((4, "@1x"), (8, "@2x")):
            png(os.path.join(BRAND, f"svg/horizontal-{name}.svg"), f"png/horizontal-{name}{suffix}.png", height=32 * scale)
            png(os.path.join(BRAND, f"svg/mark-{name}.svg"), f"png/mark-{name}{suffix}.png", 32 * scale)

    # App icons: the mark on the light background, square and rounded.
    icon_body = mark(INK, PAPER, PROOF, x=192, y=192, scale=20)
    square = write("icons/icon-square.svg", svg(1024, 1024, icon_body, bg=TABLE))
    rounded = write(
        "icons/icon-rounded.svg",
        svg(1024, 1024, f'<rect width="1024" height="1024" rx="228" fill="{TABLE}"/>' + icon_body),
    )
    png(square, "icons/icon-square-1024.png", 1024)
    png(rounded, "icons/icon-rounded-1024.png", 1024)

    # Web icons. The favicon is the bare mark; raster sizes use the square icon.
    write("web/favicon.svg", svg(32, 32, mark(INK, PAPER, PROOF)))
    png(square, "web/apple-touch-icon.png", 180)
    for size in (16, 32, 48, 192, 512):
        png(square, f"web/icon-{size}.png", size)

    # Preview of the kit, for the README.
    pw, ph = 960, 360
    body = (
        f'<rect width="{pw / 2}" height="{ph}" fill="{TABLE}"/>'
        f'<rect x="{pw / 2}" width="{pw / 2}" height="{ph}" fill="{NIGHT}"/>'
        + mark(INK, PAPER, PROOF, x=48, y=56, scale=3)
        + f'<g transform="translate(48 240) scale(1.6)">{mark(INK, PAPER, PROOF)}'
        f'<path transform="translate(40 23.6)" d="{word}" fill="{INK}"/></g>'
        + mark(FOG, NIGHT, PROOF_DARK, x=pw / 2 + 48, y=56, scale=3)
        + f'<g transform="translate({pw / 2 + 48} 240) scale(1.6)">{mark(FOG, NIGHT, PROOF_DARK)}'
        f'<path transform="translate(40 23.6)" d="{word}" fill="{FOG}"/></g>'
        + f'<image href="icons/icon-rounded-1024.png" x="{pw - 48 - 128}" y="56" width="128" height="128"/>'
    )
    preview = write("preview.svg", svg(pw, ph, body))
    subprocess.run(["rsvg-convert", "-w", str(pw * 2), preview, "-o", os.path.join(BRAND, "preview.png")], check=True,
                   cwd=BRAND)
    os.remove(preview)
    print(f"wrote {len(files)} logo SVGs, PNG logos, app icons, web icons and preview.png")


if __name__ == "__main__":
    main()
