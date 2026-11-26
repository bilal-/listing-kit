#!/usr/bin/env bash
# Validate a generated fastlane listing against current App Store + Google Play
# asset/metadata rules (see ../../references/stores/). Run from / pointed at the
# APP ROOT (the dir containing fastlane/). Read-only.
#
# Usage: validate-listing.sh [<app-root>] [--as-of YYYY-MM-DD] [--ios-sdk X.Y] [--verbose]    (default: current directory)
# Exit: 0 = all checks pass (warnings allowed), 1 = one or more failures, 2 = usage.
set -uo pipefail

ROOT=; prepared=0; review=0; options=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help) echo "Usage: listing-kit validate [-h|--help] [app-root] [--as-of YYYY-MM-DD] [--ios-sdk X.Y] [--verbose]"; exit 0 ;;
    --verbose) options+=("$1") ;;
    --prepared) prepared=1 ;;
    --review) review=1 ;;
    --as-of|--ios-sdk|--coverage-view)
      [ "$#" -ge 2 ] && [ -n "$2" ] || { echo "$1 needs a value" >&2; exit 2; }
      options+=("$1" "$2"); shift ;;
    -*) echo "Unknown option: $1" >&2; exit 2 ;;
    *) [ -z "$ROOT" ] || { echo "Expected one app root" >&2; exit 2; }; ROOT="$1" ;;
  esac
  shift
done
ROOT="${ROOT:-.}"
[ -d "$ROOT" ] || { echo "Not a directory: $ROOT" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "Need python3 to validate the listing." >&2; exit 2; }
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SELF_DIR/../lib"
if [ "$prepared" = 0 ]; then
  exec python3 -I -B "$LIB/review_inputs.py" "$SELF_DIR/validate-listing.sh" "$ROOT" ${options[@]+"${options[@]}"}
fi

if [ -t 1 ]; then G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; B=$'\033[1m'; Z=$'\033[0m'; else G=; R=; Y=; B=; Z=; fi
FAIL=0; WARN=0; PASS=0
pass(){ PASS=$((PASS+1)); printf '  %s✓%s %s\n' "$G" "$Z" "$1"; }
fail(){ FAIL=$((FAIL+1)); printf '  %s✗%s %s\n' "$R" "$Z" "$1"; }
warn(){ WARN=$((WARN+1)); printf '  %s!%s %s\n' "$Y" "$Z" "$1"; }

# Scan before evaluating copy or plans, whose diagnostics may quote their values.
if [ "${LK_REVIEW_NAME_FAILURES:-0}" -gt 0 ]; then
  fail "POTENTIAL SECRET in listing filename: [redacted path] ($LK_REVIEW_NAME_FAILURES excluded)"
fi
if [ "${LK_REVIEW_DEMO_FAILURES:-0}" -gt 0 ]; then
  fail "demo_password.txt: keep the demo password out of the repo; supply it via the environment at upload"
fi
scan_rc=0
bash "$LIB/secret-scan.sh" --prepared-listing "$ROOT" || scan_rc=$?
if [ "$scan_rc" != 0 ]; then
  echo "LISTING HAS FAILURES"
  # The review builder needs to distinguish unsafe inputs from listing-rule failures.
  if [ "$review" = 1 ]; then
    [ "$scan_rc" = 1 ] && exit 3
    exit 4
  fi
  exit 1
fi
pass "secret scan: clean"

rows="$(mktemp)" || exit 2
trap 'rm -f -- "$rows"' EXIT
echo "${B}listing-kit validating:${Z} ${LK_REVIEW_DISPLAY_ROOT:-$ROOT}"
rc=0
python3 -I -B "$LIB/validation_rows.py" "$ROOT" ${options[@]+"${options[@]}"} > "$rows" || rc=$?
[ "$rc" != 2 ] || exit 2
[ "$rc" = 0 ] || fail "could not collect listing validation rows"
im_unavailable=0
while IFS=$'\t' read -r level message; do
  case "$level" in
    PASS) pass "$message" ;;
    WARN) warn "$message" ;;
    FAIL) fail "$message" ;;
    NOTE) printf '%s\n' "$message" ;;
    IM_UNAVAILABLE) im_unavailable=1 ;;
  esac
done < "$rows"
[ "$im_unavailable" = 0 ] || warn "ImageMagick not available: images were checked structurally only"

echo "${B}── ${PASS} passed · ${WARN} warnings · ${FAIL} failures ──${Z}"
[ "$FAIL" -eq 0 ] && { echo "${G}LISTING VALID${Z}"; exit 0; } || { echo "${R}LISTING HAS FAILURES${Z}"; exit 1; }
