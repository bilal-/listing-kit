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
import sys
import pixels

import cdp
import fontcheck

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.normpath(os.path.join(HERE, "..", "..", "templates"))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import template_values

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


def needed_ratio(px, bold, canvas_width):
    scaled = px * REF_WIDTH / canvas_width
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
        css.append(':root{--font-%s:%s}' % (role, stack))
    return "\n".join(css), assets


def _vars(style, shot=None):
    pal = style.get("palette") or {}
    bg = pal.get("background")
    bezel = style.get("bezel") or {}
    if not isinstance(bg, list) or not bg:
        raise RenderError("palette.background must be a non-empty colour list")
    for c in bg + [pal.get("ink"), pal.get("detail", pal.get("ink")),
                   bezel.get("color", pal.get("ink")), bezel.get("shadow", "#00000040")]:
        if not template_values.colour(c):
            raise RenderError("colour must be #RRGGBB or #RRGGBBAA: %r" % c)
    for key, limit in (("width", 10), ("radius", 50)):
        if key in bezel and not template_values.measurement(bezel[key], limit):
            raise RenderError("bezel.%s must be a number in [0,%d]" % (key, limit))
    if shot and (len(shot) != 2 or any(type(n) is not int or not 0 < n <= 100000 for n in shot)):
        raise RenderError("invalid capture dimensions")
    v = {"--bg-a": bg[0], "--bg-b": bg[-1], "--ink": pal["ink"], "--detail": pal.get("detail", pal["ink"]),
         "--bezel": bezel.get("color", pal["ink"]), "--bezel-w": str(bezel.get("width", 1.2)),
         "--radius": str(bezel.get("radius", 5)), "--shadow": bezel.get("shadow", "#00000040")}
    if shot:
        v["--shot-w"], v["--shot-h"] = str(shot[0]), str(shot[1])
    return ":root{%s}" % ";".join("%s:%s" % kv for kv in sorted(v.items()))


PROBE = r"""(() => {
  const out = {overflow: [], text: [], device: null};
  const W = innerWidth, H = innerHeight;
  for (const el of document.querySelectorAll('[data-check="text"]')) {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    const over = Math.max(el.scrollWidth - Math.ceil(r.width), -r.left, r.right - W, r.bottom - H, -r.top, 0);
    if (over > 1) out.overflow.push({text: el.textContent.slice(0, 60), by: Math.round(over)});
    const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.2;
    const rgba = cs.color.match(/[\d.]+/g).map(Number);
    let opacity = rgba.length === 4 ? rgba.pop() : 1;
    for (let node=el; node; node=node.parentElement) opacity *= Number(getComputedStyle(node).opacity);
    rgba.push(opacity);
    out.text.push({rect:[r.left,r.top,r.right,r.bottom], rgba, px: parseFloat(cs.fontSize), bold: parseInt(cs.fontWeight) >= 600, colour: cs.color,
                   lines: Math.round(r.height / lh), sample: el.textContent.slice(0, 60),
                   top: r.top / H, bottom: r.bottom / H, area: (r.width * r.height) / (W * H), empty: !el.textContent.trim()});
  }
  const d = document.querySelector('[data-check="device"]');
  if (d) {
    const img = d.matches("img") ? d : d.querySelector("img");
    const r = img.getBoundingClientRect(), fit = getComputedStyle(img).objectFit;
    const sw = r.width / img.naturalWidth, sh = r.height / img.naturalHeight;
    const scale = fit === "contain" ? Math.min(sw,sh) : Math.max(sw,sh);
    const w = img.naturalWidth*scale, h = img.naturalHeight*scale;
    const x = r.left+(r.width-w)/2, y = r.top+(r.height-h)/2;
    let l=Math.max(0,r.left,x), t=Math.max(0,r.top,y);
    let right=Math.min(W,r.right,x+w), bottom=Math.min(H,r.bottom,y+h);
    for (let node=img.parentElement; node; node=node.parentElement) {
      if (getComputedStyle(node).overflow === "visible") continue;
      const box=node.getBoundingClientRect();
      l=Math.max(l,box.left); t=Math.max(t,box.top);
      right=Math.min(right,box.right); bottom=Math.min(bottom,box.bottom);
    }
    const visible=Math.max(0,right-l)*Math.max(0,bottom-t);
    out.device={objectFit:fit, crop:w*h ? Math.max(0,1-visible/(w*h)) : 1,
                cutBottom:Math.max(0,y+h-bottom)/h};
  }
  return out; })()"""


