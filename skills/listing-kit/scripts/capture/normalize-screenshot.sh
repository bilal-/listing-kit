#!/usr/bin/env bash
# Normalize a raw simulator/emulator capture into a store-compliant screenshot:
# 24-bit PNG (8-bit RGB, alpha flattened onto white). Raw `simctl`/`adb` output is
# 32-bit RGBA, which both stores reject.
#
# Usage:
#   normalize-screenshot.sh <in.png> <out.png> [--play]
#
# --play crops tall or wide phone captures to a promotional composition,
# anchored at the top or left edge. Check the generated Play tables for the
# slot’s promotion criteria. Apply this crop only to screenshots.
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
encoder=PNG24; depth=8; alpha=off
if [ "$mode" = "--play" ]; then
  info="$(python3 -I -B "$_here/../lib/imginfo.py" "$in")" || { echo "Could not read image size: $in" >&2; exit 1; }
  IFS=$'\t' read -r w h _ <<<"$info"
  [ "${w:-0}" -gt 0 ] && [ "${h:-0}" -gt 0 ] || { echo "Not a PNG/JPEG image: $in" >&2; exit 1; }
  settings="$(python3 -I -B "$_here/../lib/specs.py" play-crop "$w" "$h" "$out")"
  IFS=$'\t' read -r size encoder depth alpha <<<"$settings"
  if [ "$size" != "${w}x${h}" ]; then
    crop=(-crop "${size}+0+0" +repage)
  fi
fi
mkdir -p "$(dirname "$out")"
im_channels "$alpha"
"${IM[@]}" "$in" ${crop[@]+"${crop[@]}"} "${CHANNELS[@]}" -strip -depth "$depth" "$encoder:$out"
echo "Wrote screenshot: $out ($encoder)."
