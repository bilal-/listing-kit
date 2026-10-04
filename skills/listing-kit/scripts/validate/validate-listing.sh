#!/usr/bin/env bash
# Validate a generated fastlane listing against current App Store + Google Play
# asset/metadata rules (see ../../references/stores/). Run from / pointed at the
# APP ROOT (the dir containing fastlane/). Read-only.
#
# Usage: validate-listing.sh [<app-root>]    (default: current directory)
# Exit: 0 = all checks pass (warnings allowed), 1 = one or more failures, 2 = usage.
set -uo pipefail

ROOT="${1:-.}"
[ -d "$ROOT" ] || { echo "Not a directory: $ROOT" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "Need python3 to validate the listing." >&2; exit 2; }
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SELF_DIR/../lib"

if [ -t 1 ]; then G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; B=$'\033[1m'; Z=$'\033[0m'; else G=; R=; Y=; B=; Z=; fi
FAIL=0; WARN=0; PASS=0
pass(){ PASS=$((PASS+1)); printf '  %s✓%s %s\n' "$G" "$Z" "$1"; }
fail(){ FAIL=$((FAIL+1)); printf '  %s✗%s %s\n' "$R" "$Z" "$1"; }
warn(){ WARN=$((WARN+1)); printf '  %s!%s %s\n' "$Y" "$Z" "$1"; }

# Tab-separated PNG facts for every PNG directly in a dir:
#   W H DEPTH COLORTYPE BYTES APPLE_CLASS PATH   (colortype 2=RGB, 6=RGBA, 99=not PNG)
pngs_in(){
  local f files=()
  for f in "$1"/*.png; do [ -f "$f" ] && files+=("$f"); done
  [ "${#files[@]}" -gt 0 ] && python3 "$LIB/pnginfo.py" "${files[@]}"
}

# Length of a text field, mirroring how fastlane measures: trailing whitespace /
# newlines are stripped first (a 30-char name with a trailing "\n" is 30/30).
# Counts Unicode code points, or UTF-8 bytes when $2 = bytes (Apple keywords).
measure(){ [ -f "$1" ] || { echo MISSING; return; }
  python3 -c "import sys;t=open(sys.argv[1],encoding='utf-8').read().rstrip();print(len(t.encode()) if sys.argv[2]=='bytes' else len(t))" "$1" "${2:-chars}"; }
field(){ # name file limit required(0/1) [unit: chars|bytes]
  local unit="${5:-chars}" n; n=$(measure "$2" "$unit")
  if [ "$n" = MISSING ]; then
    if [ "$4" = 1 ]; then fail "$1: REQUIRED file missing ($2)"; else warn "$1: optional, absent"; fi
    return
  fi
  [ "$n" -le "$3" ] && pass "$1: $n/$3 $unit" || fail "$1: $n/$3 $unit OVER LIMIT"
}

# Does the app support iPad (→ iPad screenshots REQUIRED on the App Store)?
# Detection is stack-aware, not Expo-only (see references/stores/apple-app-store.md):
#   Expo/RN  → ios.supportsTablet in app.json / app.config.json
#   native   → TARGETED_DEVICE_FAMILY includes 2 in any *.pbxproj (also Flutter's
#              ios/Runner.xcodeproj), or UIDeviceFamily includes 2 in an Info.plist
# Prints "True"/"False". Prunes node_modules/Pods/build so it stays fast on real repos.
supports_ipad(){ python3 - "$1" <<'PY2'
import sys,os,glob,json,re,plistlib
root=sys.argv[1]
def expo():
    for f in glob.glob(os.path.join(root,'app.json'))+glob.glob(os.path.join(root,'app.config.json')):
        try:
            if json.load(open(f)).get('expo',{}).get('ios',{}).get('supportsTablet'): return True
        except Exception: pass
    return False
def native():
    skip={'node_modules','.git','Pods','build','DerivedData','.expo','dist','.dart_tool'}
    for dp,dn,fn in os.walk(root):
        dn[:]=[d for d in dn if d not in skip]
        for name in fn:
            p=os.path.join(dp,name)
            if name.endswith('.pbxproj'):
                try:
                    for v in re.findall(r'TARGETED_DEVICE_FAMILY\s*=\s*"?([0-9,\s]+)"?',open(p,errors='ignore').read()):
                        if '2' in [x.strip() for x in v.split(',')]: return True
                except Exception: pass
            elif name=='Info.plist':
                try:
                    fam=plistlib.load(open(p,'rb')).get('UIDeviceFamily')
                    if isinstance(fam,list) and 2 in fam: return True
                except Exception: pass
    return False
print('True' if (expo() or native()) else 'False')
PY2
}

echo "${B}listing-kit — validating: $ROOT${Z}"

# Scope to the store(s) actually present, so a single-store listing (e.g. Play
# only) is not failed for the store it never targeted.
apple_locales=()
for loc in "$ROOT"/fastlane/metadata/*/; do
  [ -d "$loc" ] || continue
  case "$(basename "$loc")" in android) continue;; esac   # android tree handled below
  { [ -f "$loc/name.txt" ] || [ -f "$loc/description.txt" ]; } && apple_locales+=("$loc")
