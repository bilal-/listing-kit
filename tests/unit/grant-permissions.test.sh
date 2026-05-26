#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/capture/grant-permissions.sh"

it "exits 2 with no args"
OUT="$(bash "$SUT" 2>&1)"; RC=$?
assert_eq 2 "$RC"

it "exits 2 with platform but no app id"
OUT="$(bash "$SUT" ios 2>&1)"; RC=$?
assert_eq 2 "$RC"

it "exits 2 on unknown platform"
OUT="$(bash "$SUT" windows com.x 2>&1)"; RC=$?
assert_eq 2 "$RC"

# --- iOS path (stub xcrun) ---
new_stubdir; stub xcrun
it "ios: grants supported privacy services via simctl"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" ios com.example.app booted 2>&1)"; RC=$?
LOG="$(stub_log)"
assert_eq 0 "$RC" "ios exits 0"
assert_contains "$LOG" "simctl privacy booted grant location-always com.example.app"
assert_contains "$LOG" "grant photos com.example.app"

it "ios: warns that camera/ATT cannot be pre-granted"
assert_contains "$OUT" "camera"

# --- Android path (stub adb) ---
new_stubdir; stub adb
it "android: grants runtime permissions via pm grant"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" android com.example.app 2>&1)"; RC=$?
LOG="$(stub_log)"
assert_eq 0 "$RC" "android exits 0"
assert_contains "$LOG" "shell pm grant com.example.app android.permission.CAMERA"
assert_contains "$LOG" "android.permission.ACCESS_FINE_LOCATION"

summary
