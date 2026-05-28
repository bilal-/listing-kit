# Listing Review Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `build-review.sh` script that emits a single static `listing-review.html` at the app root — store copy with copy buttons + char counts, screenshots grouped by device class, generated graphics, and the validator's output embedded verbatim — plus a "never fabricate metadata" rule in the skill.

**Architecture:** A `bash` wrapper runs `validate-listing.sh` (ANSI-stripped) into a temp file, then an embedded `python3` heredoc scans the `fastlane/` tree and writes a self-contained HTML page (inline CSS + tiny JS, screenshots linked by relative path, two-column layout B with an iOS/Android toggle). Read-only; never writes into `fastlane/`. The validator is consumed, never modified.

**Tech Stack:** `bash`, `python3` (already used across the repo's scripts/tests), zero-dependency bash test harness in `tests/`.

**Spec:** `docs/superpowers/specs/2026-05-28-listing-review-page-design.md`

---

## File structure

- **Create** `skills/listing-kit/scripts/package/build-review.sh` — the generator (one responsibility: render the review page from the fastlane tree).
- **Create** `tests/unit/build-review.test.sh` — unit test against `examples/expo-recipe-box`.
- **Modify** `tests/structure/repo-consistency.test.sh` — add the new script to the expected-scripts loop.
- **Modify** `skills/listing-kit/SKILL.md` — Assemble step wires in the script; Scripts table row; never-fabricate rule in Configure (step 6).
- **Modify** `README.md`, `docs/GUIDE.md`, `CONTRIBUTING.md` — one mention each of `listing-review.html` / the script.

---

## Task 1: The generator script `build-review.sh`

**Files:**
- Create: `skills/listing-kit/scripts/package/build-review.sh`
- Test: `tests/unit/build-review.test.sh`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/build-review.test.sh`:

```bash
#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/package/build-review.sh"
APP="$ROOT/examples/expo-recipe-box"

it "exits 2 when there is no fastlane tree"
T="$(mktemp -d)"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 2 "$RC"
rm -rf "$T"

# Build the review page against the committed example (both stores present).
T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
it "exits 0 and writes listing-review.html at the app root"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_file "$T/listing-review.html"
PAGE="$(cat "$T/listing-review.html")"

it "renders an iOS/Android toggle, copy buttons, char counts, screenshots, and the validator output"
assert_contains "$PAGE" 'data-p="iOS"'
assert_contains "$PAGE" 'data-p="Android"'
assert_contains "$PAGE" 'onclick="cp(this)"'          # copy button
assert_contains "$PAGE" '23/30'                        # name: "Recipe Box: Cook & Shop"
assert_contains "$PAGE" 'fastlane/screenshots/en-US/'  # relative screenshot link (iOS)
assert_contains "$PAGE" 'phoneScreenshots'             # android screenshot link
assert_contains "$PAGE" 'iPhone 6.9'                   # device-class grouping (note: " is HTML-escaped)
assert_contains "$PAGE" 'Feature graphic'              # generated graphic
assert_contains "$PAGE" 'LISTING VALID'                # embedded validator banner

it "is read-only — does not create or modify anything under fastlane/"
before="$(cd "$T" && find fastlane -type f -exec cksum {} \; | sort)"   # cksum is POSIX (both CI OSes)
bash "$SUT" "$T" >/dev/null 2>&1
after="$(cd "$T" && find fastlane -type f -exec cksum {} \; | sort)"
assert_eq "$before" "$after" "fastlane tree unchanged"
rm -rf "$T"

it "shows a missing required field as 'missing' rather than inventing a value"
T="$(mktemp -d)"; cp -R "$APP/fastlane" "$T/"; cp "$APP/app.json" "$T/"
rm -f "$T/fastlane/metadata/en-US/support_url.txt"
OUT="$(bash "$SUT" "$T" 2>&1)"
assert_contains "$(cat "$T/listing-review.html")" "missing"
rm -rf "$T"

summary
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash tests/unit/build-review.test.sh`
Expected: FAIL — the script does not exist yet (assertions error / file missing).

- [ ] **Step 3: Write the generator**

Create `skills/listing-kit/scripts/package/build-review.sh` with this exact content:

```bash
#!/usr/bin/env bash
# Build listing-review.html — a single, static, read-only review page for the
# fastlane listing at the app root: store copy (copy buttons + char counts),
# screenshots grouped by device class, generated graphics, and the validator's
# output embedded verbatim. Open the file in any browser; no server needed.
#
# Usage: build-review.sh [<app-root>]    (default: current directory)
# Exit:  0 = wrote listing-review.html, 2 = usage / no fastlane / no python3.
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
  bash "$VALIDATOR" "$ROOT" 2>&1 | sed $'s/\x1b\\[[0-9;]*m//g' > "$VAL_TXT" || true
else
  echo "(validate-listing.sh not found; validation section omitted)" > "$VAL_TXT"
fi

OUT="$ROOT/listing-review.html"
python3 - "$ROOT" "$VAL_TXT" "$OUT" <<'PY'
import sys, os, glob, struct, html

root, val_txt, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
FL = os.path.join(root, "fastlane")

def read(p):
    try:
        return open(p, encoding="utf-8").read().rstrip()
    except OSError:
        return None

def dims(p):
    try:
        d = open(p, "rb").read(24)
        if d[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        return struct.unpack(">II", d[16:24])
    except OSError:
        return None

def devclass(w, h):
    lo, hi = sorted((w, h))
    t = {(1320,2868):'iPhone 6.9"',(1290,2796):'iPhone 6.9"',(1284,2778):'iPhone 6.7"',
         (1242,2688):'iPhone 6.5"',(1242,2208):'iPhone 5.5"',(2064,2752):'iPad 13"',
         (2048,2732):'iPad 12.9"',(1668,2388):'iPad 11"',(1640,2360):'iPad 11"'}
    return t.get((lo, hi), f"{w}×{h}")

def esc(s):
    return html.escape(s if s is not None else "")

def copy_row(label, path, limit=None, required=False):
    v = read(path)
    return dict(label=label, value=v, limit=limit, required=required,
                count=(len(v) if v is not None else None))

platforms = {}  # name -> {locales:[...], applevel:[...]}

# ---- iOS (deliver) ----
ios_locs = sorted(d for d in glob.glob(os.path.join(FL, "metadata", "*"))
                  if os.path.isdir(d) and os.path.basename(d) != "android")
if ios_locs or os.path.isdir(os.path.join(FL, "screenshots")):
    locs = []
    for ld in ios_locs:
        loc = os.path.basename(ld)
        fields = [
            copy_row("Name", os.path.join(ld, "name.txt"), 30, True),
            copy_row("Subtitle", os.path.join(ld, "subtitle.txt"), 30),
            copy_row("Promotional text", os.path.join(ld, "promotional_text.txt"), 170),
            copy_row("Keywords", os.path.join(ld, "keywords.txt"), 100),
            copy_row("Description", os.path.join(ld, "description.txt"), 4000, True),
            copy_row("Support URL", os.path.join(ld, "support_url.txt"), None, True),
            copy_row("Marketing URL", os.path.join(ld, "marketing_url.txt")),
            copy_row("Privacy URL", os.path.join(ld, "privacy_url.txt")),
        ]
        shots = {}
        for f in sorted(glob.glob(os.path.join(FL, "screenshots", loc, "*.png"))):
            wh = dims(f)
            cls = devclass(*wh) if wh else "?"
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
    for ld in sorted(d for d in glob.glob(os.path.join(A, "*")) if os.path.isdir(d)):
        loc = os.path.basename(ld)
        fields = [
            copy_row("Title", os.path.join(ld, "title.txt"), 30, True),
            copy_row("Short description", os.path.join(ld, "short_description.txt"), 80, True),
            copy_row("Full description", os.path.join(ld, "full_description.txt"), 4000, True),
        ]
        shots = {}
        for sub, lbl in [("phoneScreenshots", "Phone"), ("sevenInchScreenshots", '7" tablet'),
                         ("tenInchScreenshots", '10" tablet'), ("wearScreenshots", "Wear")]:
            fs = sorted(glob.glob(os.path.join(ld, "images", sub, "*.png")))
            if fs:
                shots[lbl] = [os.path.relpath(f, root) for f in fs]
        graphics = []
        for sub, lbl in [("featureGraphic", "Feature graphic"), ("icon", "Icon")]:
            for f in sorted(glob.glob(os.path.join(ld, "images", sub, "*.png"))):
                graphics.append((lbl, os.path.relpath(f, root), dims(f)))
        locs.append(dict(locale=loc, fields=fields, shots=shots, graphics=graphics))
    platforms["Android"] = dict(locales=locs, applevel=[])

val_output = read(val_txt) or ""

# ---- render helpers ----
def badge(r):
    if r["count"] is None:
        return '<span class="b warn">missing</span>' if r["required"] else '<span class="b opt">optional</span>'
    if r["limit"] is None:
        return '<span class="b ok">set</span>'
    ok = r["count"] <= r["limit"]
    return f'<span class="b {"ok" if ok else "bad"}">{r["count"]}/{r["limit"]}</span>'

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
    tabs.append(f'<button class="tab{on}" data-p="{plat}" onclick="show(\'{plat}\')">{plat}</button>')
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
        f'<div class="tabs">{"".join(tabs)}</div></header>'
        f'<div class="val"><pre>{esc(val_output)}</pre></div>'
        f'{"".join(panels)}'
        f'<script>{JS}</script></body></html>\n')

open(out_path, "w", encoding="utf-8").write(page)
print(f"Wrote {out_path}")
PY
echo "Open it in a browser: $OUT"
```

- [ ] **Step 4: Make the script executable**

Run: `chmod +x skills/listing-kit/scripts/package/build-review.sh`

- [ ] **Step 5: Run the test to verify it passes**

Run: `bash tests/unit/build-review.test.sh`
Expected: PASS — all assertions green, `##SUMMARY pass=N fail=0`.

- [ ] **Step 6: Sanity-check the rendered page by eye (optional)**

Run:
```bash
T="$(mktemp -d)"; cp -R examples/expo-recipe-box/fastlane "$T/"; cp examples/expo-recipe-box/app.json "$T/"
bash skills/listing-kit/scripts/package/build-review.sh "$T"
echo "open $T/listing-review.html"
```
Expected: a `listing-review.html` that opens with an iOS/Android toggle, copy buttons, screenshots, and the validator banner. (`open` it on macOS to eyeball layout B.)

- [ ] **Step 7: Commit**

```bash
git add skills/listing-kit/scripts/package/build-review.sh tests/unit/build-review.test.sh
git commit -m "feat(skill): build-review.sh — static listing-review.html (copy buttons, screenshots, embedded validation)"
```

---

## Task 2: Wire the script into the skill and tests

**Files:**
- Modify: `tests/structure/repo-consistency.test.sh`
- Modify: `skills/listing-kit/SKILL.md`
- Modify: `README.md`, `docs/GUIDE.md`, `CONTRIBUTING.md`

- [ ] **Step 1: Add the script to the repo-consistency expected list (failing first)**

In `tests/structure/repo-consistency.test.sh`, change the scripts loop to include `package/build-review`:

```bash
for s in capture/sanitize-status-bar capture/grant-permissions \
         generate/feature-graphic lib/secret-scan package/generate-manifests \
         validate/validate-listing validate/visual-diff package/build-review; do
```

- [ ] **Step 2: Add the SKILL.md Scripts-table + Reference-map rows and the Assemble wiring**

In `skills/listing-kit/SKILL.md`, add to the Scripts table (after the `validate/visual-diff.sh` row):

```markdown
| `scripts/package/build-review.sh` | Emit a static `listing-review.html` (copy buttons, screenshots, embedded validation) for human review |
```

In the Assemble step (step 11), after the secret-scan sentence, add:

```markdown
Finally, run `scripts/package/build-review.sh` (pass the app root) to emit `listing-review.html` at the app root — a single static page (copy buttons, screenshots per device class, the validator's results) for reviewing the listing and pasting copy into the store consoles. It is read-only and never writes into `fastlane/`.
```

- [ ] **Step 3: Add a mention in README, GUIDE, CONTRIBUTING**

In `README.md` "Your repo stays clean" or "See it in action" area, add one line:

```markdown
After a run, open `listing-review.html` at the app root to review all copy (with copy buttons), screenshots, and validation in one page.
```

In `docs/GUIDE.md` section "4. The output", add `listing-review.html` to the tree block and a sentence:

```markdown
listing-review.html        # open in a browser: copy buttons, screenshots, validation
```

In `CONTRIBUTING.md`, in the "### Tests" paragraph, append one sentence so the coverage list stays accurate:

```markdown
The newest script, `build-review.sh`, is covered by `tests/unit/build-review.test.sh`, which builds the page against the example app and asserts its key contents.
```

- [ ] **Step 4: Run the full suite**

Run: `bash tests/run.sh`
Expected: ALL PASS — repo-consistency now finds `package/build-review` executable and the SKILL.md `scripts/package/build-review.sh` reference resolves.

- [ ] **Step 5: Commit**

```bash
git add tests/structure/repo-consistency.test.sh skills/listing-kit/SKILL.md README.md docs/GUIDE.md CONTRIBUTING.md
git commit -m "docs(skill): wire build-review.sh into Assemble, scripts table, and docs"
```

---

## Task 3: "Never fabricate metadata" rule in Configure

**Files:**
- Modify: `skills/listing-kit/SKILL.md` (step 6, Configure)
- Modify: `tests/structure/repo-consistency.test.sh` (assert the rule is present)

- [ ] **Step 1: Add a presence assertion (failing first)**

In `tests/structure/repo-consistency.test.sh`, before `summary`, add:

```bash
it "SKILL.md states the never-fabricate rule for URLs/copyright/category"
SK="$(cat "$SKILL_DIR/SKILL.md")"
assert_contains "$SK" "Never fabricate"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `bash tests/structure/repo-consistency.test.sh`
Expected: FAIL — `expected substring [Never fabricate] in output`.

- [ ] **Step 3: Add the rule to SKILL.md step 6 (Configure)**

In `skills/listing-kit/SKILL.md`, in the "Configure" step, after the "Secrets never enter the committed tree" sentence, add:

```markdown
**Never fabricate metadata.** Values that can only come from the user — **support / marketing / privacy-policy URLs, copyright, category** — must never be invented. If you don't have a value, **ask**; under `--non-interactive`, **leave the field unwritten (omit the `.txt` file)** rather than writing a guessed or empty value. An omitted required field is then surfaced by Validate (and shown blank with a ⚠ marker on the review page); a fabricated URL could pass review while pointing somewhere wrong.
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `bash tests/run.sh`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/listing-kit/SKILL.md tests/structure/repo-consistency.test.sh
git commit -m "docs(skill): never fabricate URLs/copyright/category — omit unknown fields"
```

---

## Done-when

- `bash tests/run.sh` is green, including the new `unit/build-review.test.sh`.
- `build-review.sh <app-root>` writes a `listing-review.html` that opens in a browser with the iOS/Android toggle, copy buttons, char counts, device-grouped screenshots, generated graphics, and the embedded validator output — and never touches `fastlane/`.
- SKILL.md Assemble runs it; the Scripts table, Reference map, README, GUIDE, and CONTRIBUTING mention it; the Configure step states the never-fabricate rule.
