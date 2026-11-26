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

# Tab-separated facts for PNG/JPEG files (extension case-insensitive):
#   W H DEPTH COLORTYPE BYTES APPLE_CLASS DECODE_STATUS PATH
imginfo_out=""
dir_img_files=()
im_unavailable=0

run_imginfo(){ # label file...
  local label="$1"; shift
  local rc=0
  imginfo_out="$(python3 "$LIB/imginfo.py" --validate "$@")" || rc=$?
  if [ "$rc" != 0 ]; then
    fail "could not inspect images for $label (imginfo.py exit $rc)"
    imginfo_out=""
    return 1
  fi
  return 0
}

record_decode(){ # status basename
  case "$1" in
    ok) return 0 ;;
    unavailable) im_unavailable=1; return 0 ;;
    "could not decode:"*) warn "$2: $1"; return 0 ;;
    "bad: "*) fail "$2: ${1#bad: }"; return 1 ;;
    *) fail "$2: image failed full decode"; return 1 ;;
  esac
}

dir_images(){ # label dir
  local label="$1" dir="$2" f
  dir_img_files=()
  imginfo_out=""
  for f in "$dir"/*; do
    case "$f" in *.[pP][nN][gG]|*.[jJ][pP][gG]|*.[jJ][pP][eE][gG]) [ -f "$f" ] && dir_img_files+=("$f");; esac
  done
  [ "${#dir_img_files[@]}" -gt 0 ] || return 0
  run_imginfo "$label" "${dir_img_files[@]}"
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
# Apple presence + locales come from apple_assets.py; Play uses listing.py.
# Both discovery paths are shared with build-review.sh.
apple_locales=(); play_locales=()
apple_loc_rc=0; apple_det_rc=0; play_loc_rc=0
apple_loc_out="$(python3 "$LIB/apple_assets.py" --locales "$ROOT")" || apple_loc_rc=$?
[ "$apple_loc_rc" = 0 ] || fail "could not discover Apple locales (apple_assets.py exit $apple_loc_rc)"
while IFS= read -r loc; do
  [ -n "$loc" ] && apple_locales+=("$loc")
done <<<"$apple_loc_out"

apple_present=0
apple_det_out="$(python3 "$LIB/apple_assets.py" --has-apple "$ROOT")" || apple_det_rc=$?
if [ "$apple_det_rc" != 0 ]; then
  fail "could not detect Apple listing (apple_assets.py exit $apple_det_rc)"
elif [ "$apple_det_out" = 1 ]; then
  apple_present=1
fi

play_loc_out="$(python3 "$LIB/listing.py" play-locales "$ROOT/fastlane")" || play_loc_rc=$?
[ "$play_loc_rc" = 0 ] || fail "could not discover Google Play locales (listing.py exit $play_loc_rc)"
while IFS= read -r loc; do
  [ -n "$loc" ] && play_locales+=("$loc")
done <<<"$play_loc_out"

apple_default="$ROOT/fastlane/metadata/default"
play_present=0
required_classes=()
[ -d "$ROOT/fastlane/metadata/android" ] && play_present=1

# ---------------- App Store (deliver) ----------------
if [ "$apple_present" = 1 ]; then
  echo "${B}== Apple App Store ==${Z}"
  if [ "${#apple_locales[@]}" -gt 0 ]; then
    for loc in "${apple_locales[@]}"; do
      echo " locale $(basename "$loc"):"
      if [ -d "$apple_default" ]; then fields apple "$loc" "$apple_default"; else fields apple "$loc"; fi
    done
  elif [ -d "$apple_default" ]; then
    echo " locale default:"
    fields apple "$apple_default"
  else
    fail "no fastlane/metadata/<locale>/ directory (e.g. en-US/)"
  fi
  fields apple-app "$ROOT/fastlane/metadata"

  # Screenshots: deliver assigns each image to a display class by its pixel size.
  # Checked per locale: ≤10 per class, Dynamic Island medium iPhone set, 13-inch iPad
  # set when the app runs on iPad.
  ipad_rc=0
  ipad_required="$(supports_ipad "$ROOT")" || ipad_rc=$?
  [ "$ipad_rc" = 0 ] || fail "could not detect iPad support (exit $ipad_rc)"
  [ "${LK_SUPPORTS_IPHONE:-1}" = 0 ] || required_classes+=('iPhone Dynamic Island (medium display)')
  [ "$ipad_required" != True ] || required_classes+=('iPad 13"')
  shot_dirs=0
  for loc in ${apple_locales[@]+"${apple_locales[@]}"}; do
    sdir="$ROOT/fastlane/screenshots/${loc##*/}"
    [ -d "$sdir" ] || continue
    shot_dirs=$((shot_dirs+1))
    echo " screenshots $(basename "$sdir"):"
    classes=""; badfmt=0
    if dir_images "screenshots $(basename "$sdir")" "$sdir"; then
      while IFS=$'\t' read -r w h depth ct bytes cls dec path; do
        [ -n "$w" ] || continue
        base="${path##*/}"; check_ext "$path"
        s_dec=1; record_decode "$dec" "$base" || { s_dec=0; badfmt=1; }
        if [ "$cls" = "-" ]; then fail "$base: ${w}x${h} is not an App Store screenshot size (see scripts/lib/apple-screenshot-sizes.tsv)"
        elif [ "$s_dec" = 1 ]; then classes="$classes$cls"$'\n'; fi
        [ "$ct" = 2 ] || { fail "$base: must be RGB no-alpha (colortype=$ct)"; badfmt=1; }
      done <<<"$imginfo_out"
    else
      badfmt=1
    fi
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
asset_rc=0
asset_result="$(python3 "$LIB/apple_assets.py" "$ROOT" ${required_classes[@]+"${required_classes[@]}"})" || asset_rc=$?
[ "$asset_rc" = 0 ] || fail "could not validate Apple assets (apple_assets.py exit $asset_rc)"
while IFS=$'\t' read -r level msg; do
  [ -n "$level" ] || continue
  case "$level" in PASS) pass "$msg";; WARN) warn "$msg";; IM_UNAVAILABLE) im_unavailable=1;; *) fail "$msg";; esac
