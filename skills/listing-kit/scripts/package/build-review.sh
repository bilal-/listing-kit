#!/usr/bin/env bash
# Build listing-review.html — a single, static, read-only review page for the
# fastlane listing at the app root: store copy (copy buttons + char counts),
# screenshots grouped by device class, generated graphics, and the validator's
# output embedded verbatim. Open the file in any browser; no server needed.
#
# Usage: build-review.sh [<app-root>]    (default: current directory)
# Exit:  0 = wrote listing-review.html, 1 = generation failed, 2 = usage / scan error, 3 = credential found.
# Read-only: never writes into fastlane/.
set -uo pipefail

ROOT=; prepared=0; coverage_view=; options=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help) echo "Usage: listing-kit review [app-root] [--verbose] [--as-of YYYY-MM-DD] [--ios-sdk X.Y]"; exit 0 ;;
    --prepared) prepared=1 ;;
    --coverage-view) [ "$#" -ge 2 ] || exit 2; coverage_view="$2"; options+=("$1" "$2"); shift ;;
    --verbose) options+=("$1") ;;
    --as-of|--ios-sdk)
      [ "$#" -ge 2 ] && [ -n "$2" ] || { echo "$1 needs a value" >&2; exit 2; }
      options+=("$1" "$2"); shift ;;
    -*) echo "Unknown option: $1" >&2; exit 2 ;;
    *) [ -z "$ROOT" ] || { echo "Expected one app root" >&2; exit 2; }; ROOT="$1" ;;
  esac
  shift
done
ROOT="${ROOT:-.}"
[ -d "$ROOT" ] || { echo "Not a directory: $ROOT" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "Need python3 to build the review page." >&2; exit 2; }

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$prepared" = 0 ]; then
  exec python3 -I -B "$SELF_DIR/../lib/review_inputs.py" "$SELF_DIR/${BASH_SOURCE[0]##*/}" "$ROOT" ${options[@]+"${options[@]}"}
fi
VALIDATOR="$SELF_DIR/../validate/validate-listing.sh"

# Keep the transcript visible even if the validator exits without a matching verdict.
VAL_RAW="$(mktemp)"; VAL_TXT="$(mktemp)"
trap 'rm -f "$VAL_RAW" "$VAL_TXT"' EXIT
if [ ! -f "$VALIDATOR" ]; then
  echo "Error: failed to capture validation transcript (missing $VALIDATOR)." >&2
  exit 1
fi
val_rc=0
bash "$VALIDATOR" "$ROOT" --prepared --review ${options[@]+"${options[@]}"} >"$VAL_RAW" 2>&1 || val_rc=$?
case "$val_rc" in
  3|4) cat "$VAL_RAW" >&2; [ "$val_rc" = 3 ] && exit 3; exit 2 ;;
esac
if ! LC_ALL=C sed $'s/\x1b\\[[0-9;]*m//g' "$VAL_RAW" > "$VAL_TXT"; then
  echo "Error: failed to capture validation transcript." >&2
  exit 1
fi
verdict="$(awk 'NF {last=$0} END {print last}' "$VAL_TXT")"
crash=""
case "$val_rc/$verdict" in
  "0/LISTING VALID"|"1/LISTING HAS FAILURES") ;;
  *) crash="validator crashed (exit $val_rc): missing or inconsistent final verdict"
     echo "$crash" >&2
     # A crash may precede the validator's scan. Scan before rendering its report.
     scan_rc=0
     bash "$SELF_DIR/../lib/secret-scan.sh" --prepared-listing "$ROOT" >/dev/null || scan_rc=$?
     case "$scan_rc" in 0) ;; 1) exit 3 ;; *) exit 2 ;; esac ;;
esac

OUT="$ROOT/listing-review.html"
python3 -I -B - "$ROOT" "$VAL_TXT" "$OUT" "$SELF_DIR/../lib" "$crash" "$coverage_view" <<'PY' || { rc=$?; echo "Error: review page generation failed." >&2; exit "$rc"; }
import sys, os, html, datetime
from urllib.parse import quote

root, val_txt, out_path, lib_dir = sys.argv[1:5]
sys.path.insert(0, lib_dir)
from imginfo import image_info
import fields as store_fields
import listing
import specs
import detect
import apple_assets
import screenshots
from secret_scan import secret_text

trees = listing.paths(root)
apple_tree, play_tree = trees["apple"], trees["play"]
generated_at = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

try:
    rules = specs.load(root)
except specs.SpecsError:
    rules = specs.load()  # Keep the review available when local rules cannot be read.
requirements = detect.Requirements(root, rules)
read = store_fields.read


