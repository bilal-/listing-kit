#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

new_tempdir T
new_stubdir
APP="$T/app with spaces"
KIT="$APP/.listing-kit"
SUT="$SCRIPTS/capture/capture.py"
mkdir -p "$KIT/flows"
export CALLS="$STUB_LOG" IOS_DEVICES="$T/ios.json" ANDROID_DEVICES="$T/android"
export IOS_IMAGE="$T/ios.png" ANDROID_IMAGE="$T/android.png"
fake_png "$IOS_IMAGE" 1206 2622
fake_png "$ANDROID_IMAGE" 1080 2400
for tool in bash python3 cat cp dirname mktemp mkdir mv rm tr; do
  ln -s "$(command -v "$tool")" "$STUB_BIN/$tool"
done
cat > "$STUB_BIN/xcrun" <<'SH'
#!/usr/bin/env bash
echo "xcrun $*" >> "$CALLS"
case "$*" in
  'simctl list devices available -j') cat "$IOS_DEVICES";;
  'simctl list devicetypes -j') echo '{"devicetypes":[{"name":"iPhone 17","identifier":"com.apple.CoreSimulator.SimDeviceType.iPhone-17"}]}';;
  'simctl get_app_container '*) [ -z "${NOT_INSTALLED:-}" ] && echo /container/App.app;;
  'simctl io '*screenshot*) for out; do :; done; cp "$IOS_IMAGE" "$out";;
  'simctl boot '*|'simctl bootstatus '*|'simctl status_bar '*) exit 0;;
  *) exit 99;;
esac
SH
cat > "$STUB_BIN/adb" <<'SH'
#!/usr/bin/env bash
echo "adb $*" >> "$CALLS"
if [ "$1" = devices ]; then
  echo 'List of devices attached'
  while read -r serial; do echo "$serial device"; done < "$ANDROID_DEVICES"
  exit 0
fi
serial="$2"
shift 2
case "$*" in
  'emu avd name') case "$serial" in emulator-5554) echo pixel_9;; *) echo pixel_tablet;; esac; echo OK;;
  'shell pm path '*) [ -n "${NOT_INSTALLED:-}" ] || echo package:/installed/base.apk;;
  'exec-out screencap -p') cat "$ANDROID_IMAGE";;
  'shell settings '*|'shell am broadcast '*|'shell getprop '*) exit 0;;
  *) exit 99;;
esac
SH
cat > "$STUB_BIN/maestro" <<'SH'
#!/usr/bin/env bash
echo "maestro $*" >> "$CALLS"
echo 'flow output'
if [ -n "${FAIL_SCREEN:-}" ] && [[ "$*" = *"LK_SCREEN=$FAIL_SCREEN" ]]; then
  for i in {1..18}; do echo "diagnostic_$i." >&2; done
  exit 3
fi
SH
cat > "$STUB_BIN/magick" <<'SH'
#!/usr/bin/env bash
echo "magick $*" >> "$CALLS"
for out; do :; done
if [ "$out" = info: ]; then
  echo "${VARIATION:-0.25}"
else
  [ -z "${BAD_NORMALIZE:-}" ] || exit 1
  cp "$1" "${out#PNG24:}"
fi
SH
chmod +x "$STUB_BIN"/{adb,xcrun,magick,maestro}
cat > "$IOS_DEVICES" <<'JSON'
{"devices":{"com.apple.CoreSimulator.SimRuntime.iOS-26-1":[
{"name":"iPhone 17","state":"Shutdown","udid":"OFF"},
{"name":"Renamed","deviceTypeIdentifier":"com.apple.CoreSimulator.SimDeviceType.iPhone-17","state":"Booted","udid":"ON"},
{"name":"iPad","state":"Booted","udid":"PAD"}]}}
JSON
printf '%s\n' emulator-5556 emulator-5554 > "$ANDROID_DEVICES"
python3 - "$ROOT/tests/fixtures/plan-example.json" "$KIT" <<'PY'
import json, sys
from pathlib import Path
p = json.loads(Path(sys.argv[1]).read_text())
kit = Path(sys.argv[2])
del p["app"]["demoEntry"], p["graphics"]
p["style"] = {"mode": "framed"}
p["targets"][2]["capture"]["nativeSize"] = [1080, 2400]
for s in p["screens"]:
    for f in [s.get("flow"), *s.get("flows", {}).values()]:
        if f:
            (kit.parent / f).touch()
(kit / "listing.json").write_text(json.dumps(p))
PY
cp "$KIT/listing.json" "$T/original.json"

run() {
  : > "$CALLS"
  OUT="$(PATH="$STUB_BIN" python3 "$SUT" "$APP" "$@" 2>&1)"
  RC=$?
}
ios() { run --target iphone-medium --screen agents "$@"; }
android() { run --target play-phone --screen agents "$@"; }
raw="$KIT/raw/play-phone/en-US/agents.png"
ios_raw="$KIT/raw/iphone-medium/en-US/agents.png"

