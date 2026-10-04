#!/usr/bin/env bash
# Build listing-review.html — a single, static, read-only review page for the
# fastlane listing at the app root: store copy (copy buttons + char counts),
# screenshots grouped by device class, generated graphics, and the validator's
# output embedded verbatim. Open the file in any browser; no server needed.
#
# Usage: build-review.sh [<app-root>]    (default: current directory)
# Exit:  0 = wrote listing-review.html, 1 = generation failed, 2 = usage / no fastlane / no python3.
# Read-only: never writes into fastlane/.
set -uo pipefail

ROOT="${1:-.}"
[ -d "$ROOT" ] || { echo "Not a directory: $ROOT" >&2; exit 2; }
[ -d "$ROOT/fastlane" ] || { echo "No fastlane/ tree under: $ROOT (run Assemble first)." >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "Need python3 to build the review page." >&2; exit 2; }

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALIDATOR="$SELF_DIR/../validate/validate-listing.sh"

# Run the validator and strip ANSI so its output embeds cleanly. Never fail the
# build on a validator non-zero exit — we embed whatever it reported.
VAL_TXT="$(mktemp)"; trap 'rm -f "$VAL_TXT"' EXIT
if [ -f "$VALIDATOR" ]; then
  (cd "$ROOT" && bash "$VALIDATOR" .) 2>&1 | sed $'s/\x1b\\[[0-9;]*m//g' > "$VAL_TXT" || true
else
  echo "(validate-listing.sh not found; validation section omitted)" > "$VAL_TXT"
fi

OUT="$ROOT/listing-review.html"
python3 - "$ROOT" "$VAL_TXT" "$OUT" "$SELF_DIR/../lib" <<'PY' || { echo "Error: review page generation failed." >&2; exit 1; }
import sys, os, html, datetime

root, val_txt, out_path, lib_dir = sys.argv[1:5]
sys.path.insert(0, lib_dir)
from imginfo import image_info, apple_class
import fields as store_fields
import listing

FL = os.path.join(root, "fastlane")
generated_at = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

read = store_fields.read

def dims(p):
    w, h = image_info(p)[:2]
    return (w, h) if w else None

images = listing.images

def devclass(wh):
    if not wh:
        return "?"
    return apple_class(*wh) or f"{wh[0]}×{wh[1]}"

def esc(s):
    return html.escape(s if s is not None else "")

def copy_row(label, path):
    """An app-level field with no limit (copyright, category)."""
    v = read(path)
    return dict(label=label, value=v, limit=None, unit="chars", required=False,
                count=(len(v) if v is not None else None))

platforms = {}  # name -> {locales:[...], applevel:[...]}

# ---- iOS (deliver) ----
ios_locs = listing.apple_locales(FL)
apple_default = listing.apple_default(FL)
if ios_locs or os.path.isdir(os.path.join(FL, "screenshots")):
    locs = []
    for ld in ios_locs:
        loc = os.path.basename(ld)
        fields = store_fields.rows("apple", ld, apple_default)
        shots = {}
        for f in images(os.path.join(FL, "screenshots", loc)):
            cls = devclass(dims(f))
            shots.setdefault(cls, []).append(os.path.relpath(f, root))
        locs.append(dict(locale=loc, fields=fields, shots=shots, graphics=[]))
    applevel = [
        copy_row("Copyright", os.path.join(FL, "metadata", "copyright.txt")),
        copy_row("Primary category", os.path.join(FL, "metadata", "primary_category.txt")),
    ]
    platforms["iOS"] = dict(locales=locs, applevel=applevel)

