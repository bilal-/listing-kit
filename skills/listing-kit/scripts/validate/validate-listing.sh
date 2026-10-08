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

# Tab-separated facts for every PNG/JPEG directly in a dir (extension case-insensitive):
#   W H DEPTH COLORTYPE BYTES APPLE_CLASS PATH   (colortype 2=RGB, 6=RGBA, 99=unreadable)
images_in(){
  local f files=()
  for f in "$1"/*; do
    case "$f" in *.[pP][nN][gG]|*.[jJ][pP][gG]|*.[jJ][pP][eE][gG]) [ -f "$f" ] && files+=("$f");; esac
  done
  [ "${#files[@]}" -gt 0 ] && python3 "$LIB/imginfo.py" "${files[@]}"
}

# fastlane globs *.png / *.jpg / *.jpeg; on case-sensitive filesystems (Linux CI)
# an upper-case extension is never uploaded.
check_ext(){ # path
  case "$1" in *.png|*.jpg|*.jpeg) ;; *) fail "${1##*/}: rename with a lower-case extension (fastlane won't upload it)";; esac
}

# Check every copy field of one locale against the shared table in lib/fields.py.
fields(){ # store locale-dir [fallback-dir]
  local level msg out rc=0
  out="$(python3 "$LIB/fields.py" "$@")" || rc=$?
  while IFS=$'\t' read -r level msg; do
    [ -n "$level" ] || continue
    case "$level" in PASS) pass "$msg";; WARN) warn "$msg";; *) fail "$msg";; esac
  done <<<"$out"
  [ "$rc" = 0 ] || fail "could not check copy fields in $2 (fields.py exit $rc)"
}

# Does the app support iPad (→ iPad screenshots REQUIRED on the App Store)?
# Detection is stack-aware, not Expo-only (see references/stores/apple-app-store.md):
#   Expo/RN  → ios.supportsTablet in app.json / app.config.json
#   native   → TARGETED_DEVICE_FAMILY includes 2 in any *.pbxproj (also Flutter's
#              ios/Runner.xcodeproj), or UIDeviceFamily includes 2 in an Info.plist
#   dynamic → a literal `supportsTablet: true` in app.config.{js,ts,mjs,cjs}
# Set LK_SUPPORTS_IPAD=1 or 0 to override detection (e.g. config computed at runtime).
# Prints "True"/"False". Prunes node_modules/Pods/build so it stays fast on real repos.
supports_ipad(){
  case "${LK_SUPPORTS_IPAD:-}" in 1) echo True; return;; 0) echo False; return;; esac
  python3 - "$1" <<'PY2'
import sys,os,glob,json,re,plistlib
root=sys.argv[1]
def expo():
    for f in glob.glob(os.path.join(glob.escape(root),'app.json'))+glob.glob(os.path.join(glob.escape(root),'app.config.json')):
        try:
            cfg=json.load(open(f))
            if cfg.get('expo',cfg).get('ios',{}).get('supportsTablet'): return True
        except Exception: pass
    for f in glob.glob(os.path.join(glob.escape(root),'app.config.*')):
        if f.endswith(('.js','.ts','.mjs','.cjs')):
            try:
                if re.search(r'supportsTablet["\']?\s*:\s*true',open(f,errors='ignore').read()): return True
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
# Locales come from lib/listing.py, shared with build-review.sh.
apple_locales=(); play_locales=()
while IFS= read -r loc; do apple_locales+=("$loc"); done < <(python3 "$LIB/apple_assets.py" --locales "$ROOT")
while IFS= read -r loc; do play_locales+=("$loc"); done < <(python3 "$LIB/listing.py" play-locales "$ROOT/fastlane")
apple_default="$ROOT/fastlane/metadata/default"
apple_present=0; play_present=0
required_classes=()
{ [ "${#apple_locales[@]}" -gt 0 ] || [ -d "$ROOT/fastlane/screenshots" ]; } && apple_present=1
[ -d "$ROOT/fastlane/metadata/android" ] && play_present=1

