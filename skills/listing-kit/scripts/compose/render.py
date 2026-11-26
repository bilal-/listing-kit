#!/usr/bin/env python3
"""Render one marketing image from a bundled template. Standard library only.

This is the layer between the plan and the browser: it takes plain values (text,
colours, font files, a raw capture, a size), fills a template, renders it through
cdp.Renderer with every request served from an allow-list, and reports the checks
that need a browser (fit, contrast). It knows nothing about listing.json.
"""
import html
import os
import re

import cdp
import fontcheck

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.normpath(os.path.join(HERE, "..", "..", "templates"))
RTL = {"ar", "he", "fa", "ur", "ps", "sd", "yi", "dv"}
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
# Text is "large" (3:1 is enough) from this many px on a 390-px-wide phone.
LARGE_PX, LARGE_BOLD_PX, REF_WIDTH = 24.0, 19.0, 390.0
# A caption or detail line that wraps further than this is too long for the canvas.
MAX_LINES = 2


class RenderError(Exception):
    pass


def text_dir(locale):
    return "rtl" if locale.split("-")[0].lower() in RTL else "ltr"


def luminance(hex_colour):
    out = []
    for i in (1, 3, 5):
        c = int(hex_colour[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def worst_contrast(colour, backgrounds):
    return min(contrast(colour, b) for b in backgrounds)


def needed_ratio(px, bold, canvas_short_side):
    scaled = px * REF_WIDTH / canvas_short_side
    return 3.0 if scaled >= LARGE_PX or (bold and scaled >= LARGE_BOLD_PX) else 4.5


def _fonts_css(fonts):
    """fonts: {"headline": [paths], "detail": [paths]} -> (css, assets). Each role is one
    family built from the files in order, so a later file supplies missing characters."""
    css, assets = [], {}
    for role, family in (("headline", "LK Headline"), ("detail", "LK Detail")):
        paths = fonts.get(role) or []
        if not paths:
            raise RenderError("no font given for %s" % role)
        for i, path in enumerate(paths):
            ext = os.path.splitext(path)[1].lower()
            if ext not in (".ttf", ".otf"):
                raise RenderError("font must be .ttf or .otf: %s" % path)
            url = "/fonts/%s-%d%s" % (role, i, ext)
            assets[url] = path
            # One family per file, listed in order in font-family below.
            css.append('@font-face{font-family:"%s %d";src:url(%s)}' % (family, i, url))
        stack = ",".join('"%s %d"' % (family, i) for i in range(len(paths)))
        css.append('.lk-%s{font-family:%s}' % (role, stack))
        css.append('@font-face{font-family:"%s";src:%s}' % (
            family, ",".join("url(/fonts/%s-0%s)" % (role, os.path.splitext(paths[0])[1].lower()) for _ in (0,))))
        css.append(':root{--font-%s:%s}' % (role, stack))
    return "\n".join(css), assets


def _vars(style, shot=None):
    pal = style["palette"]
    bg = pal["background"] if isinstance(pal["background"], list) else [pal["background"]]
    for c in bg + [pal["ink"], pal.get("detail", pal["ink"])]:
        if not HEX.match(c):
            raise RenderError("colour must be #RRGGBB: %r" % (c,))
    bezel = style.get("bezel", {})
    v = {"--bg-a": bg[0], "--bg-b": bg[-1], "--ink": pal["ink"], "--detail": pal.get("detail", pal["ink"]),
         "--bezel": bezel.get("color", pal["ink"]), "--bezel-w": str(bezel.get("width", 1.2)),
         "--radius": str(bezel.get("radius", 5)), "--shadow": bezel.get("shadow", "#00000040")}
    if shot:
        v["--shot-w"], v["--shot-h"] = str(shot[0]), str(shot[1])
    return ":root{%s}\n.headline{font-family:var(--font-headline)}\n.detail,.rows dd{font-family:var(--font-detail)}\n" % (
        ";".join("%s:%s" % kv for kv in sorted(v.items())))


PROBE = """(() => {
  const out = {overflow: [], text: [], device: null};
  const W = innerWidth, H = innerHeight;
  for (const el of document.querySelectorAll('[data-check="text"]')) {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    const over = Math.max(el.scrollWidth - Math.ceil(r.width), -r.left, r.right - W, r.bottom - H, -r.top, 0);
    if (over > 1) out.overflow.push({text: el.textContent.slice(0, 60), by: Math.round(over)});
    const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.2;
    out.text.push({px: parseFloat(cs.fontSize), bold: parseInt(cs.fontWeight) >= 600, colour: cs.color,
                   lines: Math.round(r.height / lh), sample: el.textContent.slice(0, 60),
                   top: r.top / H, bottom: r.bottom / H, area: (r.width * r.height) / (W * H), empty: !el.textContent.trim()});
  }
  const d = document.querySelector('[data-check="device"]');
  if (d) { const r = d.getBoundingClientRect();
    out.device = {left: r.left, top: r.top, right: r.right, bottom: r.bottom, cutBottom: Math.max(r.bottom - H, 0) / r.height}; }
  return out; })()"""


def _fill(template, values):
    with open(os.path.join(TEMPLATES, template + ".html"), encoding="utf-8") as f:
        page = f.read()

    def sub(m):
        key = m.group(1)
        if key not in values:
            raise RenderError("template %s needs a value for %s" % (template, key))
        return values[key]
    return re.sub(r"\{\{(\w+)\}\}", sub, page)


def _brand(logo, icon, name, assets):
    if logo:
        assets["/logo" + os.path.splitext(logo)[1].lower()] = logo
        return '<img class="logo" src="/logo%s" alt="">' % os.path.splitext(logo)[1].lower()
    parts = ""
    if icon:
        assets["/icon" + os.path.splitext(icon)[1].lower()] = icon
        parts += '<img class="icon" src="/icon%s" alt="">' % os.path.splitext(icon)[1].lower()
    return parts + '<span class="name">%s</span>' % html.escape(name or "")


def render(renderer, template, size, locale, style, fonts, text, raw=None, shot_size=None,
           logo=None, icon=None, app_name=None, fit="contain"):
    """Render one image. Returns (png bytes, report). report["problems"] lists failures.

    text: {"caption","detail"} for screenshots, {"headline","detail","rows":[(label,text)]}
    for panels and graphics. Everything in text is inserted as text, never as markup.
    """
    width, height = size
    fonts_css, assets = _fonts_css(fonts)
    problems = []
    for role, keys in (("headline", ("caption", "headline")), ("detail", ("detail",))):
        joined = "".join(text.get(k) or "" for k in keys)
        if role == "detail":
            joined += "".join(a + b for a, b in text.get("rows", []))
        gone = fontcheck.missing(joined, fonts[role])
        if gone:
            problems.append("no %s font has: %s" % (role, ", ".join(fontcheck.describe(c) for c in gone)))
    esc = lambda s: html.escape(s or "")  # noqa: E731
    values = {"lang": html.escape(locale), "dir": text_dir(locale), "fit": fit if fit in ("contain", "bleed", "cover") else "contain",
              "caption": esc(text.get("caption")), "detail": esc(text.get("detail")), "headline": esc(text.get("headline")),
              "rows": "".join("<div><dt>%s</dt><dd>%s</dd></div>" % (esc(a), esc(b)) for a, b in text.get("rows", [])),
              "brand": _brand(logo, icon, app_name, assets) if template in ("panel", "feature") else ""}
    assets["/index.html"] = _fill(template, values).encode("utf-8")
    assets["/fonts.css"] = (fonts_css + "\n" + _vars(style, shot_size)).encode("utf-8")
    assets["/base.css"] = os.path.join(TEMPLATES, "base.css")
    if raw:
        assets["/raw.png"] = raw
    png, info = renderer.render(assets, width, height, probe=PROBE)
    refused = [u for u in renderer.refused if not u.endswith("/favicon.ico")]
    if refused:
        problems.append("template asked for something outside its allow-list: %s" % ", ".join(refused[:3]))
    for o in info["overflow"]:
        problems.append("text does not fit (%d px over): %s" % (o["by"], o["text"]))
    for t in info["text"]:
        if not t["empty"] and t["lines"] > MAX_LINES:
            problems.append("text takes %d lines (at most %d): %s" % (t["lines"], MAX_LINES, t["sample"]))
    pal = style["palette"]
    bgs = pal["background"] if isinstance(pal["background"], list) else [pal["background"]]
    short = min(width, height)
    worst = None
    for t, colour in zip(info["text"], [pal["ink"], pal.get("detail", pal["ink"])]):
        if t["empty"]:
            continue
        need, have = needed_ratio(t["px"], t["bold"], short), worst_contrast(colour, bgs)
        worst = have if worst is None else min(worst, have)
        if have < need:
            problems.append("contrast %.2f:1 for %s on the background, needs %.1f:1" % (have, colour, need))
    dev = info.get("device")
    if dev and fit == "contain" and dev["cutBottom"] > 0.001:
        problems.append("the capture is cut off at the bottom (%.0f%%)" % (dev["cutBottom"] * 100))
    report = {"problems": problems, "overflow": info["overflow"], "worstContrast": worst,
              "textShare": round(sum(t["area"] for t in info["text"] if not t["empty"]), 4),
              "device": dev, "bleedCut": dev["cutBottom"] if dev else 0}
    return png, report


def open_browser():
    b = cdp.Browser()
    return b, cdp.Renderer(b)
