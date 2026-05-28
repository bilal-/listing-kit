#!/usr/bin/env bash
# Visual diff between a PREVIOUS and a CURRENT set of screenshots, matched by
# filename. Produces a regression report for reruns (skill Validate step §10):
# which screens were added, removed, unchanged, or changed (and by how much).
#
# Usage:
#   visual-diff.sh <previous-dir> <current-dir>
#
# Recurses both dirs and pairs *.png by basename. For each pair:
#   - ImageMagick present  → compares pixels (`compare -metric AE`); differing
#     dimensions count as CHANGED; 0 differing pixels = unchanged.
#   - ImageMagick absent    → falls back to a byte-identical check (cmp).
#
# Informational by design: exits 0 even when screens changed (a diff is a report,
# not a compliance gate — that is validate-listing.sh's job). Exits 2 on usage.
set -uo pipefail

prev="${1:-}"; cur="${2:-}"
if [ -z "$prev" ] || [ -z "$cur" ]; then
  echo "Usage: $0 <previous-dir> <current-dir>" >&2; exit 2
fi
[ -d "$prev" ] || { echo "Not a directory: $prev" >&2; exit 2; }
[ -d "$cur" ]  || { echo "Not a directory: $cur"  >&2; exit 2; }

if [ -t 1 ]; then G=$'\033[32m'; Y=$'\033[33m'; C=$'\033[36m'; B=$'\033[1m'; Z=$'\033[0m'; else G=; Y=; C=; B=; Z=; fi

# ImageMagick gives pixel-level diffs; set LK_NO_IMAGEMAGICK=1 to force the
# byte-compare fallback (e.g. for a quick check or in a constrained environment).
if [ -n "${LK_NO_IMAGEMAGICK:-}" ]; then HAVE_IM=0
elif command -v magick >/dev/null 2>&1; then IM=(magick compare); HAVE_IM=1
elif command -v compare >/dev/null 2>&1; then IM=(compare); HAVE_IM=1
else HAVE_IM=0; fi

# basename -> relative path, for each dir
list(){ (cd "$1" && find . -type f -name '*.png' | sed 's#^\./##' | sort); }

# differing-pixel count via ImageMagick (echoes integer, or "dim" if sizes differ)
diff_pixels(){
  local a="$1" b="$2"
  local da db
  da=$(magick identify -format '%wx%h' "$a" 2>/dev/null || echo "?")
  db=$(magick identify -format '%wx%h' "$b" 2>/dev/null || echo "?")
  [ "$da" != "$db" ] && { echo "dim:$da->$db"; return; }
  # compare writes the metric to stderr; null: discards the diff image. AE prints
  # as "<count>" or "<count>(<normalized>)" depending on the build — keep the count.
  local out; out=$("${IM[@]}" -metric AE "$a" "$b" null: 2>&1 | tr -d ' \n')
  echo "${out%%(*}"
}

changed=0; unchanged=0; added=0; removed=0
echo "${B}listing-kit — visual diff${Z}"
echo "  previous: $prev"
echo "  current:  $cur"
[ "$HAVE_IM" = 0 ] && echo "  ${Y}note: ImageMagick absent — byte-compare only (install it for pixel-level diffs)${Z}"

# unified set of basenames present in either dir
all=$( { list "$prev"; list "$cur"; } | sort -u )
while IFS= read -r rel; do
  [ -z "$rel" ] && continue
  pf="$prev/$rel"; cf="$cur/$rel"
  if [ ! -f "$pf" ]; then printf '  %s+ added%s    %s\n' "$G" "$Z" "$rel"; added=$((added+1)); continue; fi
  if [ ! -f "$cf" ]; then printf '  %s- removed%s  %s\n' "$Y" "$Z" "$rel"; removed=$((removed+1)); continue; fi
  if [ "$HAVE_IM" = 1 ]; then
    px=$(diff_pixels "$pf" "$cf")
    case "$px" in
      0)     printf '  = same     %s\n' "$rel"; unchanged=$((unchanged+1));;
      dim:*) printf '  %s~ changed%s  %s (resized %s)\n' "$C" "$Z" "$rel" "${px#dim:}"; changed=$((changed+1));;
      *)     printf '  %s~ changed%s  %s (%s px differ)\n' "$C" "$Z" "$rel" "$px"; changed=$((changed+1));;
    esac
  else
    if cmp -s "$pf" "$cf"; then printf '  = same     %s\n' "$rel"; unchanged=$((unchanged+1))
    else printf '  %s~ changed%s  %s (bytes differ)\n' "$C" "$Z" "$rel"; changed=$((changed+1)); fi
  fi
done <<EOF
$all
EOF

echo "${B}── ${unchanged} unchanged · ${changed} changed · ${added} added · ${removed} removed ──${Z}"
exit 0
