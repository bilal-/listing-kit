#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
SUT="$SCRIPTS/doctor/iphone-duo.py"
PYTHON="$(command -v python3)"
T="$(mktemp -d)"
export DUO_FIXTURES="$T" DUO_SDK=27.1 DUO_FAIL=0
new_stubdir
cat > "$STUB_BIN/xcrun" <<'SH'
#!/usr/bin/env bash
[ "$DUO_FAIL" = 0 ] || exit 1
case "$*" in
  '--sdk iphonesimulator --show-sdk-version') printf '%s\n' "$DUO_SDK" ;;
  'simctl list --json devicetypes') cat "$DUO_FIXTURES/types.json" ;;
  'simctl list --json runtimes') cat "$DUO_FIXTURES/runtimes.json" ;;
  *) exit 99 ;; # The preflight must never install, boot or mutate anything.
esac
SH
chmod +x "$STUB_BIN/xcrun"
types() { printf '%s\n' '{"devicetypes":[{"identifier":"com.apple.CoreSimulator.SimDeviceType.iPhone-Duo","minRuntimeVersionString":"27.1.0","maxRuntimeVersionString":"27.9.0"}]}' > "$T/types.json"; }
runtimes() { printf '%s\n' '{"runtimes":[{"identifier":"com.apple.CoreSimulator.SimRuntime.iOS-27-1","version":"27.1","isAvailable":true}]}' > "$T/runtimes.json"; }
probe() { PATH="$STUB_BIN:$PATH" "$PYTHON" "$SUT"; }
types; runtimes

it 'missing Xcode gracefully defers without a traceback'
OUT="$(PATH="$T" "$PYTHON" "$SUT" 2>&1)"; RC=$?
assert_eq 3 "$RC"
assert_contains "$OUT" '"status": "deferred"'
assert_not_contains "$OUT" Traceback

it 'Xcode 27.0 SDK does not qualify Duo'
export DUO_SDK=27.0
OUT="$(probe)"; RC=$?
assert_eq 3 "$RC"
assert_contains "$OUT" 'needs 27.1+'

it 'new SDK still needs the Duo device type'
export DUO_SDK=27.1
printf '%s\n' '{"devicetypes":[]}' > "$T/types.json"
OUT="$(probe)"; RC=$?
assert_eq 3 "$RC"
assert_contains "$OUT" 'device type'
types

it 'new SDK and device still need an installed compatible runtime'
for fixture in \
  '{"runtimes":[]}' \
  '{"runtimes":[{"identifier":"com.apple.CoreSimulator.SimRuntime.iOS-27-1","version":"27.1","isAvailable":false}]}' \
  '{"runtimes":[{"identifier":"com.apple.CoreSimulator.SimRuntime.iOS-27-0","version":"27.0","isAvailable":true}]}' \
  '{"runtimes":[{"identifier":"com.apple.CoreSimulator.SimRuntime.tvOS-27-1","version":"27.1","isAvailable":true}]}' \
  '{"runtimes":[{"identifier":"com.apple.CoreSimulator.SimRuntime.iOS-28-0","version":"28.0","isAvailable":true}]}'; do
  printf '%s\n' "$fixture" > "$T/runtimes.json"
  OUT="$(probe)"; RC=$?
  assert_eq 3 "$RC"
done
runtimes

it 'SDK, device and available compatible runtime produce a ready result'
OUT="$(probe)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" '"status": "ready"'
assert_contains "$OUT" '"runtime": "com.apple.CoreSimulator.SimRuntime.iOS-27-1"'

it 'simctl failure and malformed output defer clearly'
export DUO_FAIL=1
OUT="$(probe)"; RC=$?
assert_eq 3 "$RC"
assert_contains "$OUT" 'Could not verify'
export DUO_FAIL=0
for malformed in broken '{"runtimes":[1]}'; do
  printf '%s\n' "$malformed" > "$T/runtimes.json"
  OUT="$(probe)"; RC=$?
  assert_eq 3 "$RC"
  assert_not_contains "$OUT" Traceback
done

rm -r "$T"
summary
