#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
unset LISTING_KIT_HOME
installer="$SCRIPTS/package/install-review-hook.sh"
fixture() {
  new_tempdir repo
  git -C "$repo" init -q
  git -C "$repo" config user.name Tester
  git -C "$repo" config user.email test@example.test
  bash "$installer" "$repo" >/dev/null || exit 1
}
stage() {
  mkdir -p "$repo/$(dirname "$1")"
  printf '%s\n' "$2" > "$repo/$1"
  git -C "$repo" add -- "$1"
}
run_hook() { (cd "$repo" && .git/hooks/pre-commit); }
credential='AKIA''IOSFODNN7EXAMPLE'

it "scans assignment fallbacks and permits store prose and symbolic references"
python3 -I -B - "$SCRIPTS/lib" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from secret_scan import secret_text
clean = [
    'Password: autocomplete, autofill, sync', 'Password: synchronization',
    'Password: customizable.', 'Password: 128-bit-encrypted vault team',
    'One-time-password: configurable, offline',
    'A standard-bearer non-tracking-privacy-first browser',
    'https://example.com/legal/sk-privacy-policy-2026-update',
    'https://mysite.example/sk-ochrana-osobnych-udajov',
    '01_home-sk-SK-iphone-dynamic-island.png',
    'apiKey: import.meta.env.VITE_API_KEY', 'clientSecret: Constants.expoConfig.extra.clientSecret,',
    'clientSecret: config.clientSecret,', 'MAPS_API_KEY = DEFAULT_MAPS_KEY;',
    'password: process.env.X ?? config.defaultPassword',
]
secret = [
    'password: process.env.X || "s3cr3tDemoPass999"',
    "clientSecret: process.env.CLIENT_SECRET ?? 's3cr3tDemoPass999'",
    'password: process.env.X ?? config.value || "hardcodedfallback"',
    'clientSecret: abcdef.one+two3456789', 'apiKey: hardcodedcredential',
    'password: process.env.USE_KEY ? config.value : "s3cr3tDemoPass999"',
    'clientSecret: "config.clientSecret"', 'password: "synchronization"',
]
wrong = [item for item in clean if secret_text(item.encode())]
wrong += [item for item in secret if not secret_text(item.encode())]
assert not wrong, wrong
PY
assert_eq 0 "$?"

it "honors core.ignorecase for trigger, index scan and private settings"
for path in Fastlane/name Store-Assets/name .Listing-Kit/plan App.json ios/info.plist .Listing-Kit/LOCAL.JSON; do
  fixture
  git -C "$repo" config core.ignorecase true
  stage "$path" "$credential"
  if [ "$path" = .Listing-Kit/LOCAL.JSON ]; then stage "$path" '{}'; fi
  out="$(run_hook 2>&1)"; assert_ne 0 "$?" "$path"; assert_contains "$out" 'POTENTIAL SECRET'
  git -C "$repo" config core.ignorecase false
  out="$(run_hook 2>&1)"; assert_eq 0 "$?" "$path case sensitive"
done
fixture
git -C "$repo" config core.ignorecase true
stage Fastlane/name "$credential"
git -C "$repo" commit -qm bypass --no-verify
stage app.json '{}'
out="$(run_hook 2>&1)"; assert_ne 0 "$?" 'unchanged mixed-case listing blob'

it "case-folded symlink aliases retain the demo password policy"
fixture
git -C "$repo" config core.ignorecase true
stage Fastlane/target "ordinary text"
ln -s TARGET "$repo/Fastlane/DEMO_PASSWORD.TXT"
git -C "$repo" add Fastlane
out="$(run_hook 2>&1)"; assert_ne 0 "$?"

it "amend scans the proposed tree against its parent, including root commits"
for root in yes no; do
  fixture
  if [ "$root" = no ]; then git -C "$repo" commit -qm base --allow-empty; fi
  stage fastlane/metadata/en-US/description.txt "$credential"
  git -C "$repo" commit --no-verify -qm bypass
  stage README ordinary
  out="$(git -C "$repo" commit -qm recheck --amend 2>&1)"
  assert_ne 0 "$?" "amend (root=$root)"; assert_contains "$out" 'POTENTIAL SECRET'
  out="$(git -C "$repo" commit -qm 'message mentioning --amend only' 2>&1)"
  assert_eq 0 "$?" "ordinary commit (root=$root)"
done
fixture
stage fastlane/metadata/en-US/description.txt 'Amended listing'
git -C "$repo" commit --no-verify -qm stale
git -C "$repo" commit --amend --no-edit -q
assert_contains "$(git -C "$repo" show HEAD:listing-review.html 2>/dev/null)" 'Amended listing'

it "an unusable python cannot block a commit outside listing scope"
fixture
new_stubdir
stub python3 42
stage README unrelated
out="$(PATH="$STUB_BIN:$PATH" run_hook 2>&1)"; assert_eq 0 "$?"

stage fastlane/key "$credential"
git -C "$repo" commit --no-verify -qm bypass
stage README ordinary
out="$(PATH="$STUB_BIN:$PATH" git -C "$repo" commit -qm recheck --amend 2>&1)"; assert_ne 0 "$?" 'amend requires a working scanner'

it "a message mentioning --amend is unrelated even without python3 on PATH"
fixture
stage fastlane/key "$credential"
git -C "$repo" commit --no-verify -qm bypass
new_stubdir
for cmd in bash git; do ln -s "$(command -v "$cmd")" "$STUB_BIN/$cmd"; done
stage README ordinary
out="$(PATH="$STUB_BIN" git -C "$repo" commit -qm 'what --amend does' 2>&1)"; assert_eq 0 "$?"
git -C "$repo" reset --soft HEAD^ || exit 1
out="$(PATH="$STUB_BIN" git -C "$repo" commit -qm recheck --amend 2>&1)"; assert_ne 0 "$?"; assert_contains "$out" python3