def field_rows(store, directory, fallback=None):
    return store_fields.rows(store, directory, fallback, rules, requirements)

def dims(p):
    w, h = image_info(p)[:2]
    return (w, h) if w else None

images = listing.images

def esc(s):
    s = s or ""
    if secret_text(s.encode("utf-8")):
        print("POTENTIAL SECRET in review text", file=sys.stderr)
        sys.exit(3)
    return html.escape(s)

platforms = {}  # name -> {locales:[...], applevel:[...]}
try:
    coverage = apple_assets.load_coverage(root, rules, sys.argv[6])
except (OSError, ValueError):
    coverage = {"apple": {}}  # The validation section displays the malformed plan error.

descriptions = coverage.get("descriptions", {})
apple_plan = coverage["apple"]
planned = "play" in coverage
requirements.apply_inferred(coverage.get("inferred", {}))

def screenshot_groups(store, locale, deferred=(), suffixes=None):
    groups = {}
    for shot in screenshots.active(root, store, locale, rules, deferred, suffixes=suffixes, tree=trees[store]):
        if shot.manual and shot.error:
            sys.exit(shot.error)
        label = shot.slot["label"] if shot.slot else "{}×{}".format(*shot.size)
        if shot.platform == "iMessage":
            label = "iMessage " + label
        groups.setdefault(label, []).append(os.path.relpath(shot.path, root))
    return groups

# ---- iOS (deliver) ----
ios_locs = apple_assets.apple_locales(root, rules, apple_plan, apple_tree)
apple_default = listing.apple_default(apple_tree["metadata"], rules)
# A filtered legacy view has a generated listing.json that only pins its layout.
legacy_view = sys.argv[6] and not planned and os.path.isfile(os.path.join(root, apple_assets.LEGACY))
if legacy_view or apple_assets.has_apple_listing(root, rules, ios_locs, apple_tree):
    locs = []
    for ld in ios_locs:
        loc = os.path.basename(ld)
        fields = field_rows("apple", ld, apple_default)
        entry = apple_plan.get(loc, {})
        deferred = list(apple_assets.reported_deferrals(entry, rules, planned))
        deferred_ids = apple_assets.deferred_slots(rules, entry.get("deferredScreenshots", {}), planned)
        shots = screenshot_groups("apple", loc, deferred_ids, entry.get("suffixes"))
        graphics = []
        for f in images(apple_assets.header_dir(apple_tree, loc)):
            info = image_info(f)
            graphic = apple_assets.header_rule(f, info, rules)
            label = "Header Asset (manual console upload)"
            if graphic:
                label += " · " + graphic["label"]
            graphics.append((label, os.path.relpath(f, root), info[:2] if info[0] else None))
        locs.append(dict(locale=loc, fields=fields, shots=shots, graphics=graphics, deferred=deferred))
    if not locs and apple_default:
        locs.append(dict(locale="default", fields=field_rows("apple", apple_default),
                         shots={}, graphics=[], deferred={}))
    applevel = field_rows("apple-app", apple_tree["metadata"])
    platforms["iOS"] = dict(locales=locs, applevel=applevel)

# ---- Android (supply) ----
A = play_tree["metadata"]
play_locales = ([A / code for code in listing.play_asset_locales(play_tree, coverage["play"])]
                if planned else listing.play_locales(A))
if os.path.isdir(A) or play_locales:
    locs = []
    for ld in play_locales:
        loc = os.path.basename(ld)
        fields = field_rows("play", ld)
        shots = screenshot_groups("play", loc)
        graphics = []
        # supply reads the graphics directly from the locale images directory.
        for graphic in rules["stores"]["play"]["graphics"]:
            name, lbl = graphic["file"], graphic["label"]
            for f in images(os.path.join(ld, "images")):
                if os.path.splitext(os.path.basename(f))[0].lower() == name.lower():
                    graphics.append((lbl, os.path.relpath(f, root), dims(f)))
        locs.append(dict(locale=loc, fields=fields, shots=shots, graphics=graphics))
    platforms["Android"] = dict(locales=locs, applevel=[])

val_output = read(val_txt) or ""
if sys.argv[5]:
    val_output = sys.argv[5] + "\n\n" + val_output

# ---- render helpers ----
app_name = ""
import re

LEVEL_CLASS = {"PASS": "ok", "WARN": "warn", "FAIL": "bad"}


def field_level(r):
    if r.get("error"):
        return "bad"
    if r["count"] is None:
        return "warn" if r["required"] else "opt"
    level = store_fields.check(r)[0] if "stem" in r else "PASS"
    return LEVEL_CLASS[level]


