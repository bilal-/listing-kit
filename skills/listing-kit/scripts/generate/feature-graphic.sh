#!/usr/bin/env bash
# Generate a Google Play feature graphic: 1024x500, 24-bit PNG, NO alpha,
# app icon composited on a brand gradient.
#
# Usage:
#   feature-graphic.sh <icon-path> <output-path> [<color-a>] [<color-b>]
#
# Exits non-zero (code 3) if ImageMagick is absent, so the caller can fall back
# to prompting the user to supply a feature graphic (skill §12-D).
set -euo pipefail

icon="${1:-}"
out="${2:-}"
color_a="${3:-#4F46E5}"
color_b="${4:-#9333EA}"

if [ -z "$icon" ] || [ -z "$out" ]; then
  echo "Usage: $0 <icon-path> <output-path> [color-a] [color-b]" >&2
  exit 2
fi
if [ ! -f "$icon" ]; then
  echo "Icon not found: $icon" >&2
  exit 2
fi

# Resolve the ImageMagick binary (v7 'magick', v6 'convert').
if command -v magick >/dev/null 2>&1; then
  IM=(magick)
elif command -v convert >/dev/null 2>&1; then
  IM=(convert)
else
  echo "ImageMagick not found. Cannot auto-generate the feature graphic." >&2
  echo "FALLBACK: ask the user to supply a 1024x500 PNG/JPEG (no alpha), or install ImageMagick (brew install imagemagick)." >&2
  exit 3
fi

"${IM[@]}" -size 1024x500 "gradient:${color_a}-${color_b}" \
  \( "$icon" -resize 300x300 \) -gravity center -composite \
  -background white -alpha remove -alpha off \
  -define png:color-type=2 \
  "$out"

echo "Wrote feature graphic: $out (1024x500, no alpha)."
