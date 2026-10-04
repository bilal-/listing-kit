#!/usr/bin/env bash
# Pre-grant runtime permissions so system dialogs don't interrupt Maestro flows.
#
# Usage:
#   grant-permissions.sh ios <bundle-id> [<device>]       # default device: booted
#   grant-permissions.sh android <application-id> [<serial>]
#
# CAVEAT (iOS): `simctl privacy` does NOT reliably cover camera or App Tracking
# Transparency, and some grants require the app not to be running. Residual
# dialogs must be dismissed inside the Maestro flow or via manual-assist.
set -euo pipefail

platform="${1:-}"
app="${2:-}"
if [ -z "$platform" ] || [ -z "$app" ]; then
  echo "Usage: $0 {ios|android} <app-id> [device|serial]" >&2
  exit 2
fi

case "$platform" in
  ios)
    device="${3:-booted}"
    command -v xcrun >/dev/null 2>&1 || { echo "xcrun not found (install Xcode command-line tools)." >&2; exit 1; }
    # Fails if the device isn't booted/valid or the app isn't installed on it, so a
    # broken setup isn't misreported as "unsupported" for every service below.
    xcrun simctl get_app_container "$device" "$app" >/dev/null 2>&1 || {
      echo "App '$app' not found on simulator '$device' (boot it and install the app first)." >&2
      exit 1
    }
    # Services that simctl privacy reliably supports:
    for svc in location-always photos contacts calendar reminders microphone media-library motion; do
      if xcrun simctl privacy "$device" grant "$svc" "$app" 2>/dev/null; then
        echo "granted: $svc"
      else
        echo "skip (unsupported on this runtime): $svc"
      fi
    done
    echo "NOTE: camera and App Tracking Transparency cannot be pre-granted — handle in-flow."
    ;;

  android)
    serial="${3:-}"
    adb_target=(adb)
    [ -n "$serial" ] && adb_target=(adb -s "$serial")
    # Without a device every grant fails and would be misreported as "not declared".
    "${adb_target[@]}" get-state >/dev/null 2>&1 || {
      echo "No Android device/emulator reachable${serial:+ at $serial} (check: adb devices)." >&2
      exit 1
    }
    "${adb_target[@]}" shell pm path "$app" >/dev/null 2>&1 || {
      echo "App '$app' is not installed on the device (install it first)." >&2
      exit 1
    }
    for perm in \
      android.permission.ACCESS_FINE_LOCATION \
      android.permission.ACCESS_COARSE_LOCATION \
      android.permission.CAMERA \
      android.permission.RECORD_AUDIO \
      android.permission.READ_MEDIA_IMAGES \
      android.permission.POST_NOTIFICATIONS \
      android.permission.READ_CONTACTS ; do
      if "${adb_target[@]}" shell pm grant "$app" "$perm" 2>/dev/null; then
        echo "granted: $perm"
      else
        echo "skip (not declared by app): $perm"
      fi
    done
    ;;

  *)
    echo "Usage: $0 {ios|android} <app-id> [device|serial]" >&2
    exit 2
    ;;
esac