def badge(r):
    if r.get("error"):
        return f'<span class="b bad">{esc(r["error"])}</span>'
    if r["count"] is None:
        return '<span class="b warn">missing</span>' if r["required"] else '<span class="b opt">optional</span>'
    cls = field_level(r)
    if r["limit"] is None:
        return f'<span class="b {cls}">{"set" if cls == "ok" else "check"}</span>'
    unit = " bytes" if r["unit"] == "bytes" else ""
    return f'<span class="b {cls}">{r["count"]}/{r["limit"]}{unit}</span>'


def meter(r):
    if r.get("error") or r["count"] is None or not r["limit"]:
        return ""
    pct = max(0, min(100, round(100 * r["count"] / r["limit"])))
    return f'<span class="meter {field_level(r)}" aria-hidden="true"><i style="width:{pct}%"></i></span>'


def render_field(r):
    head = (f'<div class="fh"><span class="lbl">{esc(r["label"])}</span>'
            f'<span class="fx">{meter(r)}{badge(r)}</span></div>')
    if r["value"] is None:
        return f'<div class="row">{head}<div class="field"><span class="missing">— not set —</span></div></div>'
    value = r["value"]
    long_cls = " long" if len(value) > 280 or value.count("\n") > 4 else ""
    more = '<button class="more" type="button" onclick="more(this)">Show all</button>' if long_cls else ""
    return (f'<div class="row">{head}<div class="field{long_cls}"><span class="v">{esc(value)}</span>'
            f'<button class="copy" type="button" onclick="cp(this)" data-v="{esc(value)}" '
            f'aria-label="Copy {esc(r["label"])}">Copy</button></div>{more}</div>')


def url(rel):
    esc(rel)  # secret check on the raw path
    return html.escape(quote(rel))


def thumb(rel, alt, caption):
    return (f'<a class="shot" href="{url(rel)}" target="_blank" onclick="return zoom(this)">'
            f'<img src="{url(rel)}" alt="{esc(alt)}" loading="lazy"><span>{esc(caption)}</span></a>')


def shot_alt(rel, group):
    return descriptions.get(rel, f"{group} screenshot — {os.path.basename(rel)}")


def graphic_alt(rel, label):
    return descriptions.get(rel, label)


def render_shots(shots):
    if not shots:
        return '<p class="muted">No screenshots.</p>'
    out = []
    for cls, files in shots.items():
        out.append(f'<div class="dc">{esc(cls)} <span class="muted">({len(files)})</span></div><div class="gal">')
        for rel in files:
            out.append(thumb(rel, shot_alt(rel, cls), os.path.basename(rel)))
        out.append('</div>')
    return "".join(out)


def render_deferred(deferred):
    if not deferred:
        return ""
    return '<div class="dc">Deferred screenshot targets</div>' + ''.join(
        f'<p class="muted"><strong>{esc(display)} — deferred</strong>: {esc(reason)}</p>'
        for display, reason in deferred)


def render_status_bars(locale):
    strips = []
    for raw in apple_plan.get(locale, {}).get("rawCaptures", []):
        if os.path.isfile(os.path.join(root, raw)):
            label = raw.removeprefix(".listing-kit/raw/")
            strips.append(f'<figure><figcaption>{esc(label)}</figcaption><div class="strip">'
                          f'<img src="{esc(quote(raw))}" alt="{esc(label)} status bar" loading="lazy"></div></figure>')
    if not strips:
        return ""
    return '<details class="bars"><summary>Inspect raw status bars</summary>' + "".join(strips) + '</details>'


def render_graphics(graphics):
    if not graphics:
        return ""
    out = ['<div class="dc">Graphics</div><div class="gal gfx">']
    for lbl, rel, wh in graphics:
        sz = f"{wh[0]}×{wh[1]}" if wh else ""
        out.append(thumb(rel, graphic_alt(rel, lbl), f"{lbl} {sz}".strip()))
    out.append('</div>')
    return "".join(out)


def field_value(fields, *stems):
    for r in fields:
        if r.get("stem") in stems and r["value"]:
            return r["value"].strip()
    return ""


def locale_icon(L):
    for lbl, rel, _ in L["graphics"]:
        if "icon" in lbl.lower():
            return rel, lbl
    return None


def icon_html(name, icon="app"):
    if icon == "app":
        icon = (app_icon, app_icon_label) if app_icon else None
    if icon:
        return f'<img class="ic" src="{url(icon[0])}" alt="{esc(graphic_alt(*icon))}">'
    return f'<span class="ic ph" aria-hidden="true">{esc((name or "?")[:1].upper())}</span>'


