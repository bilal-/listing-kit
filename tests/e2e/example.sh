#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
set -e

it "Expo captures compose, validate, review and hand off"
browser="$(PYTHONPATH="$SCRIPTS/compose" python3 -c 'import cdp; print(cdp.find_browser() or "")')"
if [ -z "$browser" ]; then
  skip "no browser"
  if [ "${LK_REQUIRE_RENDER:-0}" = 1 ]; then fail "LK_REQUIRE_RENDER=1 requires a browser"; fi
  summary
  exit
fi

source "$SCRIPTS/lib/imagemagick.sh"
if ! im_resolve; then
  skip "no ImageMagick"
  if [ "${LK_REQUIRE_RENDER:-0}" = 1 ]; then fail "LK_REQUIRE_RENDER=1 requires ImageMagick"; fi
  summary
  exit
fi

new_tempdir app
cd "$app"
git init -q
lk="$SKILL_DIR/bin/listing-kit"

PYTHONPATH="$SCRIPTS/lib" python3 - "$ROOT" <<'PY'
import json
from pathlib import Path
import shutil
import sys

from regular_files import open_regular

root = Path(sys.argv[1])
example = Path("examples/expo-recipe-box")
locale = "en-US"
metadata = Path("fastlane/metadata")
apple = Path("fastlane/screenshots") / locale
android = metadata / "android" / locale
play = android / "images/phoneScreenshots"


def copy_input(source, dest=None):
    dest = dest or source
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open_regular(root, example / source) as infile, dest.open("xb") as outfile:
        shutil.copyfileobj(infile, outfile)


copy_input(Path("app.json"))
for name in ("copyright", "primary_category"):
    copy_input(metadata / (name + ".txt"))
for name in ("description", "keywords", "marketing_url", "name", "privacy_url",
             "promotional_text", "release_notes", "subtitle", "support_url"):
    copy_input(metadata / locale / (name + ".txt"))
for name in ("title", "short_description", "full_description"):
    copy_input(android / (name + ".txt"))
for name in ("icon.png", "featureGraphic.png"):
    copy_input(android / "images" / name)

screens = []
for index, screen in enumerate(("recipes", "recipe-detail", "shopping", "settings"), 1):
    name = f"{index:02d}_{screen}.png"
    for target, source in (("iphone", apple / name), ("ipad", apple / ("ipad13_" + name)), ("phone", play / name)):
        raw = Path(".listing-kit/raw") / target / locale / (screen + ".png")
        copy_input(source, raw)
    flow = Path(".listing-kit/flows") / (screen + ".yaml")
    copy_input(flow)
    screens.append({"id": screen, "flow": str(flow),
                    "caption": {locale: screen.replace("-", " ").title()}})

# Historical iPhone captures use the large display. Frame them on the medium canvas.
plan = {
    "format": 2, "app": "sh.bilal.recipebox", "locales": [locale], "style": {"mode": "raw"},
    "targets": [
        {"id": "iphone", "store": "apple", "slot": "iphone-di-medium", "size": [1206, 2622], "state": "active",
         "style": {"mode": "framed", "template": "caption-bottom",
                   "palette": {"background": ["#fff7ea"], "ink": "#221811"},
                   "fonts": {"default": {"headline": ["bundled:Inter"], "detail": ["bundled:Inter"]}}}},
        {"id": "ipad", "store": "apple", "slot": "ipad-13", "size": [2064, 2752], "suffix": "ipad", "state": "active"},
        {"id": "phone", "store": "play", "slot": "phone", "size": [1080, 1920], "state": "active"},
    ],
    "screens": screens,
}
Path(".listing-kit/listing.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
PY

"$lk" doctor
"$lk" plan check
"$lk" compose
"$lk" validate
"$lk" review
"$lk" handoff .

assert_file listing-review.html
assert_file .listing-kit/outputs.json
assert_file .listing-kit/upload/INDEX.html
assert_file .listing-kit/upload/INDEX.md
apple=fastlane/screenshots/en-US
play=fastlane/metadata/android/en-US/images/phoneScreenshots
upload=.listing-kit/upload
for stem in 01_recipes 02_recipe-detail 03_shopping 04_settings; do
  name="${stem#*_}"
  order="${stem%%_*}"
  assert_file "$apple/${stem}_iphone-medium.png"
  assert_file "$apple/${stem}_ipad.png"
  assert_file "$play/$stem.png"
  cmp "$apple/${stem}_iphone-medium.png" "$upload/apple/en-US/01 iPhone Dynamic Island (medium display)/$order-${name}_iphone-medium.png"
  cmp "$apple/${stem}_ipad.png" "$upload/apple/en-US/02 iPad 13in/$order-${name}_ipad.png"
  cmp "$play/$stem.png" "$upload/play/en-US/01 Phone/$order-$name.png"
done
pass "handoff contains the composed screenshots for all three targets"
summary