done
apple_present=0; play_present=0
{ [ "${#apple_locales[@]}" -gt 0 ] || [ -d "$ROOT/fastlane/screenshots" ]; } && apple_present=1
[ -d "$ROOT/fastlane/metadata/android" ] && play_present=1

# ---------------- App Store (deliver) ----------------
if [ "$apple_present" = 1 ]; then
  echo "${B}== Apple App Store ==${Z}"
  for loc in ${apple_locales[@]+"${apple_locales[@]}"}; do
    echo " locale $(basename "$loc"):"
    field "name" "$loc/name.txt" 30 1
    field "subtitle" "$loc/subtitle.txt" 30 0
    field "promotional_text" "$loc/promotional_text.txt" 170 0
    field "keywords" "$loc/keywords.txt" 100 0 bytes
    field "description" "$loc/description.txt" 4000 1
    [ -f "$loc/support_url.txt" ] && pass "support_url present" || warn "support_url absent (Apple requires one)"
    [ -f "$loc/privacy_url.txt" ] && pass "privacy_url present" || warn "privacy_url absent (Apple requires a privacy policy URL)"
  done
  [ -f "$ROOT/fastlane/metadata/copyright.txt" ] && pass "copyright.txt present" || warn "copyright.txt absent"

  # Screenshots: deliver assigns each PNG to a display class by its pixel size.
  # Checked per locale: ≤10 per class, a 6.9" or 6.5" iPhone set, and a 13" iPad
  # set when the app runs on iPad.
  ipad_required=$(supports_ipad "$ROOT")
  shot_dirs=0
  for sdir in "$ROOT"/fastlane/screenshots/*/; do
    [ -d "$sdir" ] || continue
    shot_dirs=$((shot_dirs+1))
    echo " screenshots $(basename "$sdir"):"
    classes=""; badfmt=0
    while IFS=$'\t' read -r w h depth ct bytes cls path; do
      base="${path##*/}"
      if [ "$cls" = "-" ]; then warn "$base: ${w}x${h} not a recognized App Store size"
      else classes="$classes$cls"$'\n'; fi
      [ "$ct" = 2 ] || { fail "$base: must be RGB no-alpha (colortype=$ct)"; badfmt=1; }
    done < <(pngs_in "$sdir")
    count_of(){ printf '%s' "$classes" | grep -c "^$1" || true; }
    while read -r n cls; do
      [ -n "$cls" ] && [ "$n" -gt 10 ] && fail "$cls: $n screenshots (App Store max is 10 per display class)"
    done < <(printf '%s' "$classes" | sort | uniq -c)
    iphone_hero=$(( $(count_of 'iPhone 6.9"') + $(count_of 'iPhone 6.5"') ))
    [ "$iphone_hero" -ge 1 ] && pass "iPhone screenshots present ($iphone_hero at 6.9\"/6.5\")" \
      || fail "no 6.9\" or 6.5\" iPhone screenshots (App Store requires one of these sets)"
    if [ "$ipad_required" = "True" ]; then
      ipad13=$(count_of 'iPad 13"')
      [ "$ipad13" -ge 1 ] && pass "iPad screenshots present ($ipad13 at 13\") — required (app runs on iPad)" \
        || fail "app supports iPad but NO iPad screenshots at 13\" (Apple requires them)"
    fi
    [ "$badfmt" = 0 ] && pass "all screenshots are RGB/no-alpha"
  done
  [ "$shot_dirs" -gt 0 ] || fail "no fastlane/screenshots/<locale>/ directory (≥1 iPhone set required)"
fi

