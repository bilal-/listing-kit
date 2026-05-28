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
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -t 1 ]; then G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; B=$'\033[1m'; Z=$'\033[0m'; else G=; R=; Y=; B=; Z=; fi
FAIL=0; WARN=0; PASS=0
pass(){ PASS=$((PASS+1)); printf '  %s✓%s %s\n' "$G" "$Z" "$1"; }
fail(){ FAIL=$((FAIL+1)); printf '  %s✗%s %s\n' "$R" "$Z" "$1"; }
warn(){ WARN=$((WARN+1)); printf '  %s!%s %s\n' "$Y" "$Z" "$1"; }

# PNG metadata: echoes "W H DEPTH COLORTYPE BYTES" (colortype 2=RGB,6=RGBA,...).
pnginfo(){ python3 - "$1" <<'PY'
import struct,sys,os
try:
    d=open(sys.argv[1],'rb').read(33)
    if d[:8]!=b'\x89PNG\r\n\x1a\n': print("0 0 0 99 0"); sys.exit()
    w,h=struct.unpack('>II',d[16:24]); print(w,h,d[24],d[25],os.path.getsize(sys.argv[1]))
except Exception: print("0 0 0 99 0")
PY
}
# Character count, mirroring how fastlane measures: trailing whitespace/newlines
# are stripped before counting (so a 30-char field written with a trailing "\n"
# is NOT reported as 31/30). Counts Unicode code points, not bytes.
chars(){ [ -f "$1" ] || { echo MISSING; return; }; python3 -c "import sys;print(len(open(sys.argv[1],encoding='utf-8').read().rstrip()))" "$1"; }
field(){ # name file limit required(0/1)
  local n; n=$(chars "$2")
  if [ "$n" = MISSING ]; then [ "$4" = 1 ] && fail "$1: REQUIRED file missing ($2)" || warn "$1: optional, absent"; return; fi
  [ "$n" -le "$3" ] && pass "$1: $n/$3 chars" || fail "$1: $n/$3 chars OVER LIMIT"
}

# Recognized Apple portrait sizes -> family label (landscape = swapped).
apple_size(){ case "$1x$2" in
  1320x2868|1290x2796|1284x2778|2868x1320|2796x1290|2778x1284) echo "iPhone 6.9/6.7";;
  1242x2688|2688x1242) echo "iPhone 6.5";;
  1242x2208|2208x1242) echo "iPhone 5.5";;
  2064x2752|2048x2732|2752x2064|2732x2048) echo "iPad 12.9/13";;
  1668x2388|2388x1668|1640x2360) echo "iPad 11";;
  *) echo "";; esac; }

# Does the app support iPad (→ iPad screenshots REQUIRED on the App Store)?
# Detection is stack-aware, not Expo-only (see references/stores/apple-app-store.md):
#   Expo/RN  → ios.supportsTablet in app.json / app.config.json
#   native   → TARGETED_DEVICE_FAMILY includes 2 in any *.pbxproj (also Flutter's
#              ios/Runner.xcodeproj), or UIDeviceFamily includes 2 in an Info.plist
# Prints "True"/"False". Prunes node_modules/Pods/build so it stays fast on real repos.
supports_ipad(){ python3 - "$1" <<'PY'
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
PY
}

echo "${B}listing-kit — validating: $ROOT${Z}"