def _fill(template, values):
    template_values.template_name(template)
    with open(os.path.join(TEMPLATES, template + ".html"), encoding="utf-8") as f:
        page = f.read()

    def sub(m):
        key = m.group(1)
        if key not in values:
            raise RenderError("template %s needs a value for %s" % (template, key))
        return values[key]
    return re.sub(r"\{\{(\w+)\}\}", sub, page)


def _brand(logo, icon, name, assets):
    if logo or icon:
        path = logo or icon
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".png", ".svg", ".jpg", ".jpeg", ".webp"):
            raise RenderError("unsupported brand image: %s" % path)
        role = "logo" if logo else "icon"
        url = "/" + role + ext
        assets[url] = path
        image = '<img class="%s" src="%s" alt="">' % (role, url)
        if logo:
            return image
    else:
        image = ""
    return image + '<span class="name" data-check="text">%s</span>' % html.escape(name or "")


def page_assets(template, locale, style, fonts, text, raw=None, shot_size=None,
                logo=None, icon=None, app_name=None, fit="contain"):
    template_values.template_name(template)
    fonts_css, assets = _fonts_css(fonts)
    esc = lambda s: html.escape(s or "")  # noqa: E731
    values = {"lang": html.escape(locale), "dir": text_dir(locale), "fit": fit if fit in ("contain", "bleed", "cover") else "contain",
              "caption": esc(text.get("caption")), "detail": esc(text.get("detail")), "headline": esc(text.get("headline")),
              "rows": "".join('<div><dt data-check="text">%s</dt><dd data-check="text">%s</dd></div>'  % (esc(a), esc(b)) for a, b in text.get("rows", [])),
              "brand": _brand(logo, icon, app_name, assets) if template in ("panel", "feature", "header") else ""}
    assets["/index.html"] = _fill(template, values).encode("utf-8")
    assets["/fonts.css"] = (fonts_css + "\n" + _vars(style, shot_size)).encode("utf-8")
    assets["/base.css"] = os.path.join(TEMPLATES, "base.css")
    if raw:
        assets["/raw.png"] = raw
    return assets


def render(renderer, template, size, locale, style, fonts, text, raw=None, shot_size=None,
           logo=None, icon=None, app_name=None, fit="contain"):
    width, height = size
    assets = page_assets(template, locale, style, fonts, text, raw, shot_size, logo, icon, app_name, fit)
    problems = []
    headline = [text.get("caption") or text.get("headline") or ""]
    detail = [text.get("detail") or ""]
    if template == "panel":
        for label, value in text.get("rows", []):
            headline.append(label.upper())
            detail.append(value)
    if template in ("panel", "feature", "header") and not logo:
        headline.append(app_name or "")
    for role, strings in (("headline", headline), ("detail", detail)):
        gone = fontcheck.missing(" ".join(strings), fonts[role])
        if gone:
            problems.append("no %s font has: %s" % (role, ", ".join(fontcheck.describe(c) for c in gone)))
    png, info = renderer.render(assets, width, height, probe=PROBE, background=True)
    refused = [u for u in renderer.refused if not u.endswith("/favicon.ico")]
    if refused:
        problems.append("template asked for something outside its allow-list: %s" % ", ".join(refused[:3]))
    for o in info["overflow"]:
        problems.append("text does not fit (%d px over): %s" % (o["by"], o["text"]))
    for t in info["text"]:
        if not t["empty"] and t["lines"] > MAX_LINES:
            problems.append("text takes %d lines (at most %d): %s" % (t["lines"], MAX_LINES, t["sample"]))
    worst = None
    ratios = pixels.contrast_boxes(info.pop("background"), size, info["text"])
    for t, have in zip(info["text"], ratios):
        if t["empty"]:
            continue
        need = needed_ratio(t["px"], t["bold"], width)
        worst = have if worst is None else min(worst, have)
        if have < need:
            problems.append("contrast %.2f:1 for %s (%s), needs %.1f:1" % (have, t["sample"], t["colour"], need))
    dev = info.get("device")
    if dev and fit == "contain" and dev["crop"] > 0.00001:
        problems.append("the capture is cropped (%.2f%%)" % (dev["crop"] * 100))
    report = {"problems": problems, "overflow": info["overflow"], "worstContrast": worst,
              "textShare": round(sum(t["area"] for t in info["text"] if not t["empty"]), 4),
              "device": dev, "bleedCut": dev["cutBottom"] if dev else 0}
    return png, report


def open_browser():
    b = cdp.Browser()
    return b, cdp.Renderer(b)