# ---------------- Google Play (supply) ----------------
# Screenshots: JPEG or 24-bit PNG (8-bit RGB, no alpha), 320–3840 px per side,
# long side ≤ 2× short side, ≤8 per device type, ≥2 in total across types.
# Promotion eligibility (warn only): ≥4 screenshots at ≥1080 px.
play_shots(){ # dir label
  local w h depth ct bytes cls path base lo hi n=0 big=0
  while IFS=$'\t' read -r w h depth ct bytes cls path; do
    n=$((n+1)); base="${path##*/}"
    lo=$w; hi=$h; [ "$w" -gt "$h" ] && { lo=$h; hi=$w; }
    { [ "$lo" -ge 320 ] && [ "$hi" -le 3840 ]; } || fail "$base: side out of 320–3840 (${w}x${h})"
    [ "$lo" -gt 0 ] && [ $((hi * 1000)) -gt $((lo * 2000)) ] && fail "$base: aspect ${hi}/${lo} exceeds 2:1"
    { [ "$ct" = 2 ] && [ "$depth" = 8 ]; } || fail "$base: must be 24-bit no-alpha (depth=$depth colortype=$ct)"
    [ "$bytes" -le 8388608 ] || warn "$base: over 8 MB"
    [ "$lo" -ge 1080 ] && big=$((big+1))
  done < <(pngs_in "$1")
  [ "$n" -eq 0 ] && return
  [ "$n" -le 8 ] && pass "$2 screenshots: $n (≤8) ✓ format/size/aspect" || fail "$2 screenshots: $n (max 8)"
  [ "$big" -ge 4 ] || warn "$2: only $big screenshot(s) at ≥1080px; Play needs 4 for promotion eligibility"
  play_total=$((play_total+n))
}

A="$ROOT/fastlane/metadata/android"
if [ "$play_present" = 1 ]; then
  echo "${B}== Google Play ==${Z}"
  for loc in "$A"/*/; do
    [ -d "$loc" ] || continue
    echo " locale $(basename "$loc"):"
    field "title" "$loc/title.txt" 30 1
    field "short_description" "$loc/short_description.txt" 80 1
    field "full_description" "$loc/full_description.txt" 4000 1

    play_total=0
    play_shots "$loc/images/phoneScreenshots" "phone"
    play_shots "$loc/images/sevenInchScreenshots" '7" tablet'
    play_shots "$loc/images/tenInchScreenshots" '10" tablet'
    [ "$play_total" -ge 2 ] && pass "screenshots across device types: $play_total (≥2)" \
      || fail "screenshots: $play_total across device types (need ≥2)"

    # feature graphic
    fg="$loc/images/featureGraphic/featureGraphic.png"
    if [ -f "$fg" ]; then
      IFS=$'\t' read -r w h depth ct bytes cls path < <(pngs_in "$(dirname "$fg")")
      { [ "$w" = 1024 ] && [ "$h" = 500 ] && [ "$ct" = 2 ] && [ "$depth" = 8 ]; } \
        && pass "feature graphic 1024x500 24-bit no-alpha" \
        || fail "feature graphic must be 1024x500 24-bit no-alpha (got ${w}x${h} depth=$depth ct=$ct)"
    else fail "feature graphic MISSING (required to publish)"; fi

    # icon (32-bit PNG with alpha is allowed; max 1 MB)
    ic="$loc/images/icon/icon.png"
    if [ -f "$ic" ]; then
      IFS=$'\t' read -r w h depth ct bytes cls path < <(pngs_in "$(dirname "$ic")")
      { [ "$w" = 512 ] && [ "$h" = 512 ]; } && pass "icon 512x512" || fail "icon must be 512x512 (got ${w}x${h})"
      [ "$bytes" -le 1048576 ] || fail "icon is over 1 MB ($bytes bytes)"
    else warn "Play icon absent"; fi
  done
fi

# ---------------- scope notice ----------------
if [ "$apple_present" = 0 ] && [ "$play_present" = 0 ]; then
  warn "no App Store or Google Play listing content found under $ROOT/fastlane — nothing to validate"
fi

# ---------------- secrets ----------------
if [ -d "$ROOT/fastlane" ]; then
  if bash "$SELF_DIR/../lib/secret-scan.sh" "$ROOT/fastlane" >/dev/null 2>&1; then pass "secret scan: clean"; else fail "secret scan: credentials found in committed tree"; fi
fi
# Committed Maestro flows are recipes, not secrets — they must reference creds, never inline them.
if [ -d "$ROOT/.listing-kit/flows" ]; then
  if bash "$SELF_DIR/../lib/secret-scan.sh" "$ROOT/.listing-kit/flows" >/dev/null 2>&1; then pass "flow secret scan: clean"; else fail "flow secret scan: credentials inlined in a committed Maestro flow"; fi
fi

echo "${B}── ${PASS} passed · ${WARN} warnings · ${FAIL} failures ──${Z}"
[ "$FAIL" -eq 0 ] && { echo "${G}LISTING VALID${Z}"; exit 0; } || { echo "${R}LISTING HAS FAILURES${Z}"; exit 1; }