done <<<"$asset_result"
if [ "$apple_present" = 1 ] && [ ! -f "$ROOT/.listing-kit/asset-plan.json" ]; then
  warn "no asset-plan.json: store minimums checked; requested extra sets/headers cannot be confirmed"
fi

# ---------------- Google Play (supply) ----------------
# Screenshots: JPEG or 24-bit PNG (8-bit RGB, no alpha), 320–3840 px per side,
# long side ≤ 2× short side, ≤8 per device type, ≥2 in total across types.
# Promotion eligibility (warn only): ≥4 screenshots at ≥1080 px, 9:16 or 16:9.
play_shots(){ # dir label
  local w h depth ct bytes cls dec path base lo hi n=0 big=0 dec_ok=1
  dir_images "$2 screenshots" "$1" || return
  [ "${#dir_img_files[@]}" -gt 0 ] || return
  while IFS=$'\t' read -r w h depth ct bytes cls dec path; do
    [ -n "$w" ] || continue
    n=$((n+1)); base="${path##*/}"; check_ext "$path"
    record_decode "$dec" "$base" || dec_ok=0
    lo=$w; hi=$h; [ "$w" -gt "$h" ] && { lo=$h; hi=$w; }
    { [ "$lo" -ge 320 ] && [ "$hi" -le 3840 ]; } || fail "$base: side out of 320–3840 (${w}x${h})"
    [ "$lo" -gt 0 ] && [ $((hi * 1000)) -gt $((lo * 2000)) ] && fail "$base: aspect ${hi}/${lo} exceeds 2:1"
    { [ "$ct" = 2 ] && [ "$depth" = 8 ]; } || fail "$base: must be 24-bit no-alpha (depth=$depth colortype=$ct)"
    [ "$bytes" -le 8388608 ] || warn "$base: over 8 MB"
    # Promotion bar: ≥1080 px on the short side and exactly 9:16 / 16:9 (±1%).
    [ "$lo" -ge 1080 ] && [ $((hi * 900)) -ge $((lo * 1584)) ] && [ $((hi * 900)) -le $((lo * 1616)) ] && big=$((big+1))
  done <<<"$imginfo_out"
  [ "$n" -eq 0 ] && return
  if [ "$n" -le 8 ]; then
    [ "$dec_ok" = 1 ] && pass "$2 screenshots: $n (≤8) ✓ format/size/aspect"
  else
    fail "$2 screenshots: $n (max 8)"
  fi
  [ "$2" = phone ] && [ "$big" -lt 4 ] && warn "$2: only $big screenshot(s) at ≥1080px; Play needs 4 at 9:16 or 16:9 for promotion eligibility"
  play_total=$((play_total+n))
}