it 'filters targets and screens and discovers devices without booting, running flows or writing assets'
run --dry-run --target play-phone --target iphone-medium --screen agents
assert_eq 0 "$RC"
assert_contains "$OUT" emulator-5554
assert_contains "$OUT" 'ON'
assert_contains "$OUT" agents
assert_not_contains "$OUT" terminal
assert_not_contains "$OUT" play-tablet
assert_not_contains "$OUT" closing
assert_eq "" "$(grep -Ev '^(xcrun simctl list|adb devices|adb -s [^ ]+ emu avd name)' "$CALLS")"
[ ! -e "$KIT/raw" ] && [ ! -e "$KIT/logs" ] && pass 'dry run left no files' || fail 'dry run wrote files'
run --dry-run --target iphone-medium --screen terminal --screen agents
assert_contains "$OUT" terminal
assert_contains "$OUT" agents
run --target typo
assert_eq 2 "$RC"

it 'uses the booted simulator type, installed bundle, flow variables and ordered capture helpers'
ios
assert_eq 0 "$RC"
assert_file "$ios_raw"
assert_contains "$(cat "$CALLS")" 'get_app_container ON sh.bilal.shellbell'
assert_contains "$(cat "$CALLS")" '-e LK_LOCALE=en-US -e LK_TARGET=iphone-medium -e LK_SCREEN=agents'
assert_eq $'maestro\nsanitize\ncapture\nnormalize' "$(sed -n -e '/^maestro --device ON test /s/.*/maestro/p' -e '/simctl status_bar ON /s/.*/sanitize/p' -e '/simctl io ON screenshot --type=png --display internal/s/.*/capture/p' -e '/^magick .*PNG24:/s/.*/normalize/p' "$CALLS")"
assert_not_contains "$(cat "$CALLS")" 'simctl boot '
assert_contains "$(cat "$KIT/logs/iphone-medium/agents.en-US.log")" 'flow output'

it 'honors local pins and CLI precedence and waits for a shutdown simulator'
echo '{"devices":{"iphone-medium":"OFF"}}' > "$KIT/local.json"
ios --dry-run
assert_contains "$OUT" OFF
assert_not_contains "$(cat "$CALLS")" 'simctl boot'
ios
assert_eq 0 "$RC"
assert_contains "$(cat "$CALLS")" $'simctl boot OFF\nxcrun simctl bootstatus OFF -b\nxcrun simctl get_app_container OFF'
ios --device ON
assert_eq 0 "$RC"
assert_not_contains "$(cat "$CALLS")" OFF
rm "$KIT/local.json"

it 'lists available types and a creation command when no matching iOS device exists'
cp "$IOS_DEVICES" "$T/all-ios"
echo '{"devices":{"iOS":[{"name":"iPad","udid":"PAD","state":"Booted"}]}}' > "$IOS_DEVICES"
ios
assert_eq 1 "$RC"
assert_contains "$OUT" iPad
assert_contains "$OUT" 'xcrun simctl create'
assert_not_contains "$(cat "$CALLS")" 'simctl create'
it 'reports malformed simulator inventory as a failed job with a summary'
echo '{"devices":{"iOS":[{"state":"Booted"}]}}' > "$IOS_DEVICES"
ios
assert_eq 1 "$RC"
assert_contains "$OUT" 'simulator inventory'
assert_not_contains "$OUT" Traceback
assert_contains "$OUT" '1 failed'
cp "$T/all-ios" "$IOS_DEVICES"

it 'matches the AVD and preserves the full native Android capture'
android
assert_eq 0 "$RC"
assert_eq $'maestro\nsanitize\ncapture\nnormalize' "$(sed -n -e '/^maestro --device emulator-5554 test /s/.*/maestro/p' -e '/shell settings put global sysui_demo_allowed/s/.*/sanitize/p' -e '/exec-out screencap -p/s/.*/capture/p' -e '/^magick .*PNG24:/s/.*/normalize/p' "$CALLS")"
assert_file "$raw"
assert_not_contains "$(cat "$CALLS")" '-crop'
printf '%s\n' emulator-5556 emulator-5558 > "$ANDROID_DEVICES"
android
assert_eq 1 "$RC"
assert_contains "$OUT" emulator-5558
assert_contains "$OUT" pixel_tablet

it 'refuses a physical device, including when pinned, until explicitly allowed'
echo usb-serial > "$ANDROID_DEVICES"
android --device usb-serial
assert_eq 1 "$RC"
assert_contains "$OUT" '--allow-device'
assert_eq 'adb devices' "$(cat "$CALLS")"
android --allow-device
assert_eq 0 "$RC"
assert_contains "$(cat "$CALLS")" 'adb -s usb-serial exec-out screencap -p'
echo emulator-5554 > "$ANDROID_DEVICES"

it 'checks both installs before launching Maestro'
export NOT_INSTALLED=1
for target in iphone-medium play-phone; do
  run --target "$target" --screen agents
  assert_eq 1 "$RC"
  assert_contains "$OUT" 'build and install'
  assert_contains "$OUT" 'references/stacks/'
  assert_not_contains "$(cat "$CALLS")" maestro
done
unset NOT_INSTALLED

