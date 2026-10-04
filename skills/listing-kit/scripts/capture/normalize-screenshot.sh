#!/usr/bin/env bash
# Normalize a raw simulator/emulator capture into a store-compliant screenshot:
# 24-bit PNG (8-bit RGB, alpha flattened onto white). Raw `simctl`/`adb` output is
# 32-bit RGBA, which both stores reject.
#
# Usage:
#   normalize-screenshot.sh <in.png> <out.png> [--play]
#
#   --play  also crop to Google Play's ≤2:1 aspect, keeping the top of the screen
#           (e.g. a 1080x2400 capture becomes 1080x2160).
#
# Exits 3 if ImageMagick is absent so the caller can tell the user to install it
# (brew install imagemagick / apt install imagemagick).
set -euo pipefail

in="${1:-}"; out="${2:-}"; mode="${3:-}"
if [ -z "$in" ] || [ -z "$out" ] || { [ -n "$mode" ] && [ "$mode" != "--play" ]; }; then
  echo "Usage: $0 <in.png> <out.png> [--play]" >&2
  exit 2
fi
[ -f "$in" ] || { echo "Input not found: $in" >&2; exit 2; }

# Resolve the ImageMagick binary (v7 'magick', v6 'convert').
if command -v magick >/dev/null 2>&1; then IM=(magick)
elif command -v convert >/dev/null 2>&1; then IM=(convert)
else
  echo "ImageMagick not found; cannot flatten screenshots to RGB (both stores reject alpha)." >&2
  echo "Install it (brew install imagemagick / apt install imagemagick) and rerun." >&2
  exit 3
fi

crop=()
if [ "$mode" = "--play" ]; then
  SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  IFS=$'\t' read -r w h _ <<<"$(python3 "$SELF_DIR/../lib/imginfo.py" "$in")"
  if [ "$h" -gt $((w * 2)) ]; then crop=(-crop "${w}x$((w * 2))+0+0" +repage)
  elif [ "$w" -gt $((h * 2)) ]; then crop=(-crop "$((h * 2))x${h}+0+0" +repage)
  fi
fi

mkdir -p "$(dirname "$out")"
"${IM[@]}" "$in" ${crop[@]+"${crop[@]}"} \
  -background white -alpha remove -alpha off \
  -depth 8 -define png:color-type=2 \
  "PNG24:$out"

echo "Wrote $out (24-bit RGB, no alpha${crop[0]:+, cropped to ≤2:1})."