# ---------------- App Store (deliver) ----------------
if [ "$apple_present" = 1 ]; then
  echo "${B}== Apple App Store ==${Z}"
  for loc in ${apple_locales[@]+"${apple_locales[@]}"}; do
    echo " locale $(basename "$loc"):"
    if [ -d "$apple_default" ]; then fields apple "$loc" "$apple_default"; else fields apple "$loc"; fi
  done
  fields apple-app "$ROOT/fastlane/metadata"

  # Screenshots: deliver assigns each image to a display class by its pixel size.
  # Checked per locale: ≤10 per class, Dynamic Island medium iPhone set, 13-inch iPad
  # set when the app runs on iPad.
  ipad_required=$(supports_ipad "$ROOT")
  [ "${LK_SUPPORTS_IPHONE:-1}" = 0 ] || required_classes+=('iPhone Dynamic Island (medium display)')
  [ "$ipad_required" != True ] || required_classes+=('iPad 13"')
  shot_dirs=0
  for sdir in "$ROOT"/fastlane/screenshots/*/; do
    [ -d "$sdir" ] || continue
    shot_dirs=$((shot_dirs+1))
    echo " screenshots $(basename "$sdir"):"
    classes=""; badfmt=0
    while IFS=$'\t' read -r w h depth ct bytes cls path; do
      base="${path##*/}"; check_ext "$path"
      if [ "$cls" = "-" ]; then fail "$base: ${w}x${h} is not an App Store screenshot size (see scripts/lib/apple-screenshot-sizes.tsv)"
      else classes="$classes$cls"$'\n'; fi
      [ "$ct" = 2 ] || { fail "$base: must be RGB no-alpha (colortype=$ct)"; badfmt=1; }
    done < <(images_in "$sdir")
    count_of(){ printf '%s' "$classes" | grep -c "^$1" || true; }
    while read -r n cls; do
      [ -n "$cls" ] && [ "$n" -gt 10 ] && fail "$cls: $n screenshots (App Store max is 10 per display class)"
    done < <(printf '%s' "$classes" | sort | uniq -c)
    # LK_SUPPORTS_IPHONE=0 for iPad-only apps (TARGETED_DEVICE_FAMILY = 2).
    if [ "${LK_SUPPORTS_IPHONE:-1}" != 0 ]; then
      iphone_hero=$(count_of 'iPhone Dynamic Island (medium display)')
      [ "$iphone_hero" -ge 1 ] && pass "iPhone screenshots present ($iphone_hero at Dynamic Island medium)" \
        || fail 'no iPhone Dynamic Island (medium display) screenshots — capture 1206x2622 or 1179x2556; large-display images do not fill this slot'
    fi
    if [ "$ipad_required" = "True" ]; then
      ipad13=$(count_of 'iPad 13"')
      [ "$ipad13" -ge 1 ] && pass "iPad screenshots present ($ipad13 at 13\") — required (app runs on iPad)" \
        || fail "app supports iPad but NO iPad screenshots at 13\" (Apple requires them)"
    fi
    [ "$badfmt" = 0 ] && pass "all screenshots are RGB/no-alpha"
  done
  [ "$shot_dirs" -gt 0 ] || fail "no fastlane/screenshots/<locale>/ directory (≥1 iPhone set required)"
fi

# Validate separate creative assets and the user's persisted Apple upload plan.
asset_result="$(python3 "$LIB/apple_assets.py" "$ROOT" ${required_classes[@]+"${required_classes[@]}"})"; asset_rc=$?
[ "$asset_rc" = 0 ] || fail "could not validate Apple assets (exit $asset_rc)"
while IFS=$'\t' read -r level msg; do
  [ -n "$level" ] || continue
  case "$level" in PASS) pass "$msg";; WARN) warn "$msg";; *) fail "$msg";; esac
done <<<"$asset_result"
if [ "$apple_present" = 1 ] && [ ! -f "$ROOT/.listing-kit/asset-plan.json" ]; then
  warn "no asset-plan.json: store minimums checked; requested extra sets/headers cannot be confirmed"
fi

# ---------------- Google Play (supply) ----------------
# Screenshots: JPEG or 24-bit PNG (8-bit RGB, no alpha), 320–3840 px per side,
# long side ≤ 2× short side, ≤8 per device type, ≥2 in total across types.
# Promotion eligibility (warn only): ≥4 screenshots at ≥1080 px, 9:16 or 16:9.
play_shots(){ # dir label
  local w h depth ct bytes cls path base lo hi n=0 big=0
  while IFS=$'\t' read -r w h depth ct bytes cls path; do
    n=$((n+1)); base="${path##*/}"; check_ext "$path"
    lo=$w; hi=$h; [ "$w" -gt "$h" ] && { lo=$h; hi=$w; }
    { [ "$lo" -ge 320 ] && [ "$hi" -le 3840 ]; } || fail "$base: side out of 320–3840 (${w}x${h})"
    [ "$lo" -gt 0 ] && [ $((hi * 1000)) -gt $((lo * 2000)) ] && fail "$base: aspect ${hi}/${lo} exceeds 2:1"
    { [ "$ct" = 2 ] && [ "$depth" = 8 ]; } || fail "$base: must be 24-bit no-alpha (depth=$depth colortype=$ct)"
    [ "$bytes" -le 8388608 ] || warn "$base: over 8 MB"
    # Promotion bar: ≥1080 px on the short side and exactly 9:16 / 16:9 (±1%).
    [ "$lo" -ge 1080 ] && [ $((hi * 900)) -ge $((lo * 1584)) ] && [ $((hi * 900)) -le $((lo * 1616)) ] && big=$((big+1))
  done < <(images_in "$1")
  [ "$n" -eq 0 ] && return
  [ "$n" -le 8 ] && pass "$2 screenshots: $n (≤8) ✓ format/size/aspect" || fail "$2 screenshots: $n (max 8)"
  [ "$2" = phone ] && [ "$big" -lt 4 ] && warn "$2: only $big screenshot(s) at ≥1080px; Play needs 4 at 9:16 or 16:9 for promotion eligibility"
  play_total=$((play_total+n))
}

