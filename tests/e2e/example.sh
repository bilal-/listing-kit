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

new_tempdir app
cp -R "$ROOT/examples/expo-recipe-box/." "$app/"
cd "$app"
git init -q
lk="$SKILL_DIR/bin/listing-kit"
"$lk" doctor

python3 - <<'PY'
import json
from pathlib import Path

locale = "en-US"
apple = Path("fastlane/screenshots") / locale
play = Path("fastlane/metadata/android") / locale / "images/phoneScreenshots"
screens = []
for index, screen in enumerate(("recipes", "recipe-detail", "shopping", "settings"), 1):
    name = f"{index:02d}_{screen}.png"
    for target, source in (("iphone", apple / name), ("ipad", apple / ("ipad13_" + name)), ("phone", play / name)):
        raw = Path(".listing-kit/raw") / target / locale / (screen + ".png")
        raw.parent.mkdir(parents=True, exist_ok=True)
        source.rename(raw)
    screens.append({"id": screen, "flow": f".listing-kit/flows/{screen}.yaml",
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
