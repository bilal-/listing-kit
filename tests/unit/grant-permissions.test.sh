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
assert_contains "$LOG" "simctl terminate booted com.example.app" "stops the app before granting"

it "ios: warns that camera/ATT cannot be pre-granted"
assert_contains "$OUT" "camera"

it "ios: fails clearly when the app isn't installed on the simulator"
new_stubdir
cat > "$STUB_BIN/xcrun" <<'EOF'
#!/usr/bin/env bash
case "$*" in *get_app_container*) exit 2;; esac
exit 0
EOF
chmod +x "$STUB_BIN/xcrun"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" ios com.example.app 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "not found on simulator"

it "ios: skips services simctl reports as unsupported and succeeds when applicable ones succeed"
new_stubdir
cat > "$STUB_BIN/xcrun" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *"grant photos "*|*"grant contacts "*) exit 0;;
  *"privacy"*"grant"*) echo "Unsupported service on this runtime" >&2; exit 1;;
esac
exit 0
EOF
chmod +x "$STUB_BIN/xcrun"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" ios com.example.app booted 2>&1)"; RC=$?
assert_eq 0 "$RC" "exits 0 when unsupported services are skipped and applicable grants succeed"
assert_contains "$OUT" "granted: photos"
assert_contains "$OUT" "granted: contacts"

it "ios: succeeds with a note when simctl reports every service as unsupported"
new_stubdir
cat > "$STUB_BIN/xcrun" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *"privacy"*"grant"*) echo "Invalid service for runtime" >&2; exit 1;;
esac
exit 0
EOF
chmod +x "$STUB_BIN/xcrun"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" ios com.example.app booted 2>&1)"; RC=$?
assert_eq 0 "$RC" "none applicable on iOS exits 0"
assert_contains "$OUT" "none"

it "ios: exits non-zero if any applicable grant fails and names which failed"
new_stubdir
cat > "$STUB_BIN/xcrun" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *"grant location-always "*) exit 0;;
  *"grant photos "*) echo "An error was encountered processing the command: Operation not permitted" >&2; exit 1;;
  *"privacy"*"grant"*) exit 0;;
esac
exit 0
EOF
chmod +x "$STUB_BIN/xcrun"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" ios com.example.app booted 2>&1)"; RC=$?
assert_ne 0 "$RC" "partial applicable iOS failure exits non-zero"
assert_contains "$OUT" "Operation not permitted"
assert_contains "$OUT" "photos"

it "ios: lost simulator mid-run is an error even after an earlier grant succeeded"
new_stubdir
STATE_FILE="$STUB_BIN/.alive"; echo 1 > "$STATE_FILE"
cat > "$STUB_BIN/xcrun" <<EOF
#!/usr/bin/env bash
case "\$*" in
  *get_app_container*) [ "\$(cat "$STATE_FILE")" = 1 ] && exit 0 || exit 1;;
  *"grant location-always "*) echo 0 > "$STATE_FILE"; exit 0;;
  *"privacy"*"grant"*) echo "Unable to lookup in current state: Shutdown" >&2; exit 1;;
esac
exit 0
EOF
chmod +x "$STUB_BIN/xcrun"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" ios com.example.app booted 2>&1)"; RC=$?
assert_ne 0 "$RC" "lost simulator exits non-zero"
assert_contains "$OUT" "photos"

# --- Android path (stub adb) ---
it "android: fails clearly when no device is reachable"
new_stubdir; stub adb 1
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" android com.example.app 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "No Android device"

it "android: fails clearly when the app isn't installed"
new_stubdir
cat > "$STUB_BIN/adb" <<'EOF'
#!/usr/bin/env bash
case "$*" in *"pm path"*) exit 1;; esac
exit 0
EOF
chmod +x "$STUB_BIN/adb"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" android com.example.app 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" "not installed"

it "android: grants only declared runtime permissions from dumpsys package"
new_stubdir
cat > "$STUB_BIN/adb" <<EOF
#!/usr/bin/env bash
echo "adb \$*" >> "$STUB_LOG"
case "\$*" in
  *"dumpsys package com.example.app"*)
    cat <<'DUMP'
