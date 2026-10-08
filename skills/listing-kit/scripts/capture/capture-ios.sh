#!/usr/bin/env bash
# Capture one explicitly selected simulator display without replacing a good
# asset with a wrong-size or blank frame. Never resize native screenshots.
# Usage: capture-ios.sh <simulator-udid> <display-id-or-name> <width>x<height> <out.png>
set -euo pipefail
device="${1:-}"; display="${2:-}"; size="${3:-}"; out="${4:-}"
if [ "$#" -ne 4 ] || [ -z "$device" ] || [ "$device" = booted ] || [ -z "$display" ] ||
   [[ ! "$size" =~ ^[1-9][0-9]*x[1-9][0-9]*$ ]] || [[ "$out" != *.png ]]; then
  echo "Usage: $0 <simulator-udid> <display-id-or-name> <width>x<height> <out.png>" >&2
  echo 'Use an explicit device and enumerate its displays with simctl io <udid> enumerate.' >&2
  exit 2
fi
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$here/../lib/imagemagick.sh"
if ! im_resolve; then
  echo 'ImageMagick is required; install it before capturing.' >&2
  exit 3
fi
mkdir -p "$(dirname "$out")"
tmp="$(mktemp -d "$(dirname "$out")/.listing-capture.XXXXXX")"
trap 'rm -r "$tmp"' EXIT
xcrun simctl io "$device" screenshot --type=png --display "$display" "$tmp/raw.png"
info="$(python3 "$here/../lib/imginfo.py" "$tmp/raw.png")"
IFS=$'\t' read -r width height rest <<< "$info"
if [ "${width}x${height}" != "$size" ]; then
  echo "Capture size ${width}x${height} does not match planned $size; existing asset preserved." >&2
  exit 1
fi
# Fully black/solid frames are common when the inactive Duo display is selected.
# Visual review is still required for nonuniform loading screens and clipping.
variation="$("${IM[@]}" "$tmp/raw.png" -alpha off -colorspace Gray -format '%[fx:standard_deviation]' info:)"
if ! python3 -c 'import math,sys; n=float(sys.argv[1]); sys.exit(0 if math.isfinite(n) and n > 0 else 1)' "$variation"; then
  echo 'Blank or solid capture; select the active display and wait for app content. Existing asset preserved.' >&2
  exit 1
fi
bash "$here/normalize-screenshot.sh" "$tmp/raw.png" "$tmp/ready.png"
mv "$tmp/ready.png" "$out"
echo "Captured $out ($size, display $display). Review the actual app content before delivery."
