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

clean_err() {
  printf '%s' "$1" | tr '\r\n\t' '   ' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//; s/[[:space:]][[:space:]]+/ /g'
}

is_unsupported_ios_service() {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    *"unsupported service"*|*"invalid service"*|*"unknown service"*|*"unrecognized service"*|*"service"*"not supported"*|*"not a valid service"*)
      return 0 ;;
    *)
      return 1 ;;
  esac
}

applicable_count=0
granted=0
failed=()

case "$platform" in
  ios)
    device="${3:-booted}"
    command -v xcrun >/dev/null 2>&1 || { echo "xcrun not found (install Xcode command-line tools)." >&2; exit 1; }
    # Fails if the device isn't booted/valid or the app isn't installed on it, so a
    # broken setup isn't misreported for every service below.
    xcrun simctl get_app_container "$device" "$app" >/dev/null 2>&1 || {
      echo "App '$app' not found on simulator '$device' (boot it and install the app first)." >&2
      exit 1
    }
    # Some grants only take effect while the app is not running.
    xcrun simctl terminate "$device" "$app" >/dev/null 2>&1 || true
    for svc in location-always photos contacts calendar reminders microphone media-library motion; do
      rc=0
      err="$(xcrun simctl privacy "$device" grant "$svc" "$app" 2>&1)" || rc=$?
      if [ "$rc" -eq 0 ]; then
        applicable_count=$((applicable_count + 1))
        echo "granted: $svc"
        granted=$((granted + 1))
      else
        msg="$(clean_err "$err")"
        [ -n "$msg" ] || msg="exit $rc"
        if is_unsupported_ios_service "$msg"; then
          echo "skip (unsupported service): $svc"
        else
          applicable_count=$((applicable_count + 1))
          echo "failed: $svc ($msg)" >&2
          failed+=("$svc")
          if ! xcrun simctl get_app_container "$device" "$app" >/dev/null 2>&1; then
            echo "Simulator '$device' is no longer reachable while granting $svc ($msg)." >&2
            break
          fi
        fi
      fi
    done
    if [ "$applicable_count" -eq 0 ]; then
      echo "NOTE: none of the pre-grantable privacy services are supported on simulator '$device' — nothing to grant."
    fi
    echo "NOTE: camera and App Tracking Transparency cannot be pre-granted — handle in-flow."
    ;;

  android)
    serial="${3:-}"
    command -v adb >/dev/null 2>&1 || { echo "adb not found (install Android platform-tools)." >&2; exit 1; }
    adb_target=(adb)
    [ -n "$serial" ] && adb_target=(adb -s "$serial")
    "${adb_target[@]}" get-state >/dev/null 2>&1 || {
      echo "No Android device/emulator reachable${serial:+ at $serial} (check: adb devices)." >&2
      exit 1
    }
    "${adb_target[@]}" shell pm path "$app" >/dev/null 2>&1 || {
      echo "App '$app' is not installed on the device (install it first)." >&2
      exit 1
    }
    dump_rc=0
    dump_out="$("${adb_target[@]}" shell dumpsys package "$app" 2>&1)" || dump_rc=$?
    if [ "$dump_rc" -ne 0 ]; then
      if ! "${adb_target[@]}" get-state >/dev/null 2>&1; then
        msg="$(clean_err "$dump_out")"; [ -n "$msg" ] || msg="exit $dump_rc"
        echo "Lost connection to Android device${serial:+ at $serial} while inspecting '$app' ($msg)." >&2
        exit 1
      fi
      pm_rc=0
      dump_out="$("${adb_target[@]}" shell pm dump "$app" 2>&1)" || pm_rc=$?
      if [ "$pm_rc" -ne 0 ]; then
        msg="$(clean_err "$dump_out")"; [ -n "$msg" ] || msg="exit $pm_rc"
        echo "Could not inspect declared permissions for '$app' ($msg)." >&2
        exit 1
      fi
    fi
    case "$dump_out" in
      *"Unable to find package:"*)
        echo "App '$app' is not installed on the device (install it first)." >&2
        exit 1 ;;
    esac
    dump_clean="$(printf '%s' "$dump_out" | tr -d '\r')"
    applicable=()
    for perm in \
      android.permission.ACCESS_FINE_LOCATION \
      android.permission.ACCESS_COARSE_LOCATION \
      android.permission.CAMERA \
      android.permission.RECORD_AUDIO \
      android.permission.READ_MEDIA_IMAGES \
      android.permission.POST_NOTIFICATIONS \
      android.permission.READ_CONTACTS ; do
      if printf '%s\n' "$dump_clean" | grep -Eq "(^|[^A-Za-z0-9_.])${perm}([^A-Za-z0-9_.]|$)"; then
        applicable+=("$perm")
      fi
    done
    if [ "${#applicable[@]}" -eq 0 ]; then
      echo "NOTE: app '$app' declares none of the pre-grantable runtime permissions — nothing to grant."
      exit 0
    fi
    for perm in "${applicable[@]}"; do
      rc=0
      err="$("${adb_target[@]}" shell pm grant "$app" "$perm" 2>&1)" || rc=$?
      msg="$(clean_err "$err")"
      if [ "$rc" -eq 0 ] && [[ ! "$msg" =~ (SecurityException|IllegalArgumentException|^Error:|Exception:) ]]; then
        echo "granted: $perm"
        granted=$((granted + 1))
      else
        [ -n "$msg" ] || msg="exit $rc"
        echo "failed: $perm ($msg)" >&2
        failed+=("$perm")
        if ! "${adb_target[@]}" get-state >/dev/null 2>&1; then
          echo "Lost connection to Android device${serial:+ at $serial} while granting $perm ($msg)." >&2
          break
        fi
      fi
    done
    ;;

  *)
    echo "Usage: $0 {ios|android} <app-id> [device|serial]" >&2
    exit 2
    ;;
esac

if [ "${#failed[@]}" -gt 0 ]; then
  echo "Failed permission grants (${#failed[@]}): ${failed[@]+"${failed[*]}"}" >&2
  exit 1
fi