it 'keeps old raw files, reports the last 15 log lines, and stops unless asked to continue'
printf old > "$raw"
export FAIL_SCREEN=agents
run --target play-phone
assert_eq 1 "$RC"
assert_eq old "$(cat "$raw")"
assert_contains "$OUT" '.listing-kit/logs/play-phone/agents.en-US.log'
assert_contains "$OUT" 'diagnostic_4.'
assert_contains "$OUT" 'diagnostic_18.'
assert_not_contains "$OUT" 'diagnostic_3.'
assert_contains "$OUT" skipped
assert_not_contains "$(cat "$CALLS")" 'LK_SCREEN=terminal'
assert_not_contains "$(cat "$CALLS")" 'exec-out'
run --target play-phone --keep-going
assert_eq 1 "$RC"
assert_file "$KIT/raw/play-phone/en-US/terminal.png"
assert_eq 1 "$(grep -c 'pm path' "$CALLS")"
unset FAIL_SCREEN

it 'rejects a swapped native size with flow guidance on both platforms'
export IOS_IMAGE="$T/ios-swapped.png" ANDROID_IMAGE="$T/android-swapped.png"
fake_png "$IOS_IMAGE" 2622 1206
fake_png "$ANDROID_IMAGE" 2400 1080
for target in iphone-medium play-phone; do
  run --target "$target" --screen agents
  assert_eq 1 "$RC"
  assert_contains "$OUT" 'wrong orientation'
  assert_contains "$OUT" flow
done
export IOS_IMAGE="$T/ios.png" ANDROID_IMAGE="$T/android.png"
it 'refuses blank Android frames and preserves previous assets on normalize failure'
VARIATION=0 android
assert_eq 1 "$RC"
assert_contains "$OUT" 'lank'
BAD_NORMALIZE=1 android
assert_eq 1 "$RC"
assert_eq old "$(cat "$raw")"

it 'checks landscape orientation even when the plan omits a native size'
run --target play-tablet --screen agents
assert_eq 1 "$RC"
assert_contains "$OUT" 'wrong orientation'
export ANDROID_IMAGE="$T/android-swapped.png"
run --target play-tablet --screen agents
assert_eq 0 "$RC"
assert_contains "$(cat "$CALLS")" '01_agents_tablet.yaml'
export ANDROID_IMAGE="$T/android.png"

it 'raw mode requires the target dimensions and never crops'
sed 's/"mode": "framed"/"mode": "raw"/' "$T/original.json" > "$KIT/listing.json"
android
assert_eq 1 "$RC"
assert_contains "$OUT" 'raw'
assert_contains "$OUT" '1080x1920'
assert_eq old "$(cat "$raw")"
cp "$T/original.json" "$KIT/listing.json"

it 'explains the exact raw upload size when the iOS helper rejects the geometry'
sed 's/"mode": "framed"/"mode": "raw"/' "$T/original.json" > "$KIT/listing.json"
IOS_IMAGE="$T/android.png" ios
assert_eq 1 "$RC"
assert_contains "$OUT" 'raw upload'
assert_contains "$OUT" '1206x2622'
ios
assert_eq 0 "$RC"
assert_contains "$OUT" "raw upload 1206x2622"
cp "$T/original.json" "$KIT/listing.json"

it 'passes a store locale to Maestro and writes the logical capture locale path'
python3 - "$KIT/listing.json" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
p = json.loads(path.read_text())
p["locales"].append({"id":"zh","play":"zh-CN"})
p["targets"][2]["captureLocales"] = "all"
path.write_text(json.dumps(p))
PY
android
assert_eq 0 "$RC"
assert_contains "$(cat "$CALLS")" '-e LK_LOCALE=zh-CN'
assert_file "$KIT/raw/play-phone/zh/agents.png"
assert_file "$KIT/logs/play-phone/agents.zh.log"
cp "$T/original.json" "$KIT/listing.json"

it 'names missing tools and installation hints and exits 3 before capture'
for tool in adb xcrun maestro magick; do
  mv "$STUB_BIN/$tool" "$T/hidden"
  if [ "$tool" = xcrun ]; then ios; else android; fi
  assert_eq 3 "$RC"
  if [ "$tool" = magick ]; then assert_contains "$OUT" ImageMagick; else assert_contains "$OUT" "$tool"; fi
  assert_contains "$OUT" 'install'
  mv "$T/hidden" "$STUB_BIN/$tool"
done

it 'manual assist waits for confirmation, and EOF preserves the old capture'
printf old > "$raw"
android --manual </dev/null
assert_eq 1 "$RC"
assert_eq old "$(cat "$raw")"
android --manual <<< ''
assert_eq 0 "$RC"
assert_not_contains "$(cat "$CALLS")" maestro
assert_contains "$(cat "$CALLS")" 'exec-out screencap'

it 'rejects an invalid capture plan before discovery, even when filtering'
rm "$KIT/flows/terminal.yaml"
android --dry-run
assert_eq 2 "$RC"
assert_contains "$OUT" 'terminal.yaml'
assert_eq '' "$(cat "$CALLS")"

summary
