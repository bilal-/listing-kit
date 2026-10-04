#!/usr/bin/env bash
# Normalize a raw simulator/emulator capture into a store-compliant screenshot:
# 24-bit PNG (8-bit RGB, alpha flattened onto white). Raw `simctl`/`adb` output is
# 32-bit RGBA, which both stores reject.
#
# Usage:
#   normalize-screenshot.sh <in.png> <out.png> [--play]
#
#   --play  also crop anything taller/wider than 16:9 to exactly 9:16 (16:9), keeping
#           the top of the screen (a 1080x2400 capture becomes 1080x1920). That is
#           within Play's 2:1 limit and meets its promotion bar (≥1080 px, 9:16/16:9). Screenshots only: never
#           use it on the 1024x500 feature graphic, which it would crop.
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

# Helpers live in ../lib; parameter expansion (not dirname) so this works on a bare PATH.
_here="${BASH_SOURCE[0]%/*}"; [ "$_here" = "${BASH_SOURCE[0]}" ] && _here=.
. "$_here/../lib/imagemagick.sh"
if ! im_resolve; then
  echo "ImageMagick not found; cannot flatten screenshots to RGB (both stores reject alpha)." >&2
  echo "Install it (brew install imagemagick / apt install imagemagick) and rerun." >&2
  exit 3
fi

crop=()
if [ "$mode" = "--play" ]; then
  info="$(python3 "$_here/../lib/imginfo.py" "$in")" || { echo "Could not read image size: $in" >&2; exit 1; }
  IFS=$'\t' read -r w h _ <<<"$info"
  [ "${w:-0}" -gt 0 ] && [ "${h:-0}" -gt 0 ] || { echo "Not a PNG/JPEG image: $in" >&2; exit 1; }
  # Taller (or wider) than 16:9 → crop to exactly 9:16 (16:9), keeping the top
  # (left) edge. That satisfies Play's 2:1 limit and its promotion bar
  # (≥1080 px, 9:16 or 16:9). Squarer images (tablets) are left alone.
  if [ $((h * 9)) -gt $((w * 16)) ]; then crop=(-crop "${w}x$((w * 16 / 9))+0+0" +repage)
  elif [ $((w * 9)) -gt $((h * 16)) ]; then crop=(-crop "$((h * 16 / 9))x${h}+0+0" +repage)
  fi
fi

mkdir -p "$(dirname "$out")"
"${IM[@]}" "$in" ${crop[@]+"${crop[@]}"} \
  -background white -alpha remove -alpha off \
  -depth 8 -define png:color-type=2 \
  "PNG24:$out"

echo "Wrote $out (24-bit RGB, no alpha${crop[0]:+, cropped to 9:16})."
