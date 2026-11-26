#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

COMPOSE="$SCRIPTS/compose/compose.py"
PLAN="$SCRIPTS/lib/plan.py"
T="$(mktemp -d)"; [ -n "$T" ] && [ -d "$T" ] || { echo "mktemp failed" >&2; exit 1; }
trap 'rm -rf "$T"' EXIT

have_browser() { python3 -c "import sys; sys.path.insert(0, '$SCRIPTS/compose'); import cdp; sys.exit(0 if cdp.find_browser() else 1)"; }
have_magick() { command -v magick >/dev/null 2>&1 || command -v convert >/dev/null 2>&1; }

# A small app: one iPhone target and one Play phone target, two captured screens and a
# closing panel, the bundled font, no logo. Raw captures are fixture PNGs at device size.
make_app() { # dir [mode]
  mkdir -p "$1/.listing-kit"
  python3 - "$1" "${2:-framed}" <<'PY'
import json, sys
root, mode = sys.argv[1:3]
plan = {
 "format": 2, "app": "com.example.app", "locales": ["en-US"],
 "style": {"mode": mode, "template": "caption-top",
           "palette": {"background": ["#F6BC4A", "#E79B19"], "ink": "#17191D", "detail": "#493416"},
           "bezel": {"color": "#17191D", "bleed": False},
           "fonts": {"default": {"headline": ["bundled:Inter"], "detail": ["bundled:Inter"]}}},
 "targets": [
  {"id": "iphone", "store": "apple", "slot": "iphone-di-medium", "size": [1206, 2622], "state": "active"},
  {"id": "phone", "store": "play", "slot": "phone", "size": [1080, 1920], "state": "active"}],
 "screens": [
  {"id": "home", "flow": ".listing-kit/flows/home.yaml", "caption": {"en-US": "Every recipe, one list"},
   "detail": {"en-US": "Saved and sorted"}},
  {"id": "detail", "flow": ".listing-kit/flows/detail.yaml", "caption": {"en-US": "Cook step by step"},
   "detail": {"en-US": "Clear instructions"}},
  {"id": "shop", "flow": ".listing-kit/flows/shop.yaml", "caption": {"en-US": "Shop once"},
   "detail": {"en-US": "One list for the week"}}],
 "graphics": {"play": {"featureGraphic": {"headline": {"en-US": "Recipe Box"}, "detail": {"en-US": "Cook and shop"}}}},
}
json.dump(plan, open(root + "/.listing-kit/listing.json", "w"), indent=1)
PY
}
raws() { # dir w h  -> raw captures for both targets at the given capture size
  local s
  for s in home detail shop; do
    fake_png "$1/.listing-kit/raw/iphone/en-US/$s.png" "$2" "$3"
    fake_png "$1/.listing-kit/raw/phone/en-US/$s.png" "${4:-1080}" "${5:-1920}"
  done
}
size_of() { python3 "$SCRIPTS/lib/imginfo.py" "$1" | cut -f1-4 | tr '\t' ' '; }
files_in() { (cd "$1" && find fastlane store-assets -type f 2>/dev/null | LC_ALL=C sort | tr '\n' ' '); }

it "with no plan file it exits 2 and says what is missing"
mkdir -p "$T/none"
OUT="$(python3 "$COMPOSE" "$T/none" 2>&1)"; RC=$?
assert_eq 2 "$RC" "exit 2"
assert_contains "$OUT" "no .listing-kit/listing.json"

it "a missing raw capture is reported per output and nothing is written for it"
make_app "$T/missing" raw
OUT="$(python3 "$COMPOSE" "$T/missing" 2>&1)"; RC=$?
assert_eq 1 "$RC" "exit 1"
assert_contains "$OUT" "no raw capture at .listing-kit/raw/iphone/en-US/home.png"
assert_eq "" "$(files_in "$T/missing" | tr ' ' '\n' | grep Screenshots || true)" "no screenshots written"