def preview_card(plat, L):
    """A store-style card: what a shopper sees first, from this locale's files."""
    if plat == "iOS":
        name = field_value(L["fields"], "name") or app_name
        sub = field_value(L["fields"], "subtitle")
        store_label, action = "App Store", "Get"
        card_icon = "app"  # Apple's icon ships in the binary; show the app's Play icon as the stand-in.
    else:
        name = field_value(L["fields"], "title") or app_name
        sub = field_value(L["fields"], "short_description")
        store_label, action = "Google Play", "Install"
        card_icon = locale_icon(L)  # this locale's own icon, or the placeholder
    feature = ""
    if plat == "Android":
        for lbl, rel, _ in L["graphics"]:
            if "feature" in lbl.lower():
                feature = f'<img class="feature" src="{url(rel)}" alt="{esc(graphic_alt(rel, lbl))}" loading="lazy">'
                break
    # Lead with the screenshots a phone shopper sees first.
    groups = list(L["shots"].items())
    prefer = ("iphone", "phone")
    first = next((g for key in prefer for g in groups if key in g[0].lower() and "outer" not in g[0].lower()),
                 groups[0] if groups else None)
    strip = ""
    if first:
        group, files = first
        strip = ('<div class="pstrip">' + "".join(
            f'<img src="{url(rel)}" alt="{esc(shot_alt(rel, group))}" loading="lazy">'
            for rel in files) + '</div>'
            f'<div class="pnote">{esc(group)} · {len(files)} screenshot{"s" if len(files) != 1 else ""}</div>')
    return (f'<div class="pcard {"ios" if plat == "iOS" else "play"}">'
            f'<div class="pstore"><span class="dot"></span>{store_label} preview</div>{feature}'
            f'<div class="phead">{icon_html(name, card_icon)}<div class="pt"><div class="pname">{esc(name)}</div>'
            f'<div class="psub">{esc(sub)}</div></div><span class="get">{action}</span></div>{strip}</div>')


app_icon, app_icon_label = "", ""
if "Android" in platforms:
    for L in platforms["Android"]["locales"]:
        for lbl, rel, _ in L["graphics"]:
            if "icon" in lbl.lower():
                app_icon, app_icon_label = rel, lbl
                break
        if app_icon:
            break

for plat, stem in (("iOS", "name"), ("Android", "title")):
    for L in platforms.get(plat, {}).get("locales", []):
        app_name = app_name or field_value(L["fields"], stem)

STORE_NAMES = {"iOS": "App Store", "Android": "Google Play"}
tabs, panels = [], []
for i, (plat, data) in enumerate(platforms.items()):
    on = " on" if i == 0 else ""
    tabs.append(f'<button class="tab{on}" type="button" data-p="{esc(plat)}" onclick="show(\'{esc(plat)}\')">'
                f'{esc(STORE_NAMES.get(plat, plat))}<span class="n">{len(data["locales"])}</span></button>')
    body = []
    if len(data["locales"]) > 1:
        body.append('<nav class="locs">' + "".join(
            f'<a href="#{esc(plat)}-{esc(L["locale"])}">{esc(L["locale"])}</a>' for L in data["locales"]) + '</nav>')
    for L in data["locales"]:
        left = "".join(render_field(r) for r in L["fields"]) + "".join(render_field(r) for r in data["applevel"])
        right = render_shots(L["shots"]) + render_deferred(L.get("deferred", {})) + render_graphics(L["graphics"])
        if plat == "iOS":
            right += render_status_bars(L["locale"])
        body.append(f'<article class="loc" id="{esc(plat)}-{esc(L["locale"])}">'
                    f'<div class="loclabel">locale: {esc(L["locale"])}</div>'
                    f'{preview_card(plat, L)}'
                    f'<div class="cols"><div class="left"><h3>Store copy</h3>{left}</div>'
                    f'<div class="right"><h3>Screenshots &amp; graphics</h3>{right}</div></div></article>')
    if not body and data["applevel"]:
        left = "".join(render_field(r) for r in data["applevel"])
        body.append('<article class="loc"><div class="loclabel">app-level metadata</div>'
                    f'<div class="cols"><div class="left">{left}</div>'
                    '<div class="right"><p class="muted">No locale folders.</p></div></div></article>')
    panels.append(f'<section class="panel{on}" id="p-{plat}">{"".join(body)}</section>')
if not panels:
    panels.append('<section class="panel on" id="p-empty">'
                  '<p class="muted">Nothing to validate — no App Store or Google Play listing was found.</p>'
                  '</section>')

