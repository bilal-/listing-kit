#!/usr/bin/env bash
# Visual diff between a PREVIOUS and a CURRENT set of screenshots, matched by
# filename. Produces a regression report for reruns (skill Validate step):
# which screens were added, removed, unchanged, or changed (and by how much).
#
# Usage:
#   visual-diff.sh <previous-dir> <current-dir>
#
# Recurses both dirs and pairs PNG/JPEG files by relative path. For each pair:
#   - ImageMagick present  → compares pixels (`compare -metric AE`); differing
#     dimensions count as CHANGED; 0 differing pixels = unchanged; decode or
#     compare failures are reported as an error for that screen.
#   - ImageMagick absent    → falls back to a byte-identical check (cmp).
#
# Informational by design: exits 0 even when screens changed or errored (a diff
# is a report, not a compliance gate — that is validate-listing.sh's job). Exits 2 on usage.
set -uo pipefail

prev="${1:-}"; cur="${2:-}"
if [ -z "$prev" ] || [ -z "$cur" ]; then
  echo "Usage: $0 <previous-dir> <current-dir>" >&2; exit 2
fi
[ -d "$prev" ] || { echo "Not a directory: $prev" >&2; exit 2; }
[ -d "$cur" ]  || { echo "Not a directory: $cur"  >&2; exit 2; }

if [ -t 1 ]; then G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; C=$'\033[36m'; B=$'\033[1m'; Z=$'\033[0m'; else G=; R=; Y=; C=; B=; Z=; fi

# ImageMagick gives pixel-level diffs; set LK_NO_IMAGEMAGICK=1 to force the
# byte-compare fallback (e.g. for a quick check or in a constrained environment).
# Helpers live in ../lib; parameter expansion (not dirname) so this works on a bare PATH.
_here="${BASH_SOURCE[0]%/*}"; [ "$_here" = "${BASH_SOURCE[0]}" ] && _here=.
. "$_here/../lib/imagemagick.sh"
if im_resolve compare; then HAVE_IM=1; else HAVE_IM=0; fi

ERR_TMP="$(mktemp)"
trap 'rm -f "$ERR_TMP"' EXIT

# relative paths of every PNG/JPEG under a dir
list(){ (cd "$1" && find . -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' \) | sed 's#^\./##' | sort); }

clean_err(){
  printf '%s' "$1" | tr '\r\n\t' '   ' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//; s/[[:space:]][[:space:]]+/ /g'
}

# differing-pixel count via ImageMagick (echoes integer, "dim:...", or "err:...")
diff_pixels(){
  local a="$1" b="$2"
  local da db rc raw trimmed reason
  local dim_re='^[1-9][0-9]*x[1-9][0-9]*$'
  local ae_re='^[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?(\([0-9.eE+-]+\))?$'
  da=$("${IM_IDENTIFY[@]}" -format '%wx%h' "$a" 2>"$ERR_TMP"); rc=$?
  if [ "$rc" -ne 0 ] || [[ ! "$da" =~ $dim_re ]]; then
    reason="$(clean_err "$(cat "$ERR_TMP")")"
    [ -n "$reason" ] || reason="identify exited $rc"
    echo "err:$reason"; return
  fi
  db=$("${IM_IDENTIFY[@]}" -format '%wx%h' "$b" 2>"$ERR_TMP"); rc=$?
  if [ "$rc" -ne 0 ] || [[ ! "$db" =~ $dim_re ]]; then
    reason="$(clean_err "$(cat "$ERR_TMP")")"
    [ -n "$reason" ] || reason="identify exited $rc"
    echo "err:$reason"; return
  fi
  [ "$da" != "$db" ] && { echo "dim:$da->$db"; return; }
  # compare writes the metric to stderr; null: discards the diff image. AE prints
  # as "<count>" or "<count>(<normalized>)" depending on the build — keep the count.
  # IM7 may print a float ("1.12957e+06"); round it to a whole pixel count.
  # Exit 0 = identical, 1 = dissimilar, >=2 = error.
  raw=$("${IM_COMPARE[@]}" -metric AE "$a" "$b" null: 2>&1); rc=$?
  trimmed=$(printf '%s' "$raw" | tr -d ' \t\r\n')
  if [ "$rc" -ge 2 ] || [[ ! "$trimmed" =~ $ae_re ]]; then
    reason="$(clean_err "$raw")"
    [ -n "$reason" ] || reason="compare exited $rc"
    echo "err:$reason"; return
  fi
  awk -v n="${trimmed%%(*}" 'BEGIN { printf "%.0f\n", n }'
}

changed=0; unchanged=0; added=0; removed=0; errors=0
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
      err:*) printf '  %s! error%s    %s (comparison failed: %s)\n' "$R" "$Z" "$rel" "${px#err:}"; errors=$((errors+1));;
      *)     printf '  %s~ changed%s  %s (%s px differ)\n' "$C" "$Z" "$rel" "$px"; changed=$((changed+1));;
    esac
  else
    if cmp -s "$pf" "$cf"; then printf '  = same     %s\n' "$rel"; unchanged=$((unchanged+1))
    else printf '  %s~ changed%s  %s (bytes differ)\n' "$C" "$Z" "$rel"; changed=$((changed+1)); fi
  fi
done <<EOF
$all
EOF

if [ "$errors" -gt 0 ]; then
  echo "${B}── ${unchanged} unchanged · ${changed} changed · ${added} added · ${removed} removed · ${errors} errors ──${Z}"
else
  echo "${B}── ${unchanged} unchanged · ${changed} changed · ${added} added · ${removed} removed ──${Z}"
fi
exit 0