Packages:
  Package [com.example.app] (1234abcd):
    requested permissions:
      android.permission.INTERNET
      android.permission.CAMERA
      android.permission.ACCESS_FINE_LOCATION: restricted=true
    install permissions:
      android.permission.READ_CONTACTS: granted=true
DUMP
      awk 'BEGIN {for(i=0;i<16000;i++) print "additional package information"}' 
    exit 0;;
esac
exit 0
EOF
chmod +x "$STUB_BIN/adb"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" android com.example.app 2>&1)"; RC=$?
LOG="$(stub_log)"
assert_eq 0 "$RC" "android exits 0 when declared grants succeed"
assert_eq 1 "$(printf '%s\n' "$LOG" | grep -c 'dumpsys package')" "one package inspection"
assert_contains "$LOG" "shell pm grant com.example.app android.permission.CAMERA"
assert_contains "$LOG" "shell pm grant com.example.app android.permission.ACCESS_FINE_LOCATION"
assert_not_contains "$LOG" "pm grant com.example.app android.permission.READ_CONTACTS" "undeclared permission skipped"

it "android: succeeds with a note when the installed app declares none of the permissions"
new_stubdir
cat > "$STUB_BIN/adb" <<EOF
#!/usr/bin/env bash
echo "adb \$*" >> "$STUB_LOG"
case "\$*" in
  *"dumpsys package com.example.app"*)
    printf 'Packages:\n  Package [com.example.app]:\n    requested permissions:\n      android.permission.INTERNET\n    runtime permissions:\n      android.permission.CAMERA: granted=false\n'
    exit 0;;
esac
exit 0
EOF
chmod +x "$STUB_BIN/adb"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" android com.example.app 2>&1)"; RC=$?
LOG="$(stub_log)"
assert_eq 0 "$RC" "none applicable on Android exits 0"
assert_contains "$OUT" "none"
assert_not_contains "$LOG" "pm grant" "no pm grant attempted"

it "android: exits non-zero if any applicable grant fails and names which failed"
new_stubdir
cat > "$STUB_BIN/adb" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *"dumpsys package"*)
    printf '    requested permissions:\n      android.permission.CAMERA\n      android.permission.RECORD_AUDIO\n'
    exit 0;;
  *"pm grant"*"CAMERA"*) exit 0;;
  *"pm grant"*"RECORD_AUDIO"*)
    echo "SecurityException: Permission is not a changeable permission type" >&2
    exit 1;;
esac
exit 0
EOF
chmod +x "$STUB_BIN/adb"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" android com.example.app 2>&1)"; RC=$?
assert_ne 0 "$RC" "partial applicable Android failure exits non-zero"
assert_contains "$OUT" "granted: android.permission.CAMERA"
assert_contains "$OUT" "SecurityException: Permission is not a changeable permission type"
assert_contains "$OUT" "android.permission.RECORD_AUDIO"

it "android: lost device mid-run fails with an error even after an earlier grant succeeded"
new_stubdir
ADB_ALIVE="$STUB_BIN/.adb_alive"; echo 1 > "$ADB_ALIVE"
cat > "$STUB_BIN/adb" <<EOF
#!/usr/bin/env bash
case "\$*" in
  *get-state*) [ "\$(cat "$ADB_ALIVE")" = 1 ] && { echo device; exit 0; } || { echo "adb: no devices/emulators found" >&2; exit 1; };;
  *"dumpsys package"*)
    printf '    requested permissions:\n      android.permission.CAMERA\n      android.permission.POST_NOTIFICATIONS\n'
    exit 0;;
  *"pm grant"*"CAMERA"*) echo 0 > "$ADB_ALIVE"; exit 0;;
  *"pm grant"*) echo "adb: error: failed to get feature set: device offline" >&2; exit 1;;
esac
exit 0
EOF
chmod +x "$STUB_BIN/adb"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" android com.example.app 2>&1)"; RC=$?
assert_ne 0 "$RC" "lost Android device exits non-zero"
assert_contains "$OUT" "device offline"
assert_contains "$OUT" "android.permission.POST_NOTIFICATIONS"

summary