# ---- Android (supply) ----
A = os.path.join(FL, "metadata", "android")
if os.path.isdir(A):
    locs = []
    for ld in listing.play_locales(FL):
        loc = os.path.basename(ld)
        fields = store_fields.rows("play", ld)
        shots = {}
        for sub, lbl in [("phoneScreenshots", "Phone"), ("sevenInchScreenshots", '7" tablet'),
                         ("tenInchScreenshots", '10" tablet'), ("tvScreenshots", "TV"),
                         ("wearScreenshots", "Wear")]:
            fs = images(os.path.join(ld, "images", sub))
            if fs:
                shots[lbl] = [os.path.relpath(f, root) for f in fs]
        graphics = []
        # supply uploads images/featureGraphic.<ext> and images/icon.<ext> directly.
        for name, lbl in [("featureGraphic", "Feature graphic"), ("icon", "Icon")]:
            for f in images(os.path.join(ld, "images")):
                if os.path.splitext(os.path.basename(f))[0].lower() == name.lower():
                    graphics.append((lbl, os.path.relpath(f, root), dims(f)))
        locs.append(dict(locale=loc, fields=fields, shots=shots, graphics=graphics))
    platforms["Android"] = dict(locales=locs, applevel=[])

val_output = read(val_txt) or ""

# ---- render helpers ----
def badge(r):
    if r.get("error"):
        return f'<span class="b bad">{esc(r["error"])}</span>'
    if r["count"] is None:
        return '<span class="b warn">missing</span>' if r["required"] else '<span class="b opt">optional</span>'
    if "stem" in r:  # a store field: same verdict as validate-listing.sh
        level = store_fields.check(r)[0]
    else:
        level = "PASS"
    cls = {"PASS": "ok", "WARN": "warn", "FAIL": "bad"}[level]
    if r["limit"] is None:
        return f'<span class="b {cls}">{"set" if level == "PASS" else "check"}</span>'
    unit = " bytes" if r["unit"] == "bytes" else ""
    return f'<span class="b {cls}">{r["count"]}/{r["limit"]}{unit}</span>'

def render_field(r):
    if r["value"] is None:
        return (f'<div class="row"><div class="lbl">{esc(r["label"])}</div>'
                f'<div class="field"><span class="missing">— not set —</span></div>{badge(r)}</div>')
    return (f'<div class="row"><div class="lbl">{esc(r["label"])}</div>'
            f'<div class="field"><span class="v">{esc(r["value"])}</span></div>{badge(r)}'
            f'<button class="copy" onclick="cp(this)" data-v="{esc(r["value"])}">Copy</button></div>')

def render_shots(shots):
    if not shots:
        return '<p class="muted">No screenshots.</p>'
    out = []
    for cls, files in shots.items():
        out.append(f'<div class="dc">{esc(cls)} <span class="muted">({len(files)})</span></div><div class="gal">')
        for rel in files:
            out.append(f'<a href="{esc(rel)}" target="_blank"><img src="{esc(rel)}" loading="lazy"><span>{esc(os.path.basename(rel))}</span></a>')
        out.append('</div>')
    return "".join(out)

def render_graphics(graphics):
    if not graphics:
        return ""
    out = ['<div class="dc">Graphics</div><div class="gal">']
    for lbl, rel, wh in graphics:
        sz = f"{wh[0]}×{wh[1]}" if wh else ""
        out.append(f'<a href="{esc(rel)}" target="_blank"><img src="{esc(rel)}" loading="lazy"><span>{esc(lbl)} {sz}</span></a>')
    out.append('</div>')
    return "".join(out)

tabs, panels, app_name = [], [], ""
for i, (plat, data) in enumerate(platforms.items()):
    on = " on" if i == 0 else ""
    tabs.append(f'<button class="tab{on}" data-p="{esc(plat)}" onclick="show(\'{esc(plat)}\')">{esc(plat)}</button>')
    body = []
    for L in data["locales"]:
        left = "".join(render_field(r) for r in L["fields"]) + "".join(render_field(r) for r in data["applevel"])
        right = render_shots(L["shots"]) + render_graphics(L["graphics"])
        body.append(f'<div class="loc"><div class="loclabel">locale: {esc(L["locale"])}</div>'
                    f'<div class="cols"><div class="left">{left}</div><div class="right">{right}</div></div></div>')
    panels.append(f'<section class="panel{on}" id="p-{plat}">{"".join(body)}</section>')