# supply uploads images/<type>.{png,jpg,jpeg} (case-insensitive); echoes the match.
play_graphic(){ # images-dir type
  local f
  for f in "$1/$2".*; do
    case "$f" in *.[pP][nN][gG]|*.[jJ][pP][gG]|*.[jJ][pP][eE][gG]) [ -f "$f" ] && { echo "$f"; return; };; esac
  done
}

if [ "$play_present" = 1 ]; then
  echo "${B}== Google Play ==${Z}"
  [ "${#play_locales[@]}" -gt 0 ] || fail "fastlane/metadata/android has no locale folders (e.g. en-US/)"
  for loc in ${play_locales[@]+"${play_locales[@]}"}; do
    echo " locale $(basename "$loc"):"
    fields play "$loc"

    img="$loc/images"
    play_total=0
    play_shots "$img/phoneScreenshots" "phone"
    play_shots "$img/sevenInchScreenshots" '7" tablet'
    play_shots "$img/tenInchScreenshots" '10" tablet'
    play_shots "$img/tvScreenshots" "TV"
    play_shots "$img/wearScreenshots" "Wear OS"
    [ "$play_total" -ge 2 ] && pass "screenshots across device types: $play_total (≥2)" \
      || fail "screenshots: $play_total across device types (need ≥2)"

    # Graphics live directly in images/ — supply never uploads images/featureGraphic/*.
    for t in featureGraphic icon; do
      [ -d "$img/$t" ] && fail "images/$t/ is not uploaded by fastlane supply; move the file to images/$t.png"
    done

    fg="$(play_graphic "$img" featureGraphic)"
    if [ -n "$fg" ]; then
      check_ext "$fg"
      IFS=$'\t' read -r w h depth ct bytes cls path < <(python3 "$LIB/imginfo.py" "$fg")
      { [ "$w" = 1024 ] && [ "$h" = 500 ] && [ "$ct" = 2 ] && [ "$depth" = 8 ]; } \
        && pass "feature graphic 1024x500 24-bit no-alpha" \
        || fail "feature graphic must be 1024x500 24-bit no-alpha (got ${w}x${h} depth=$depth ct=$ct)"
    else fail "feature graphic MISSING (required to publish): images/featureGraphic.png"; fi

    # icon (32-bit PNG with alpha is allowed; max 1 MB)
    ic="$(play_graphic "$img" icon)"
    if [ -n "$ic" ]; then
      IFS=$'\t' read -r w h depth ct bytes cls path < <(python3 "$LIB/imginfo.py" "$ic")
      # By content, not just name: a JPEG saved as icon.png is still a JPEG.
      { case "$ic" in *.png) true;; *) false;; esac && [ "$(head -c 4 "$ic" | od -An -tx1 | tr -d ' \n')" = 89504e47 ]; } \
        || fail "icon must be a PNG (Play requires a 32-bit PNG)"
      { [ "$w" = 512 ] && [ "$h" = 512 ]; } && pass "icon 512x512" || fail "icon must be 512x512 (got ${w}x${h})"
      { [ "$depth" = 8 ] && { [ "$ct" = 6 ] || [ "$ct" = 2 ]; }; } \
        || fail "icon must be an 8-bit RGB(A) PNG (got depth=$depth colortype=$ct)"
      [ "$bytes" -le 1048576 ] || fail "icon is over 1 MB ($bytes bytes)"
    else fail "Play icon MISSING (required): images/icon.png"; fi
  done
fi

# ---------------- scope notice ----------------
if [ "$apple_present" = 0 ] && [ "$play_present" = 0 ]; then
  warn "no App Store or Google Play listing content found under $ROOT/fastlane — nothing to validate"
fi

# ---------------- secrets ----------------
scan(){ # dir label found-msg
  local rc=0; bash "$LIB/secret-scan.sh" "$1" >/dev/null 2>&1 || rc=$?
  case "$rc" in 0) pass "$2: clean";; 1) fail "$2: $3";; *) fail "$2: could not complete (exit $rc)";; esac
}
[ -d "$ROOT/fastlane" ] && scan "$ROOT/fastlane" "secret scan" "credentials found in committed tree"
# Committed Maestro flows are recipes, not secrets — they must reference creds, never inline them.
[ -d "$ROOT/store-assets" ] && scan "$ROOT/store-assets" "creative asset secret scan" "credentials found in creative assets"
[ -d "$ROOT/.listing-kit/flows" ] && scan "$ROOT/.listing-kit/flows" "flow secret scan" "credentials inlined in a committed Maestro flow"

echo "${B}── ${PASS} passed · ${WARN} warnings · ${FAIL} failures ──${Z}"
[ "$FAIL" -eq 0 ] && { echo "${G}LISTING VALID${Z}"; exit 0; } || { echo "${R}LISTING HAS FAILURES${Z}"; exit 1; }