# Scope to the store(s) actually present, so a single-store listing (e.g. Play
# only) is not failed for the store it never targeted.
apple_present=0; play_present=0
[ -d "$ROOT/fastlane/screenshots" ] && apple_present=1
for loc in "$ROOT"/fastlane/metadata/*/; do
  [ -d "$loc" ] || continue
  case "$(basename "$loc")" in android) continue;; esac
  { [ -f "$loc/name.txt" ] || [ -f "$loc/description.txt" ]; } && apple_present=1
done
[ -d "$ROOT/fastlane/metadata/android" ] && play_present=1

# ---------------- App Store (deliver) ----------------
if [ "$apple_present" = 1 ]; then
  echo "${B}== Apple App Store ==${Z}"
  for loc in "$ROOT"/fastlane/metadata/*/; do
    [ -d "$loc" ] || continue
    case "$(basename "$loc")" in android) continue;; esac   # android tree handled below
    echo " locale $(basename "$loc"):"
    field "name" "$loc/name.txt" 30 1
    field "subtitle" "$loc/subtitle.txt" 30 0
    field "promotional_text" "$loc/promotional_text.txt" 170 0
    field "keywords" "$loc/keywords.txt" 100 0
    field "description" "$loc/description.txt" 4000 1
    [ -f "$loc/support_url.txt" ] && pass "support_url present" || warn "support_url absent (Apple requires one)"
  done
  [ -f "$ROOT/fastlane/metadata/copyright.txt" ] && pass "copyright.txt present" || warn "copyright.txt absent"

  # screenshots
  iphone=0; ipad=0; badfmt=0
  for f in "$ROOT"/fastlane/screenshots/*/*.png; do
    [ -f "$f" ] || continue
    read -r w h depth ct bytes <<<"$(pnginfo "$f")"
    fam=$(apple_size "$w" "$h"); base="${f##*/}"
    if [ -z "$fam" ]; then warn "$base: ${w}x${h} not a recognized App Store size"; else
      case "$fam" in iPhone*) iphone=$((iphone+1));; iPad*) ipad=$((ipad+1));; esac
    fi
    [ "$ct" = 2 ] || { fail "$base: must be RGB no-alpha (colortype=$ct)"; badfmt=1; }
  done
  [ "$iphone" -ge 1 ] && pass "iPhone screenshots present ($iphone)" || fail "no recognized iPhone screenshots (≥1 required)"
  # iPad required iff app supports iPad (stack-aware detection)
  supports_ipad=$(supports_ipad "$ROOT")
  if [ "$supports_ipad" = "True" ]; then
    [ "$ipad" -ge 1 ] && pass "iPad screenshots present ($ipad) — required (supportsTablet)" || fail "app supports iPad but NO iPad screenshots (Apple requires them)"
  fi
  [ "$badfmt" = 0 ] && pass "all iOS screenshots are RGB/no-alpha"
fi

# ---------------- Google Play (supply) ----------------
A="$ROOT/fastlane/metadata/android"
if [ "$play_present" = 1 ]; then
  echo "${B}== Google Play ==${Z}"
  for loc in "$A"/*/; do
    [ -d "$loc" ] || continue
    echo " locale $(basename "$loc"):"
    field "title" "$loc/title.txt" 30 1
    field "short_description" "$loc/short_description.txt" 80 1
    field "full_description" "$loc/full_description.txt" 4000 1

    # phone screenshots
    shots=("$loc"images/phoneScreenshots/*.png); n=0
    for f in "${shots[@]}"; do [ -f "$f" ] || continue; n=$((n+1))
      read -r w hh depth ct bytes <<<"$(pnginfo "$f")"; base="${f##*/}"
      lo=$w; hi=$hh; [ "$w" -gt "$hh" ] && { lo=$hh; hi=$w; }
      [ "$lo" -ge 320 ] && [ "$hi" -le 3840 ] || fail "$base: side out of 320–3840 (${w}x${hh})"
      python3 -c "import sys;sys.exit(0 if ($hi/$lo)<=2.0001 else 1)" && : || fail "$base: aspect ${hi}/${lo} exceeds 2:1"
      [ "$ct" = 2 ] || fail "$base: must be 24-bit no-alpha (colortype=$ct)"
      [ "$bytes" -le 8388608 ] || fail "$base: over 8MB"
    done
    [ "$n" -ge 2 ] && [ "$n" -le 8 ] && pass "phone screenshots: $n (2–8) ✓ format/size/aspect" || fail "phone screenshots: $n (need 2–8)"

    # feature graphic
    fg="$loc"images/featureGraphic/featureGraphic.png
    if [ -f "$fg" ]; then read -r w hh depth ct bytes <<<"$(pnginfo "$fg")"
      { [ "$w" = 1024 ] && [ "$hh" = 500 ] && [ "$ct" = 2 ] && [ "$depth" = 8 ]; } \
        && pass "feature graphic 1024x500 24-bit no-alpha" \
        || fail "feature graphic must be 1024x500 24-bit no-alpha (got ${w}x${hh} depth=$depth ct=$ct)"
    else fail "feature graphic MISSING (required to publish)"; fi

    # icon
    ic="$loc"images/icon/icon.png
    if [ -f "$ic" ]; then read -r w hh depth ct bytes <<<"$(pnginfo "$ic")"
      { [ "$w" = 512 ] && [ "$hh" = 512 ]; } && pass "icon 512x512" || fail "icon must be 512x512 (got ${w}x${hh})"
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