# ---- validation summary, from the validator's own transcript ----
crashed = bool(sys.argv[5])
transcript_only = read(val_txt) or ""
# The totals are the line just before the final verdict; listing text elsewhere cannot override them.
tail_lines = [l.strip() for l in transcript_only.splitlines() if l.strip()]
counts = None if crashed or len(tail_lines) < 2 else re.fullmatch(
    r"── (\d+) passed · (\d+) warnings · (\d+) failures ──", tail_lines[-2])
passed, warned, failed = (int(n) for n in counts.groups()) if counts else (None, None, None)
issues = []
for line in ([] if crashed else transcript_only.splitlines()):
    stripped = line.strip()
    if stripped.startswith("✗ "):
        issues.append(("bad", stripped[2:]))
    elif stripped.startswith("! "):
        issues.append(("warn", stripped[2:]))
last_line = next((l.strip() for l in reversed(transcript_only.splitlines()) if l.strip()), "")
if crashed:
    verdict_cls, verdict_txt = "bad", "Validator crashed"
elif last_line == "LISTING HAS FAILURES":
    verdict_cls, verdict_txt = "bad", "Listing has failures"
elif last_line == "LISTING VALID" and counts is None:
    verdict_cls, verdict_txt = "warn", "Valid (counts unavailable)"
elif last_line == "LISTING VALID":
    has_warn = warned or any(c == "warn" for c, _ in issues)
    verdict_cls, verdict_txt = ("warn", "Valid, with warnings") if has_warn else ("ok", "Listing valid")
else:
    verdict_cls, verdict_txt = "warn", "Not validated"
rules_date = re.search(r"store rules verified on (\d{4}-\d{2}-\d{2})", val_output)


def stat(n, label, cls):
    return f'<div class="stat {cls}"><b>{"–" if n is None else n}</b><span>{label}</span></div>'


issue_html = ""
if issues:
    issue_html = ('<div class="issues"><h2>Needs attention</h2><ul>' + "".join(
        f'<li class="{cls}"><span class="mk">{"✗" if cls == "bad" else "!"}</span>{esc(text)}</li>'
        for cls, text in issues) + '</ul></div>')
summary = (f'<section class="summary"><div class="sumhead">{icon_html(app_name)}<div>'
           f'<div class="eyebrow">Listing review</div><h1>{esc(app_name) or "Untitled app"}</h1>'
           f'<div class="meta">Generated {esc(generated_at)}'
           + (f' · store rules verified {esc(rules_date.group(1))}' if rules_date else "")
           + '</div></div></div>'
           f'<div class="stats">{stat(passed, "passed", "ok")}{stat(warned, "warnings", "warn")}'
           f'{stat(failed, "failures", "bad")}</div>{issue_html}</section>')
transcript = (f'<details class="val"{" open" if crashed or not counts else ""}>'
              f'<summary>Validator output <span class="muted">verbatim</span></summary>'
              f'<pre>{esc(val_output)}</pre></details>')

LOGO = ('<svg class="mark" viewBox="0 0 32 32" width="26" height="26" aria-hidden="true">'
        '<rect x="11" y="6" width="10" height="20" rx="2.2" fill="var(--bg-elevated)" stroke="var(--ink)" stroke-width="2"/>'
        '<path d="M3 9V3h6M29 23v6h-6" fill="none" stroke="var(--proof)" stroke-width="2.4" stroke-linecap="square"/></svg>')

