#!/usr/bin/env bash
# Sanitize the status bar for clean, store-quality screenshots:
# 9:41, full battery, full signal, Wi-Fi.
#
# Usage:
#   sanitize-status-bar.sh ios [<device>]      # default device: booted
#   sanitize-status-bar.sh android [<serial>]  # default serial: first attached
#
# iOS uses `xcrun simctl status_bar override`.
# Android uses SYSTEM DEMO MODE (sysui_demo) — NOT plain `adb shell settings`.
set -euo pipefail

platform="${1:-}"

case "$platform" in
  ios)
    device="${2:-booted}"
    xcrun simctl status_bar "$device" override \
      --time "9:41" \
      --dataNetwork wifi \
      --wifiMode active --wifiBars 3 \
      --cellularMode active --cellularBars 4 \
      --batteryState discharging --batteryLevel 100   # "charged" draws a charging bolt
    echo "iOS status bar sanitized on '$device' (9:41, full battery/signal)."
    ;;

  android)
    serial="${2:-}"
    adb_target=(adb)
    [ -n "$serial" ] && adb_target=(adb -s "$serial")

    demo(){ "${adb_target[@]}" shell am broadcast -a com.android.systemui.demo -e command "$@" >/dev/null; }

    # Enable demo mode, then push a clean status bar via broadcasts: Wi-Fi only
    # (a mobile icon shows a "3G"/"LTE" label on recent releases), no system icons.
    "${adb_target[@]}" shell settings put global sysui_demo_allowed 1
    demo enter
    demo clock -e hhmm 0941
    demo battery -e level 100 -e plugged false
    demo network -e wifi show -e level 4 -e fully true
    demo network -e mobile hide
    demo status -e location hide -e alarm hide -e volume hide -e bluetooth hide -e zen hide \
      -e mute hide -e speakerphone hide -e cast hide -e hotspot hide -e sync hide -e eri hide -e tty hide
    demo notifications -e visible false

    # Android 15+ ignores "notifications visible false" for some system notifications
    # (e.g. Safety Center's shield). On an emulator, snooze whatever is posted for an
    # hour; a physical device's notifications are left alone.
    if [ "$("${adb_target[@]}" shell getprop ro.kernel.qemu 2>/dev/null | tr -d '\r')" = 1 ] \
       || [ "$("${adb_target[@]}" shell getprop ro.boot.qemu 2>/dev/null | tr -d '\r')" = 1 ]; then
      "${adb_target[@]}" shell dumpsys notification --noredact 2>/dev/null \
        | grep -o 'NotificationRecord([^ ]* pkg=[^ ]* user=[^ ]* id=[^ ]* tag=[^ ]* importance=[^ ]* key=[^:]*' \
        | sed 's/.*key=//' | sort -u \
        | while IFS= read -r key; do
            "${adb_target[@]}" shell cmd notification snooze --for 3600000 "'$key'" >/dev/null 2>&1 || true
          done
    else
      echo "Note: not an emulator; dismiss notifications by hand if any icons remain."
    fi
    echo "Android status bar sanitized via demo mode (9:41, full battery/signal)."
    echo "Note: run 'adb shell am broadcast -a com.android.systemui.demo -e command exit' to restore."
    ;;

  *)
    echo "Usage: $0 {ios|android} [device|serial]" >&2
    exit 2
    ;;
esac
