#!/usr/bin/env bash
set -euo pipefail

# Pass the listing-kit skill directory, containing scripts/ and references/.
skill_root="${1:?Pass the listing-kit skill directory}"
app_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo_root="$(cd "$app_root/../.." && pwd)"
images="$app_root/fastlane/metadata/android/en-US/images"
mkdir -p "$images"
cp "$repo_root/brand/android/play-store-512.png" "$images/icon.png"
bash "$skill_root/scripts/generate/feature-graphic.sh" \
  "$repo_root/brand/android/play-store-512.png" \
  "$images/featureGraphic.png" '#674312' '#B57C25'

# Replace the skill's generic icon placeholder with a Shellbell composition.
# Fonts and outlined branding come from the repository's approved brand kit.
magick -size 1024x500 'gradient:#F6BC4A-#E79B19' \
  \( "$repo_root/brand/png/horizontal-black@2x.png" -resize 340x \) \
  -gravity northwest -geometry +112+100 -composite \
  -font "$app_root/assets/fonts/JetBrainsMonoNerdFont-Bold.ttf" \
  -pointsize 48 -fill '#151719' \
  -annotate +112+250 'Your terminal,' \
  -annotate +112+314 'from anywhere.' \
  -font "$app_root/assets/fonts/JetBrainsMonoNerdFont-Regular.ttf" \
  -pointsize 26 -fill '#493416' \
  -annotate +112+392 'Claude Code · Codex · Herdr · tmux · iTerm2' \
  -strip -alpha off -depth 8 "PNG24:$images/featureGraphic.png"

# App Store Connect creative headers are uploaded separately from screenshots.
headers="$app_root/store-assets/apple/en-US"
mkdir -p "$headers"
render_header() {
  local size="$1" logo_width="$2" logo_y="$3" title_size="$4"
  local title_y="$5" privacy_y="$6" detail_size="$7" detail_y="$8" output="$9"
  magick -size "$size" 'gradient:#F6BC4A-#E79B19' \
    \( "$repo_root/brand/png/horizontal-black@2x.png" -resize "${logo_width}x" \) \
    -gravity north -geometry "+0+$logo_y" -composite \
    -font "$app_root/assets/fonts/JetBrainsMonoNerdFont-Bold.ttf" \
    -pointsize "$title_size" -fill '#151719' \
    -annotate "+0+$title_y" 'Your terminal,' \
    -annotate "+0+$privacy_y" 'from anywhere.' \
    -font "$app_root/assets/fonts/JetBrainsMonoNerdFont-Regular.ttf" \
    -pointsize "$detail_size" -fill '#493416' \
    -annotate "+0+$detail_y" 'Agents / Terminals / End-to-end encrypted / Open source' \
    -strip -alpha off -depth 8 "PNG24:$output"
}
render_header 5244x2950 1360 580 210 1200 1490 84 1880 "$headers/header-16x9.png"
render_header 3840x1646 1000 280 150 620 825 60 1110 "$headers/header-21x9.png"