play_graphics(){ # images-dir type
  local dir="$1" type="$2" f w h depth ct bytes cls dec path decoded
  local files=()
  [ -d "$dir/$type" ] && fail "images/$type/ is not uploaded by fastlane supply; move the file to images/$type.png"
  for f in "$dir/$type".*; do
    case "${f#"$dir/$type."}" in [pP][nN][gG]|[jJ][pP][gG]|[jJ][pP][eE][gG]) [ -f "$f" ] && files+=("$f");; esac
  done
  if [ "${#files[@]}" -eq 0 ]; then
    case "$type" in
      featureGraphic) fail "feature graphic MISSING (required to publish): images/$type.png";;
      icon) fail "Play icon MISSING (required): images/$type.png";;
    esac
    return
  fi
  [ "${#files[@]}" -le 1 ] || fail "duplicate $type candidates: ${files[*]}"
  run_imginfo "$type" "${files[@]}" || return
  while IFS=$'\t' read -r w h depth ct bytes cls dec path; do
    check_ext "$path"
    decoded=1; record_decode "$dec" "${path##*/}" || decoded=0
    case "$type" in
      featureGraphic)
        if [ "$w" = 1024 ] && [ "$h" = 500 ] && [ "$ct" = 2 ] && [ "$depth" = 8 ]; then
          [ "$decoded" = 1 ] && pass "feature graphic 1024x500 24-bit no-alpha"
        else
          fail "feature graphic must be 1024x500 24-bit no-alpha (got ${w}x${h} depth=$depth ct=$ct)"
        fi ;;
      icon)
        if [[ "$path" != *.png ]] || [ "$(head -c 4 "$path" | od -An -tx1 | tr -d ' \n')" != 89504e47 ]; then
          fail "icon must be a PNG (Play requires 32-bit PNG)"
        fi
        if [ "$w" = 512 ] && [ "$h" = 512 ]; then
          [ "$decoded" = 1 ] && pass "icon 512x512"
        else
          fail "icon must be 512x512 (got ${w}x${h})"
        fi
        { [ "$depth" = 8 ] && { [ "$ct" = 6 ] || [ "$ct" = 2 ]; }; } || fail "icon must be an 8-bit RGB(A) PNG (got depth=$depth colortype=$ct)"
        [ "$bytes" -le 1048576 ] || fail "icon over 1 MB ($bytes bytes)" ;;
      tvBanner)
        if [ "$w" = 1280 ] && [ "$h" = 720 ]; then
          [ "$decoded" = 1 ] && pass "TV banner 1280x720"
        else
          fail "TV banner must be 1280x720 (got ${w}x${h})"
        fi ;;
    esac
  done <<<"$imginfo_out"
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

    for t in featureGraphic icon tvBanner; do
      play_graphics "$img" "$t"
    done
  done
fi

if [ "$im_unavailable" = 1 ]; then
  warn "ImageMagick not available: images were checked structurally only"
fi

# ---------------- scope notice ----------------
if [ "$apple_present" = 0 ] && [ "$play_present" = 0 ] && [ "$apple_det_rc" = 0 ] && [ "$apple_loc_rc" = 0 ] && [ "$play_loc_rc" = 0 ]; then
  fail "no App Store or Google Play listing was found under $ROOT — nothing to validate"
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
[ -f "$ROOT/.listing-kit/asset-plan.json" ] && scan "$ROOT/.listing-kit/asset-plan.json" "asset plan secret scan" "credentials found in asset-plan.json"

echo "${B}── ${PASS} passed · ${WARN} warnings · ${FAIL} failures ──${Z}"
[ "$FAIL" -eq 0 ] && { echo "${G}LISTING VALID${Z}"; exit 0; } || { echo "${R}LISTING HAS FAILURES${Z}"; exit 1; }