CSS = """
:root{--bg:#f6f4ee;--bg-elevated:#fbfaf7;--stage:#ebe7de;--ink:#111214;--ink-soft:#4c5059;--ink-faint:#7b8290;
--rule:#ddd8cc;--rule-strong:#c5bfb1;--proof:#ce0f63;--proof-ink:#a8084f;--ok:#15803d;--warn:#a15c00;--bad:#c2261d;
--code-bg:#131519;--code-ink:#eef0f4;--shadow:0 1px 2px #1112140f,0 8px 24px #11121414;color-scheme:light}
:root[data-theme=dark]{--bg:#0b0c0e;--bg-elevated:#131519;--stage:#101216;--ink:#f3f4f6;--ink-soft:#a1a7b3;--ink-faint:#7b8290;
--rule:#232730;--rule-strong:#343946;--proof:#f43f85;--proof-ink:#ff6ba3;--ok:#34d399;--warn:#fbbf24;--bad:#f87171;
--code-bg:#08090b;--shadow:0 1px 2px #00000073,0 8px 24px #00000059;color-scheme:dark}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0b0c0e;--bg-elevated:#131519;--stage:#101216;
--ink:#f3f4f6;--ink-soft:#a1a7b3;--ink-faint:#7b8290;--rule:#232730;--rule-strong:#343946;--proof:#f43f85;--proof-ink:#ff6ba3;
--ok:#34d399;--warn:#fbbf24;--bad:#f87171;--code-bg:#08090b;--shadow:0 1px 2px #00000073,0 8px 24px #00000059;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 "Geist","Inter",ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
.mono,pre,.b,.eyebrow,.loclabel,.meta,.tab .n,.pstore,.pnote,.gal span,.locs a{font-family:"IBM Plex Mono",ui-monospace,"SFMono-Regular",Menlo,monospace}
.wrap{max-width:1240px;margin:0 auto;padding:0 clamp(16px,4vw,40px)}
header.top{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 86%,transparent);
backdrop-filter:saturate(1.4) blur(10px);-webkit-backdrop-filter:saturate(1.4) blur(10px);border-bottom:1px solid var(--rule)}
.bar{display:flex;align-items:center;gap:14px;height:60px}
.brand{display:flex;align-items:center;gap:9px;font-weight:600;letter-spacing:-.01em;font-size:16px}
.brand .sep{color:var(--ink-faint);font-weight:400}.brand .what{color:var(--ink-soft);font-weight:400}
.tabs{display:flex;gap:4px;margin-left:18px}
.tab{display:flex;align-items:center;gap:8px;padding:7px 13px;border:1px solid transparent;background:none;color:var(--ink-soft);
border-radius:999px;cursor:pointer;font:inherit;font-size:14px}
.tab:hover{color:var(--ink);background:var(--bg-elevated)}
.tab.on{color:var(--ink);background:var(--bg-elevated);border-color:var(--rule-strong)}
.tab .n{font-size:11px;color:var(--ink-faint)}
.grow{flex:1}
.pill{display:inline-flex;align-items:center;gap:7px;padding:5px 11px;border-radius:999px;font:12px/1 "IBM Plex Mono",ui-monospace,Menlo,monospace;
border:1px solid color-mix(in srgb,currentColor 30%,transparent);background:color-mix(in srgb,currentColor 10%,transparent)}
.pill::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.opt{color:var(--ink-faint)}
.theme{width:34px;height:34px;border-radius:50%;border:1px solid var(--rule-strong);background:var(--bg-elevated);color:var(--ink);cursor:pointer;font-size:15px}
.summary{margin:36px 0 28px;display:grid;grid-template-columns:1fr auto;gap:24px 40px;align-items:end}
.sumhead{display:flex;gap:18px;align-items:center}
.ic{width:72px;height:72px;border-radius:18px;flex:none;box-shadow:var(--shadow);background:var(--stage);object-fit:cover}
.ic.ph{display:grid;place-items:center;font-size:30px;font-weight:600;color:var(--proof)}
.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--proof-ink)}
h1{margin:2px 0 4px;font-size:clamp(28px,4vw,44px);line-height:1.05;letter-spacing:-.025em;font-weight:650}
.meta{font-size:12px;color:var(--ink-faint)}
.stats{display:flex;gap:10px}
.stat{min-width:96px;padding:12px 16px;border:1px solid var(--rule);border-radius:12px;background:var(--bg-elevated)}
.stat b{display:block;font-size:26px;line-height:1.1;font-weight:650;letter-spacing:-.02em}
.stat span{font-size:12px;color:var(--ink-soft)}
.issues{grid-column:1/-1;border:1px solid var(--rule);border-left:3px solid var(--warn);border-radius:12px;background:var(--bg-elevated);padding:14px 18px}
.issues h2{margin:0 0 8px;font-size:14px}
.issues ul{margin:0;padding:0;list-style:none;display:grid;gap:6px}
.issues li{display:flex;gap:10px;color:var(--ink)}.issues .mk{font-weight:700;width:12px}
.issues li.bad .mk{color:var(--bad)}.issues li.warn .mk{color:var(--warn)}
.panel{display:none;padding-bottom:40px}.panel.on{display:block}
.locs{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 18px}
.locs a{font-size:12px;padding:4px 10px;border:1px solid var(--rule);border-radius:999px;color:var(--ink-soft);text-decoration:none}
.locs a:hover{border-color:var(--proof);color:var(--proof-ink)}
.loc{border:1px solid var(--rule);border-radius:18px;background:var(--bg-elevated);padding:22px;margin-bottom:24px;box-shadow:var(--shadow);scroll-margin-top:76px}
.loclabel{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-faint);margin:0 0 14px}
.pcard{border-radius:14px;background:var(--stage);padding:18px;margin-bottom:22px;overflow:hidden;position:relative}
.pcard::before,.pcard::after{content:"";position:absolute;width:14px;height:14px;border:2px solid var(--proof)}
.pcard::before{top:8px;left:8px;border-right:0;border-bottom:0}.pcard::after{right:8px;bottom:8px;border-left:0;border-top:0}
.pstore{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-soft);display:flex;align-items:center;gap:7px;margin:0 0 12px 12px}
.pstore .dot{width:6px;height:6px;border-radius:50%;background:var(--proof)}
.feature{display:block;width:100%;max-width:520px;border-radius:10px;margin:0 0 14px}
.phead{display:flex;align-items:center;gap:14px}
.phead .ic{width:64px;height:64px;border-radius:15px}
.pcard.play .phead .ic{border-radius:14px}
.pt{flex:1;min-width:0}.pname{font-size:19px;font-weight:650;letter-spacing:-.01em}.psub{color:var(--ink-soft);font-size:14px}
.get{flex:none;padding:6px 18px;border-radius:999px;font-weight:650;font-size:14px;background:#0a84ff;color:#fff}
.pcard.play .get{background:#01875f;border-radius:8px}
.pstrip{display:flex;gap:10px;overflow-x:auto;margin-top:16px;padding-bottom:6px;scroll-snap-type:x mandatory}
.pstrip img{height:340px;width:auto;border-radius:12px;flex:none;scroll-snap-align:start;box-shadow:var(--shadow)}
.pnote{font-size:11px;color:var(--ink-faint);margin-top:6px}
.cols{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:28px;align-items:start}
h3{margin:0 0 8px;font-size:13px;font-weight:600;color:var(--ink-soft)}
.row{padding:12px 0;border-top:1px solid var(--rule)}
.fh{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.lbl{flex:1;font-weight:550;font-size:14px}
.fx{display:flex;align-items:center;gap:8px}
.meter{width:64px;height:4px;border-radius:4px;background:var(--rule);overflow:hidden}
.meter i{display:block;height:100%;background:currentColor;border-radius:4px}
.b{font-size:11.5px;padding:2px 8px;border-radius:999px;background:color-mix(in srgb,currentColor 12%,transparent)}
.b.ok{color:var(--ok)}.b.bad{color:var(--bad)}.b.warn{color:var(--warn)}.b.opt{color:var(--ink-faint)}
.field{position:relative;background:var(--bg);border:1px solid var(--rule);border-radius:10px;padding:10px 64px 10px 12px}
.field.long{max-height:9.5em;overflow:hidden}
.field.long::after{content:"";position:absolute;left:0;right:0;bottom:0;height:3em;background:linear-gradient(transparent,var(--bg));pointer-events:none}
.field.long.open{max-height:none}.field.long.open::after{display:none}
.v{white-space:pre-wrap;word-break:break-word;font-size:14px}
.missing{color:var(--bad);font-style:italic}
.copy{position:absolute;top:7px;right:7px;border:1px solid var(--rule-strong);background:var(--bg-elevated);color:var(--ink-soft);
border-radius:7px;padding:3px 9px;cursor:pointer;font:inherit;font-size:12px}
.copy:hover{color:var(--proof-ink);border-color:var(--proof)}
.more{margin-top:6px;border:0;background:none;color:var(--proof-ink);cursor:pointer;font:inherit;font-size:13px;padding:0}
.dc{margin:16px 0 8px;font-weight:600;font-size:14px}.dc:first-of-type{margin-top:0}
.muted{color:var(--ink-faint);font-weight:400}
.gal{display:flex;flex-wrap:wrap;gap:10px}
.shot{text-decoration:none;color:var(--ink-faint);font-size:11px;width:118px}
.shot img{display:block;width:118px;height:auto;max-height:240px;object-fit:contain;border:1px solid var(--rule);border-radius:8px;background:var(--stage);transition:transform .15s,border-color .15s}
.shot:hover img{transform:translateY(-2px);border-color:var(--proof)}
.gfx .shot{width:220px}.gfx .shot img{width:220px}
.shot span{display:block;margin-top:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bars{margin-top:16px}.bars summary{cursor:pointer;font-weight:600}
.bars figure{margin:12px 0}.bars figcaption{overflow-wrap:anywhere}
.strip{height:128px;overflow-x:auto;overflow-y:hidden;border:1px solid var(--rule)}.strip img{display:block}
.val{margin:8px 0 56px;border:1px solid var(--rule);border-radius:14px;background:var(--code-bg);color:var(--code-ink);overflow:hidden}
.val summary{cursor:pointer;padding:12px 16px;font-weight:600;color:#eef0f4}
.val pre{margin:0;padding:4px 16px 16px;font-size:12px;line-height:1.55;white-space:pre-wrap;overflow:auto;max-height:70vh}
footer{color:var(--ink-faint);font-size:12px;padding:0 0 40px}
footer a{color:var(--ink-soft)}
dialog{border:0;padding:0;background:transparent;max-width:96vw;max-height:94vh}
dialog::backdrop{background:#0b0c0ee6}
dialog img{display:block;max-width:96vw;max-height:88vh;border-radius:12px}
dialog p{color:#eef0f4;text-align:center;font:12px "IBM Plex Mono",ui-monospace,Menlo,monospace;margin:10px 0 0}
@media(max-width:860px){.cols{grid-template-columns:1fr}.summary{grid-template-columns:1fr}.brand .what{display:none}.tabs{margin-left:0}.pstrip img{height:260px}}
"""

