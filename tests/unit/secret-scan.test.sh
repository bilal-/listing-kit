#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/lib/secret-scan.sh"

# Build a throwaway listing tree per case.
mktree() { new_tempdir TREE; TREE="$TREE/fastlane"; mkdir -p "$TREE/en-US"; }

it "exits 0 on a clean listing tree"
mktree
printf 'My Reading App\n' > "$TREE/en-US/name.txt"
printf 'Read anywhere.\n'  > "$TREE/en-US/description.txt"
OUT="$(bash "$SUT" "$TREE" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" "clean"

it "returns a scan error for a missing explicitly named directory"
OUT="$(bash "$SUT" /no/such/dir 2>&1)"; RC=$?
assert_eq 2 "$RC"

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

it "scans a text asset with a .png extension"
mktree; printf 'AKIAIOSFODNN7EXAMPLE\n' > "$TREE/en-US/01_home.png"
OUT="$(bash "$SUT" "$TREE" 2>&1)"; RC=$?
assert_eq 1 "$RC"

it "a scan error exits 2 instead of reporting clean"
new_tempdir D; echo "harmless copy" > "$D/description.txt"
ln -s loop "$D/loop"
OUT="$(bash "$SUT" "$D" 2>&1)"; RC=$?
assert_eq 2 "$RC"
assert_not_contains "$OUT" "Secret scan clean"
remove_fixture "$D"

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
  "clientSecret: process.env.CLIENT_SECRET" \
  "https://example.test/search?monkeytoken=springlaunch2026" \
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


mktree
for name in Fastfile .env setup.rb config.toml; do
  it "scans listing text in $name"
  printf '%s%s\n' 'ghp_' '0123456789abcdefghijklmnopqrstuvwxyz' > "$TREE/$name"
  OUT="$(bash "$SUT" "$TREE" 2>&1)"; RC=$?
  assert_eq 1 "$RC"
  assert_contains "$OUT" "$name"
  rm "$TREE/$name"
done

for name in .p8 cert.p8 cert.p12 cert.pem cert.key cert.jks cert.keystore demo_password.txt account.json; do
  it "identifies credential file $name"
  case "$name" in
    demo_password.txt) echo 'short' > "$TREE/$name" ;;
    account.json) printf '{"type":\n "service_account"}\n' > "$TREE/$name" ;;
    *) printf '\0' > "$TREE/$name" ;;
  esac
  OUT="$(bash "$SUT" "$TREE" 2>&1)"; RC=$?
  assert_eq 1 "$RC"
  assert_contains "$OUT" "$name"
  rm "$TREE/$name"
done

it "identifies a credential filename even when the file is a symbolic link"
ln -s unavailable "$TREE/upload.keystore"
OUT="$(bash "$SUT" "$TREE" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" 'upload.keystore'
rm "$TREE/upload.keystore"

it "scans unknown bytes, font lookalikes and raw text captures"
mkdir -p "$TREE/nested/.listing-kit/raw"
for file in blob font.woff2 notes.svg nested/.listing-kit/raw/log.txt; do
  printf 'note\0AKIAIOSFODNN7EXAMPLE' > "$TREE/$file"
  OUT="$(bash "$SUT" "$TREE" 2>&1)"; RC=$?
  assert_eq 1 "$RC" "$file is scanned"
  rm "$TREE/$file"
done

it "redacts credentials in path components even for real images"
secret=AKIAIOSFODNN7EXAMPLE
fake_png "$TREE/$secret.png" 20 20
OUT="$(bash "$SUT" "$TREE" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_not_contains "$OUT" "$secret"
rm "$TREE/$secret.png"

it "uses content signatures for genuine media"
fake_png "$TREE/image" 20 20
printf '%s' "$secret" >> "$TREE/image"
OUT="$(bash "$SUT" "$TREE" 2>&1)"; RC=$?
assert_eq 0 "$RC"

it "skips only untracked local settings in a worktree scan"
new_tempdir app
git -C "$app" init -q
mkdir "$app/.listing-kit"
echo 'AKIAIOSFODNN7EXAMPLE' > "$app/.listing-kit/local.json"
bash "$SUT" "$app/.listing-kit" >/dev/null || fail "read untracked private settings"
echo '{}' > "$app/.listing-kit/local.json"
git -C "$app" add -f .listing-kit/local.json
OUT="$(bash "$SUT" "$app/.listing-kit" 2>&1)"; RC=$?
assert_eq 1 "$RC"
assert_contains "$OUT" local.json

for copy in 'Password: 12-character minimum' 'Token: ERC20-compatible wallets' 'Password: auto-generated, synced' 'apiKey: Env.GOOGLE_API_KEY,'; do
  it "permits ordinary copy or reference: $copy"
  echo "$copy" > "$TREE/en-US/description.txt"
  bash "$SUT" "$TREE" >/dev/null 2>&1; assert_eq 0 "$?"
done
for key in 'accessToken=' 'authToken:' 'dbPassword=' 'mypassword='; do
  it "detects credential assignment $key"
  echo "${key}abc123def456ghi789" > "$TREE/en-US/description.txt"
  bash "$SUT" "$TREE" >/dev/null 2>&1; assert_eq 1 "$?"
done
it "ignores components above the scan root and treats credential prefixes case-sensitively"
mkdir -p "$TREE/xoxo-valentines-app/fastlane"
echo 'GHP_0123456789abcdefghijklmnopqrstuvwxyz' > "$TREE/xoxo-valentines-app/fastlane/name"
bash "$SUT" "$TREE/xoxo-valentines-app/fastlane" >/dev/null 2>&1; assert_eq 0 "$?"


it "finds an assignment inside a longer field value"
mktree
echo 'note: accessToken=abc123def456ghi789' > "$TREE/en-US/description.txt"
bash "$SUT" "$TREE" >/dev/null 2>&1; assert_eq 1 "$?"

it "recognizes PDF, Photoshop and preview media by path and signature"
new_tempdir media
python3 - "$media" <<'PYMEDIA'
from pathlib import Path
import sys
for ext, magic in (("pdf", b"%PDF-1.7"), ("psd", b"8BPS\0\1" + b"\0"*6),
                   ("mp4", b"\0\0\0\x18ftypisom"), ("mov", b"\0\0\0\x18ftypqt  ")):
    (Path(sys.argv[1]) / ("asset." + ext)).write_bytes(magic + b"\0AKIAIOSFODNN7EXAMPLE")
PYMEDIA
bash "$SUT" "$media" >/dev/null 2>&1; assert_eq 0 "$?"
echo 'AKIAIOSFODNN7EXAMPLE' > "$media/plain.mp4"
bash "$SUT" "$media" >/dev/null 2>&1; assert_eq 1 "$?"

summary
