#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/lib/secret-scan.sh"

# Build a throwaway listing tree per case.
mktree() { TREE="$(mktemp -d)/fastlane"; mkdir -p "$TREE/en-US"; }

it "exits 0 on a clean listing tree"
mktree
printf 'My Reading App\n' > "$TREE/en-US/name.txt"
printf 'Read anywhere.\n'  > "$TREE/en-US/description.txt"
OUT="$(bash "$SUT" "$TREE" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" "clean"

it "exits 0 (not an error) when the directory does not exist"
OUT="$(bash "$SUT" /no/such/dir 2>&1)"; RC=$?
assert_eq 0 "$RC"

it "fails on an AWS access key id"
mktree; printf 'AKIAIOSFODNN7EXAMPLE\n' > "$TREE/en-US/keywords.txt"
OUT="$(bash "$SUT" "$TREE" 2>&1)"; RC=$?
assert_eq 1 "$RC"

it "fails on a GitHub personal access token"
mktree; printf 'token: ghp_0123456789abcdefghijklmnopqrstuvwxyz\n' > "$TREE/en-US/release_notes.txt"
OUT="$(bash "$SUT" "$TREE" 2>&1)"; RC=$?
assert_eq 1 "$RC"

it "fails on a private key block"
mktree; printf -- '-----BEGIN RSA PRIVATE KEY-----\nabc\n' > "$TREE/en-US/notes.md"
OUT="$(bash "$SUT" "$TREE" 2>&1)"; RC=$?
assert_eq 1 "$RC"

it "fails on a generic api_key=... assignment"
mktree; printf 'api_key=sk_live_0123456789abcdef0123\n' > "$TREE/en-US/subtitle.txt"
OUT="$(bash "$SUT" "$TREE" 2>&1)"; RC=$?
assert_eq 1 "$RC"

it "reports which file leaked"
assert_contains "$OUT" "subtitle.txt"

it "ignores non-listing file types (e.g. .png)"
mktree; printf 'AKIAIOSFODNN7EXAMPLE\n' > "$TREE/en-US/01_home.png"
OUT="$(bash "$SUT" "$TREE" 2>&1)"; RC=$?
assert_eq 0 "$RC" "binary/screenshot files are not scanned for copy secrets"

it "a scan error exits 2 instead of reporting clean"
D="$(mktemp -d)"; echo "harmless copy" > "$D/description.txt"
new_stubdir
printf '#!/usr/bin/env bash\nexit 2\n' > "$STUB_BIN/grep"; chmod +x "$STUB_BIN/grep"
OUT="$(PATH="$STUB_BIN:$PATH" bash "$SUT" "$D" 2>&1)"; RC=$?
assert_eq 2 "$RC"
assert_not_contains "$OUT" "Secret scan clean"
rm -rf "$D"

# --- current credential formats (each on its own line, no "token:" keyword) ---
# Fixtures are split into two literals and joined by the shell, so this file never
# contains a token-shaped string (GitHub push protection rejects those, even fakes).
for k in \
  "sk-""proj-Ab3dEf6hIj9kLm2nOp5qRs8tUv1wXy4z" \
  "sk-""ant-api03-Ab3dEf6hIj9kLm2nOp5qRs8tUv1wXy4zAb3dEf" \
  "sk_""live_51Hab3dEf6hIj9kLm2nOp5qRs" \
  "rk_""test_51Hab3dEf6hIj9kLm2nOp5qRs" \
  "eyJ""hbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U" \
  '"private_key''_id": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"' \
  "ghs""_Ab3dEf6hIj9kLm2nOp5qRs8tUv1wXy4zAb3d" \
  "glpat""-Ab3dEf6hIj9kLm2nOp5q" \
  "ASIA""IOSFODNN7EXAMPLE" \
  "ghs""_123456_Ab3dEf6hIj9kLm2nOp5qRs8tUv1wXy4zAb3dEf_Ab" \
  "xapp""-1-A0123456789-0123456789-abcdef0123" \
  "xoxe""-1-Ab3dEf6hIj9kLm2nOp5q" \
  "whsec""_Ab3dEf6hIj9kLm2nOp5qRs8tUv1" \
  "ey""IHsiYWxnIjoi.eyAic3ViIjog.abcdefghijkl" \
  "api_key""=abc123def456ghi==" \
  "DB_PASSWORD: s3cr3t""Value99xx" \
  "password: CorrectHorse""BatteryStaple" \
  "token=abcdefghijkl""mnopqrstuvwxyz" \
  "Authorization: Bearer abcdef12345""67890abcdef"; do
  it "fails on ${k:0:16}…"
  mktree; printf '%s\n' "$k" > "$TREE/en-US/description.txt"
  OUT="$(bash "$SUT" "$TREE" 2>&1)"; RC=$?
  assert_eq 1 "$RC"
done

# --- ordinary store copy must not trip the token patterns ---
for c in \
  "The best task-management-for-every-busy-family app" \
  "Use our desk-organizer-and-planner-for-students-and-teachers" \
  "Track your password strength" \
  "Tokens of appreciation: share recipes" \
  "Password synchronization across devices" \
  "Password: synchronization made easy" \
  "Plan trips at https://asiatraveladventures.example today"; do
  it "store copy is clean: ${c:0:28}…"
  mktree; printf '%s\n' "$c" > "$TREE/en-US/description.txt"
  OUT="$(bash "$SUT" "$TREE" 2>&1)"; RC=$?
  assert_eq 0 "$RC"
done

it "scans an explicitly selected public JSON file"
mktree
printf '%s\n' '{"note":"No runtime"}' > "$TREE/asset-plan.json"
OUT="$(bash "$SUT" "$TREE/asset-plan.json" 2>&1)"; RC=$?
assert_eq 0 "$RC"
printf '%s%s\n' 'ghp_' '0123456789abcdefghijklmnopqrstuvwxyz' > "$TREE/asset-plan.json"
OUT="$(bash "$SUT" "$TREE/asset-plan.json" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" 'POTENTIAL SECRET'

summary
