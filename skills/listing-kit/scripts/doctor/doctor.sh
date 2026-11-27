#!/usr/bin/env bash
unset CDPATH
case "${1:-}" in
  -h|--help)
    echo 'Usage: listing-kit doctor [app-root]'
    echo 'Exit 3 if Python 3.8+ or the bundled store rules fail their check. Other missing tools are reported only.'
    exit 0 ;;
esac
scripts="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$scripts/lib/imagemagick.sh"
root=${1:-.}
report() {
  local name="$1" hint="$2"
  shift 2
  if "$@" >/dev/null 2>&1; then
    printf 'OK %s\n' "$name"
  else
    printf 'MISSING %s (%s)\n' "$name" "$hint"
    return 1
  fi
}
browser() {
  local candidate
  if [ -n "${LK_BROWSER:-}" ]; then command -v "$LK_BROWSER"; return; fi
  for candidate in google-chrome google-chrome-stable chromium chromium-browser microsoft-edge brave-browser; do
    [ -n "$candidate" ] && command -v "$candidate" && return
  done
  if [ "$(uname -s)" = Darwin ]; then
    for candidate in 'Google Chrome' Chromium 'Microsoft Edge' 'Brave Browser'; do
      [ -x "/Applications/$candidate.app/Contents/MacOS/$candidate" ] && return
    done
  fi
  return 1
}
rc=0
report python3 'install Python 3.8 or later' python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))' || rc=3
if [ "$rc" = 0 ]; then
  python3 -I -B "$scripts/lib/specs.py" doctor || rc=3
fi
report ImageMagick 'install ImageMagick' im_resolve
report Chromium 'install Chrome or Chromium, or set LK_BROWSER' browser
report maestro 'install Maestro CLI' command -v maestro
if [ "$(uname -s)" = Darwin ]; then
  report 'xcrun simctl' 'install Xcode and select its developer directory' xcrun simctl help
fi
report adb 'install Android SDK Platform-Tools' command -v adb
report 'fastlane (listing-kit fastlane setup|pull|publish)' 'gem install fastlane -v 2.242.0' command -v fastlane
if [ ! -e "$root/.listing-kit/listing.json" ]; then
  echo 'MISSING .listing-kit/listing.json (create a listing plan)'
elif [ "$rc" != 0 ]; then
  echo 'UNCHECKED .listing-kit/listing.json (see tool diagnostics above)'
elif detail="$(python3 "$scripts/lib/plan.py" check "$root" 2>&1)"; then
  echo 'OK .listing-kit/listing.json'
elif [ "$detail" = $'ERROR\tformat\trequired key is missing' ]; then
  echo 'found a plan in an older, unversioned layout; see references/plan-file.md for manual port steps'
else
  printf 'INVALID .listing-kit/listing.json (%s)\n' "${detail:-run listing-kit plan check for details}"
fi
if status="$(bash "$scripts/package/install-review-hook.sh" --status "$root" 2>&1)"; then
  printf 'OK hook (%s)\n' "${status%%$'\n'*}"
else
  printf 'hook: %s (run listing-kit hook install)\n' "${status:-unknown status}"
fi
exit "$rc"