it "preview embeds both Apple header canvases and every screenshot without writing PNGs"
make_app "$T/preview"
raws "$T/preview" 1206 2622
python3 - "$T/preview/.listing-kit/listing.json" <<'PYP'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
d = json.loads(p.read_text())
d["graphics"]["apple"] = {k: {"headline": {"en-US": "Apple <Header>"}, "detail": {"en-US": "Detail"}} for k in ("header-16x9", "header-21x9")}
p.write_text(json.dumps(d))
PYP
OUT="$(python3 "$COMPOSE" "$T/preview" --preview 2>&1)"; RC=$?
assert_eq 0 "$RC" "preview: $OUT"
assert_contains "$OUT" "$T/preview/.listing-kit/preview.html"
if python3 - "$T/preview" <<'PYP'
from html.parser import HTMLParser
from pathlib import Path
import sys
class Frames(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pages = []
    def handle_starttag(self, tag, attrs):
        if tag == "iframe":
            self.pages.append(dict(attrs)["srcdoc"])
root = Path(sys.argv[1])
frames = Frames()
frames.feed((root / ".listing-kit/preview.html").read_text())
assert len(frames.pages) == 9
assert all('href="/' not in p and 'src="/' not in p for p in frames.pages)
assert sum("Apple &lt;Header&gt;" in p and 'class="header"' in p for p in frames.pages) == 2
assert any("data:image/png;base64," in p for p in frames.pages)
assert all("data:font/ttf;base64," in p for p in frames.pages)
assert not list((root / "fastlane").rglob("*.png"))
PYP
then pass; else fail; fi

it "unknown templates and empty backgrounds are invalid before loading build inputs"
for invalid in template background; do
    make_app "$T/invalid"
    python3 - "$T/invalid/.listing-kit/listing.json" "$invalid" <<'PYP'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
d = json.loads(p.read_text())
if sys.argv[2] == "template":
    d["style"]["template"] = "../outside"
else:
    d["style"]["palette"]["background"] = []
p.write_text(json.dumps(d))
PYP
    OUT="$(python3 "$COMPOSE" "$T/invalid" 2>&1)"; RC=$?
    assert_eq 2 "$RC" "invalid $invalid rejects the plan"
    assert_contains "$OUT" "$invalid"
done
if have_magick; then

it "raw mode copies captures to the store paths, numbered in screen order, and records what it owns"
make_app "$T/raw" raw; raws "$T/raw" 1206 2622
OUT="$(python3 "$COMPOSE" "$T/raw" 2>&1)"; RC=$?
assert_eq 0 "$RC" "exit 0: $OUT"
assert_contains "$OUT" "wrote fastlane/screenshots/en-US/01_home_iphone-medium.png"
A="$T/raw/fastlane/screenshots/en-US"; P="$T/raw/fastlane/metadata/android/en-US/images/phoneScreenshots"
assert_eq 3 "$(ls "$A" | wc -l | tr -d ' ')" "three Apple screenshots"
assert_eq "01_home.png 02_detail.png 03_shop.png" "$(ls "$P" | tr '\n' ' ' | sed 's/ $//')" "Play files in order"
assert_eq "1206 2622 8 2" "$(size_of "$A"/01_home*.png)" "Apple file is the target size, RGB"
assert_contains "$(cat "$T/raw/.listing-kit/outputs.json")" '"format": 1'
assert_contains "$(cat "$T/raw/.listing-kit/outputs.json")" 'phoneScreenshots/02_detail.png'
assert_file "$T/raw/.listing-kit/compose.lock.json"

it "raw mode refuses a capture that is not the target size"
make_app "$T/rawbad" raw; raws "$T/rawbad" 1320 2868
OUT="$(python3 "$COMPOSE" "$T/rawbad" --target iphone 2>&1)"; RC=$?
assert_eq 1 "$RC" "exit 1"
assert_contains "$OUT" "raw mode needs a 1206x2622 capture"

it "a second run writes nothing"
OUT="$(python3 "$COMPOSE" "$T/raw" --target iphone --target phone 2>&1)"
assert_contains "$OUT" "0 written"

it "a file the plan no longer produces is moved to held/, and only files the kit wrote are ever moved"
echo "mine" > "$T/raw/fastlane/screenshots/en-US/99_my_own.png.txt"
python3 - "$T/raw" <<'PY'
import json, sys
p = sys.argv[1] + "/.listing-kit/listing.json"; d = json.load(open(p)); d["screens"] = d["screens"][:2]
json.dump(d, open(p, "w"), indent=1)
PY
OUT="$(python3 "$COMPOSE" "$T/raw" 2>&1)"
assert_contains "$OUT" "moved out of the upload tree"
assert_eq 2 "$(ls "$P" | wc -l | tr -d ' ')" "Play folder has two files left"
assert_file "$T/raw/.listing-kit/held/fastlane/metadata/android/en-US/images/phoneScreenshots/03_shop.png"
assert_file "$T/raw/fastlane/screenshots/en-US/99_my_own.png.txt" "the user's own file is untouched"

fi

if have_browser && have_magick; then

it "framed mode renders every output at the exact store size, as RGB without alpha"
make_app "$T/framed"; raws "$T/framed" 1206 2622 1080 2400
OUT="$(python3 "$COMPOSE" "$T/framed" 2>&1)"; RC=$?
assert_eq 0 "$RC" "exit 0: $OUT"
assert_eq "1206 2622 8 2" "$(size_of "$T/framed/fastlane/screenshots/en-US/01_home_iphone-medium.png")" "iPhone"
assert_eq "1080 1920 8 2" "$(size_of "$T/framed/fastlane/metadata/android/en-US/images/phoneScreenshots/02_detail.png")" "Play phone"
assert_eq "1024 500 8 2" "$(size_of "$T/framed/fastlane/metadata/android/en-US/images/featureGraphic.png")" "feature graphic"

it "the framed output is not the raw capture"
if cmp -s "$T/framed/.listing-kit/raw/iphone/en-US/home.png" "$T/framed/fastlane/screenshots/en-US/01_home_iphone-medium.png"; then fail "output equals raw"; else pass "composed"; fi

it "editing one caption rewrites only that screen's files"
BEFORE="$(cd "$T/framed" && shasum fastlane/screenshots/en-US/*.png fastlane/metadata/android/en-US/images/*/*.png fastlane/metadata/android/en-US/images/*.png)"
python3 - "$T/framed" <<'PY'
import json, sys
p = sys.argv[1] + "/.listing-kit/listing.json"; d = json.load(open(p)); d["screens"][1]["caption"]["en-US"] = "Cook with confidence"
json.dump(d, open(p, "w"), indent=1)
PY
OUT="$(python3 "$COMPOSE" "$T/framed" 2>&1)"
assert_contains "$OUT" "2 written, 5 unchanged"
AFTER="$(cd "$T/framed" && shasum fastlane/screenshots/en-US/*.png fastlane/metadata/android/en-US/images/*/*.png fastlane/metadata/android/en-US/images/*.png)"
assert_eq 2 "$(diff <(printf '%s\n' "$BEFORE") <(printf '%s\n' "$AFTER") | grep -c '^>')" "exactly two files changed"

it "a style change is refused without --restyle and changes nothing"
python3 - "$T/framed" <<'PY'
import json, sys
p = sys.argv[1] + "/.listing-kit/listing.json"; d = json.load(open(p)); d["style"]["palette"]["ink"] = "#101216"
json.dump(d, open(p, "w"), indent=1)
PY
OUT="$(python3 "$COMPOSE" "$T/framed" 2>&1)"; RC=$?
assert_eq 4 "$RC" "exit 4"
assert_contains "$OUT" "Rerun with --restyle"
NOW="$(cd "$T/framed" && shasum fastlane/screenshots/en-US/*.png fastlane/metadata/android/en-US/images/*/*.png fastlane/metadata/android/en-US/images/*.png)"
assert_eq "$AFTER" "$NOW" "nothing rewritten"
OUT="$(python3 "$COMPOSE" "$T/framed" --restyle 2>&1)"; RC=$?
assert_eq 0 "$RC" "--restyle proceeds"
assert_contains "$OUT" "7 written"

it "a caption that does not fit fails that image, names it, and leaves the previous file in place"
KEEP="$(shasum "$T/framed/fastlane/screenshots/en-US/01_home_iphone-medium.png")"
python3 - "$T/framed" <<'PY'
import json, sys
p = sys.argv[1] + "/.listing-kit/listing.json"; d = json.load(open(p))
d["screens"][0]["caption"]["en-US"] = "This caption is much too long to fit on the canvas at this size no matter what"
json.dump(d, open(p, "w"), indent=1)
PY
OUT="$(python3 "$COMPOSE" "$T/framed" 2>&1)"; RC=$?
assert_eq 1 "$RC" "exit 1"
assert_contains "$OUT" "01_home_iphone-medium.png: text takes"
assert_eq "$KEEP" "$(shasum "$T/framed/fastlane/screenshots/en-US/01_home_iphone-medium.png")" "previous image kept"

it "a character the fonts cannot draw fails with the character named"
python3 - "$T/framed" <<'PY'
import json, sys
p = sys.argv[1] + "/.listing-kit/listing.json"; d = json.load(open(p)); d["screens"][0]["caption"]["en-US"] = "すべてのレシピ"
json.dump(d, open(p, "w"), indent=1)
PY
OUT="$(python3 "$COMPOSE" "$T/framed" 2>&1)"; RC=$?
assert_eq 1 "$RC" "exit 1"
assert_contains "$OUT" "no headline font has"
assert_contains "$OUT" "U+3059"

it "low contrast between text and background fails with both the ratio and the need"
make_app "$T/contrast"; raws "$T/contrast" 1206 2622 1080 2400
python3 - "$T/contrast" <<'PY'
import json, sys
p = sys.argv[1] + "/.listing-kit/listing.json"; d = json.load(open(p)); d["style"]["palette"]["detail"] = "#E8A52A"
json.dump(d, open(p, "w"), indent=1)
PY
OUT="$(python3 "$COMPOSE" "$T/contrast" --target iphone --screen home 2>&1)"; RC=$?
assert_eq 1 "$RC" "exit 1"
assert_contains "$OUT" "contrast"
assert_contains "$OUT" "needs 4.5:1"

it "the browser serves nothing outside the allow-list: local files, loopback, the network and workers are refused"
OUT="$(cd "$SCRIPTS/compose" && python3 - <<'PY'
import cdp
b = cdp.Browser(); r = cdp.Renderer(b)
page = b'''<!doctype html><body><img src="file:///etc/hosts"><img src="http://127.0.0.1:9/x.png"><img src="https://example.com/a.png">
<iframe src="file:///etc/passwd"></iframe><script>new Worker("/w.js");fetch("https://example.net/f").catch(()=>0)</script></body>'''
try:
    png, info = r.render({"/index.html": page, "/w.js": b"fetch('https://worker.example/w').catch(()=>0)"}, 320, 200,
                         probe="{text: (()=>{try{return frames[0].document.body.innerText.length}catch(e){return -1}})()}", csp=False)
    import time; time.sleep(0.4)
    hosts = sorted({u.split('/')[2] for u in r.refused if '://' in u and 'listing-kit.invalid' not in u})
    print("frame-text", info["text"], "refused", " ".join(hosts), "png", len(png) > 100)
finally:
    b.close()
PY
)"
assert_contains "$OUT" "127.0.0.1:9"
assert_contains "$OUT" "example.com"
assert_contains "$OUT" "example.net"
assert_contains "$OUT" "worker.example"
assert_contains "$OUT" "png True"
case "$OUT" in "frame-text 0 "*|"frame-text -1 "*) pass "the local file frame is empty";; *) fail "local file content reached the page: $OUT";; esac

else
  it "framed-mode tests need a Chromium-family browser and ImageMagick"
  pass "skipped: not installed here"
fi

it "composer regression cases"
if python3 "$ROOT/tests/unit/compose_regressions.py"; then pass; else fail; fi
summary
