#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/capture/sanitize-status-bar.sh"

it "exits 2 on unknown platform"
OUT="$(bash "$SUT" bogus 2>&1)"; RC=$?
assert_eq 2 "$RC"

it "exits 2 with no platform"
OUT="$(bash "$SUT" 2>&1)"; RC=$?
assert_eq 2 "$RC"

# --- iOS path (stub xcrun) ---
new_stubdir; stub xcrun
it "ios: overrides status bar to 9:41, full battery/signal via simctl"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" ios booted 2>&1)"; RC=$?
LOG="$(stub_log)"
assert_eq 0 "$RC" "ios exits 0"
assert_contains "$LOG" "simctl status_bar booted override"
assert_contains "$LOG" "9:41"
assert_contains "$LOG" "batteryLevel 100"
assert_contains "$LOG" "batteryState discharging" "full battery without the charging bolt"

it "ios: defaults device to 'booted' when omitted"
new_stubdir; stub xcrun
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" ios 2>&1)"; RC=$?
assert_contains "$(stub_log)" "status_bar booted override"

# --- Android path (stub adb) — must use demo mode, not plain settings ---
new_stubdir; stub adb
it "android: enables demo mode and sets a clean status bar via broadcasts"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" android 2>&1)"; RC=$?
LOG="$(stub_log)"
assert_eq 0 "$RC" "android exits 0"
assert_contains "$LOG" "settings put global sysui_demo_allowed 1"
assert_contains "$LOG" "com.android.systemui.demo"
assert_contains "$LOG" "hhmm 0941"
assert_contains "$LOG" "level 100"

it "android: wifi-only status bar with system icons hidden"
assert_contains "$LOG" "-e mobile hide"
assert_contains "$LOG" "-e wifi show -e level 4 -e fully true"
assert_contains "$LOG" "command status -e location hide"

it "android: snoozes posted notifications only on an emulator"
new_stubdir
cat > "$STUB_BIN/adb" <<'EOF'
#!/usr/bin/env bash
echo "adb $*" >> "$(dirname "$0")/.calls"
case "$*" in
  *"getprop ro.kernel.qemu"*) echo 1;;
  *"dumpsys notification"*) echo "NotificationRecord(0x1: pkg=android user=UserHandle{0} id=7 tag=null importance=2 key=0|android|7|null|1000: Notification(x)";;
esac
EOF
chmod +x "$STUB_BIN/adb"
PATH="$STUB_BIN:$PATH" bash "$SUT" android >/dev/null 2>&1
assert_contains "$(stub_log)" "cmd notification snooze --for 3600000 '0|android|7|null|1000'"

it "android: leaves a physical device's notifications alone"
new_stubdir; stub adb
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" android 2>&1)"
assert_not_contains "$(stub_log)" "snooze"
assert_contains "$OUT" "not an emulator"

it "android: an emulator with no notifications still succeeds"
new_stubdir
cat > "$STUB_BIN/adb" <<'EOF'
#!/usr/bin/env bash
echo "adb $*" >> "$(dirname "$0")/.calls"
case "$*" in *"getprop ro.kernel.qemu"*) echo 1;; esac
EOF
chmod +x "$STUB_BIN/adb"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" android 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" "sanitized via demo mode"

summary