for plat in ("iOS", "Android"):
    if plat in platforms and platforms[plat]["locales"]:
        v0 = platforms[plat]["locales"][0]["fields"][0]["value"]
        if v0:
            app_name = v0
            break

CSS = """
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f7f5f0;color:#2b2b2b}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid #e6e1d6;padding:14px 20px;z-index:5}
header h1{margin:0;font-size:16px}
header .app{color:#7a7468;font-size:13px;margin-top:2px}
header .meta{color:#9a948a;font-size:12px;margin-top:2px}
.tabs{margin-top:10px;display:flex;gap:8px}
.tab{padding:6px 14px;border:1px solid #ddd6c8;background:#faf8f3;border-radius:8px;cursor:pointer;font:inherit}
.tab.on{background:#A69060;color:#fff;border-color:#A69060}
.val{margin:16px 20px;background:#1f1d1a;color:#e8e4da;border-radius:10px;overflow:auto}
.val pre{margin:0;padding:14px 16px;font:12px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap}
.panel{display:none;padding:0 20px 48px}
.panel.on{display:block}
.loclabel{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#9a948a;margin:8px 0}
.cols{display:flex;gap:24px;align-items:flex-start}
.left{flex:1;min-width:0}
.right{flex:1;min-width:0}
.row{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #ece8df}
.lbl{width:130px;color:#7a7468;flex:none}
.field{flex:1;min-width:0;background:#fff;border:1px solid #e6e1d6;border-radius:6px;padding:6px 8px;max-height:120px;overflow:auto}
.v{white-space:pre-wrap;word-break:break-word}
.missing{color:#b3261e;font-style:italic}
.b{flex:none;font-size:12px;padding:2px 8px;border-radius:10px}
.b.ok{background:#e7f5ea;color:#1c6b3a}
.b.bad{background:#fdecec;color:#b3261e}
.b.warn{background:#fff4e5;color:#9a5b00}
.b.opt{background:#eee;color:#888}
.copy{flex:none;background:#A69060;color:#fff;border:0;border-radius:6px;padding:4px 10px;cursor:pointer;font:inherit}
.dc{margin:14px 0 6px;font-weight:600}
.muted{color:#9a948a;font-weight:400}
.gal{display:flex;flex-wrap:wrap;gap:10px}
.gal a{text-decoration:none;color:#7a7468;font-size:11px;text-align:center}
.gal img{display:block;width:120px;border:1px solid #ddd6c8;border-radius:6px;background:#fff}
.gal span{display:block;margin-top:4px;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@media(max-width:720px){.cols{flex-direction:column}}
"""

JS = """
function show(p){document.querySelectorAll('.panel').forEach(function(e){e.classList.toggle('on',e.id=='p-'+p)});
document.querySelectorAll('.tab').forEach(function(e){e.classList.toggle('on',e.dataset.p==p)});}
function flash(b){var o=b.textContent;b.textContent='Copied';setTimeout(function(){b.textContent=o},1000);}
function fb(t,b){var a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();
try{document.execCommand('copy')}catch(e){}a.remove();flash(b);}
function cp(b){var t=b.dataset.v;if(navigator.clipboard){navigator.clipboard.writeText(t).then(function(){flash(b)}).catch(function(){fb(t,b)});}else{fb(t,b);}}
"""

page = (f'<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>Listing review — {esc(app_name)}</title><style>{CSS}</style></head><body>'
        f'<header><h1>Listing review</h1><div class="app">{esc(app_name)}</div>'
        f'<div class="meta">Generated {esc(generated_at)} from fastlane metadata .txt files. '
        f'Rerun build-review.sh after editing copy.</div>'
        f'<div class="tabs">{"".join(tabs)}</div></header>'
        f'<div class="val"><pre>{esc(val_output)}</pre></div>'
        f'{"".join(panels)}'
        f'<script>{JS}</script></body></html>\n')

open(out_path, "w", encoding="utf-8").write(page)
print(f"Wrote {out_path}")
PY
echo "Open it in a browser: $OUT"