it "vendor and build device files are outside the listing scope"
fixture
for path in ios/Pods/X/project.pbxproj ios/build/Info.plist ios/Foo.framework/Info.plist libs/Foo.xcframework/Info.plist; do
  stage "$path" "$credential"
done
out="$(run_hook 2>&1)"; assert_eq 0 "$?"
stage fastlane/metadata/en-US/name.txt 'Clean listing'
out="$(run_hook 2>&1)"; assert_eq 0 "$?"
stage ios/App/Info.plist "$credential"
out="$(run_hook 2>&1)"; assert_ne 0 "$?"

it "partial listing commits cannot leave a staged page rollback"
fixture
file=fastlane/metadata/en-US/description.txt
stage "$file" VersionOne
git -C "$repo" commit -qm initial
stage "$file" VersionTwo
out="$(git -C "$repo" commit -qm partial -- "$file" 2>&1)"; assert_eq 0 "$?"
assert_eq "$(git -C "$repo" rev-parse HEAD:listing-review.html)" "$(git -C "$repo" rev-parse :listing-review.html)"
stage "$file" "$credential"
out="$(git -C "$repo" commit -qm partial -- "$file" 2>&1)"; assert_ne 0 "$?"

it "CRLF and sparse checkout refresh problems allow a clean commit"
fixture
git -C "$repo" config core.autocrlf true
git -C "$repo" config core.safecrlf true
mkdir -p "$repo/fastlane/metadata/en-US" "$repo/ios"
printf 'first\r\n' > "$repo/fastlane/metadata/en-US/name.txt"
printf 'app\r\n' > "$repo/ios/Info.plist"
git -C "$repo" add fastlane ios
out="$(git -C "$repo" commit -qm first 2>&1)"; assert_eq 0 "$?"
git -C "$repo" sparse-checkout init --no-cone
git -C "$repo" sparse-checkout set --no-cone '/ios/*'
printf 'change\r\n' > "$repo/ios/Info.plist"
git -C "$repo" add ios
out="$(git -C "$repo" commit -qm sparse 2>&1)"; assert_eq 0 "$?"

it "a symlinked registered app parent cannot redirect page installation"
fixture
mkdir "$repo/mobile"
bash "$installer" "$repo/mobile" >/dev/null
stage mobile/fastlane/metadata/en-US/description.txt clean
new_tempdir other
echo sentinel > "$other/listing-review.html"
mv "$repo/mobile" "$repo/original"
ln -s "$other" "$repo/mobile"
out="$(run_hook 2>&1)"; assert_eq 0 "$?"
assert_eq sentinel "$(cat "$other/listing-review.html")"
assert_contains "$out" Warning

it "recognizes CRLF manager hooks and registers Unicode apps once across locales"
fixture
mkdir -p "$repo/.husky/_" "$repo/apps/café"
touch "$repo/.husky/_/h"
git -C "$repo" config core.hooksPath .husky/_
printf '#!/bin/sh\n' > "$repo/.husky/_/pre-commit"; chmod +x "$repo/.husky/_/pre-commit"
tr -d '\r' < "$repo/.git/hooks/pre-commit" | sed $'s/$/\r/' > "$repo/.husky/pre-commit"
LC_ALL=en_US.UTF-8 bash "$installer" "$repo/apps/café" >/dev/null
out="$(LC_ALL=C bash "$installer" --status "$repo/apps/café" 2>&1)"; assert_eq 0 "$?" "$out"
LC_ALL=C bash "$installer" "$repo/apps/café" >/dev/null
assert_eq 2 "$(grep -c '^apps+=' "$repo/.git/listing-kit-review")"

it "upgrades app entries quoted by an earlier UTF-8 installer"
python3 - "$repo/.git/listing-kit-review" <<'PYREG'
from pathlib import Path
import sys
runner = Path(sys.argv[1])
lines = runner.read_bytes().splitlines(keepends=True)
runner.write_bytes(b"".join("apps+=(apps/café)\n".encode() if line.startswith(b"apps+=($") else line for line in lines))
PYREG
LC_ALL=C bash "$installer" "$repo/apps/café" >/dev/null
assert_eq 2 "$(grep -c '^apps+=' "$repo/.git/listing-kit-review")"

it "validation batches copy and image reads across locales"
new_tempdir app
new_stubdir
py="$(command -v python3)"
cat > "$STUB_BIN/python3" <<'STUB'
#!/bin/sh
echo "$*" >> "$LK_CALLS"
exec "$LK_PYTHON" "$@"
STUB
chmod +x "$STUB_BIN/python3"
for loc in en-US de-DE fr-FR; do
  mkdir -p "$app/fastlane/metadata/$loc"
  echo name > "$app/fastlane/metadata/$loc/name.txt"
  fake_png "$app/fastlane/screenshots/$loc/01.png" 1206 2622
done
out="$(LK_PYTHON="$py" LK_CALLS="$STUB_LOG" PATH="$STUB_BIN:$PATH" bash "$SCRIPTS/validate/validate-listing.sh" "$app" 2>&1)"
assert_contains "$out" 'iPhone Dynamic Island (medium display) screenshots present'
for script in fields imginfo; do
  count="$(grep -c "/$script.py" "$STUB_LOG")"
  [ "$count" -le 1 ] && pass || fail "$count $script processes for three locales"
done

summary
