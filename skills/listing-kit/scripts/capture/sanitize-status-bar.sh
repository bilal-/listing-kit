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
      --batteryState charged --batteryLevel 100
    echo "iOS status bar sanitized on '$device' (9:41, full battery/signal)."
    ;;

  android)
    serial="${2:-}"
    adb_target=(adb)
    [ -n "$serial" ] && adb_target=(adb -s "$serial")

    # Enable demo mode, then push a clean status bar via broadcasts.
    "${adb_target[@]}" shell settings put global sysui_demo_allowed 1
    "${adb_target[@]}" shell am broadcast -a com.android.systemui.demo -e command enter >/dev/null
    "${adb_target[@]}" shell am broadcast -a com.android.systemui.demo -e command clock -e hhmm 0941 >/dev/null
    "${adb_target[@]}" shell am broadcast -a com.android.systemui.demo -e command battery -e level 100 -e plugged false >/dev/null
    "${adb_target[@]}" shell am broadcast -a com.android.systemui.demo -e command network -e wifi show -e level 4 >/dev/null
    "${adb_target[@]}" shell am broadcast -a com.android.systemui.demo -e command network -e mobile show -e datatype none -e level 4 >/dev/null
    "${adb_target[@]}" shell am broadcast -a com.android.systemui.demo -e command notifications -e visible false >/dev/null
    echo "Android status bar sanitized via demo mode (9:41, full battery/signal)."
    echo "Note: run 'adb shell am broadcast -a com.android.systemui.demo -e command exit' to restore."
    ;;

  *)
    echo "Usage: $0 {ios|android} [device|serial]" >&2
    exit 2
    ;;
esac