JS = """
(function(){try{var t=localStorage.getItem('lk-theme');if(t)document.documentElement.dataset.theme=t;}catch(e){}})();
function theme(){var d=document.documentElement,dark=d.dataset.theme?d.dataset.theme=='dark':matchMedia('(prefers-color-scheme: dark)').matches;
d.dataset.theme=dark?'light':'dark';try{localStorage.setItem('lk-theme',d.dataset.theme)}catch(e){}}
function show(p){document.querySelectorAll('.panel').forEach(function(e){e.classList.toggle('on',e.id=='p-'+p)});
document.querySelectorAll('.tab').forEach(function(e){e.classList.toggle('on',e.dataset.p==p)});}
function flash(b){var o=b.textContent;b.textContent='Copied';setTimeout(function(){b.textContent=o},1000);}
function fb(t,b){var a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();
try{document.execCommand('copy')}catch(e){}a.remove();flash(b);}
function cp(b){var t=b.dataset.v;if(navigator.clipboard){navigator.clipboard.writeText(t).then(function(){flash(b)}).catch(function(){fb(t,b)});}else{fb(t,b);}}
function more(b){var f=b.previousElementSibling;f.classList.toggle('open');b.textContent=f.classList.contains('open')?'Show less':'Show all';}
var shots=[],cur=0;
function zoom(a){var d=document.getElementById('lb');if(!d||!d.showModal)return true;
shots=Array.prototype.slice.call(a.parentNode.querySelectorAll('a.shot'));cur=shots.indexOf(a);paint();d.showModal();return false;}
function paint(){var a=shots[cur],d=document.getElementById('lb'),i=d.querySelector('img');
if(!i){i=document.createElement('img');d.insertBefore(i,d.firstChild);}i.src=a.getAttribute('href');i.alt=a.querySelector('img').alt;d.querySelector('p').textContent=a.querySelector('span').textContent+'  ·  '+(cur+1)+' / '+shots.length;}
document.addEventListener('keydown',function(e){var d=document.getElementById('lb');if(!d||!d.open)return;
if(e.key=='ArrowRight'){cur=(cur+1)%shots.length;paint();}if(e.key=='ArrowLeft'){cur=(cur+shots.length-1)%shots.length;paint();}});
document.addEventListener('click',function(e){var d=document.getElementById('lb');if(d&&d.open&&e.target==d)d.close();});
"""

page = (f'<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta name="generator" content="listing-kit">'
        f'<title>Listing review — {esc(app_name)}</title><style>{CSS}</style>'
        f'<script>{JS}</script></head><body>'
        f'<header class="top"><div class="wrap bar"><div class="brand">{LOGO}listing-kit'
        f'<span class="sep">/</span><span class="what">review</span></div>'
        f'<div class="tabs">{"".join(tabs)}</div><div class="grow"></div>'
        f'<span class="pill {verdict_cls}">{esc(verdict_txt)}</span>'
        f'<button class="theme" type="button" onclick="theme()" aria-label="Toggle dark mode">◐</button></div></header>'
        f'<main class="wrap">{summary}{"".join(panels)}{transcript}</main>'
        f'<footer class="wrap">Generated by listing-kit from fastlane metadata .txt files and images in this folder. '
        f'Run <code>listing-kit review</code> again after editing copy or screenshots.</footer>'
        f'<dialog id="lb" aria-label="Screenshot"><p></p></dialog>'
        f'</body></html>\n')

from review_inputs import write_review_page
try:
    write_review_page(out_path, page.encode("utf-8"))
except (OSError, ValueError) as exc:
    sys.exit(str(exc))
PY
[ -z "$crash" ]
