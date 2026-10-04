#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/package/install-review-hook.sh"

make_app() {
  T="$(mktemp -d)"
  git -C "$T" init >/dev/null
  git -C "$T" config user.email "listing-kit@example.test"
  git -C "$T" config user.name "listing-kit test"
  mkdir -p "$T/fastlane/metadata/en-US"
  printf 'Hook Test\n' > "$T/fastlane/metadata/en-US/name.txt"
  printf '%s\n' "$1" > "$T/fastlane/metadata/en-US/description.txt"
}

it "exits 2 outside a git worktree"
T="$(mktemp -d)"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 2 "$RC"
assert_contains "$OUT" "Not inside a git worktree"
rm -rf "$T"

it "installs a pre-commit hook"
make_app "Initial description"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_exec "$T/.git/hooks/pre-commit"
rm -rf "$T"

it "refreshes and stages listing-review.html when fastlane metadata is committed"
make_app "Initial description"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane
git -C "$T" commit -m "initial listing" >/dev/null
assert_contains "$(git -C "$T" show HEAD:listing-review.html)" "Initial description"

printf 'Updated description from hook\n' > "$T/fastlane/metadata/en-US/description.txt"
git -C "$T" add fastlane/metadata/en-US/description.txt
git -C "$T" commit -m "update listing copy" >/dev/null
assert_contains "$(git -C "$T" show HEAD:listing-review.html)" "Updated description from hook"
rm -rf "$T"

it "supports app roots below the git worktree root"
T="$(mktemp -d)"
git -C "$T" init >/dev/null
git -C "$T" config user.email "listing-kit@example.test"
git -C "$T" config user.name "listing-kit test"
mkdir -p "$T/apps/mobile/fastlane/metadata/en-US"
printf 'Nested Hook Test\n' > "$T/apps/mobile/fastlane/metadata/en-US/name.txt"
printf 'Nested description\n' > "$T/apps/mobile/fastlane/metadata/en-US/description.txt"
bash "$SUT" "$T/apps/mobile" >/dev/null
git -C "$T" add apps/mobile/fastlane
git -C "$T" commit -m "nested listing" >/dev/null
assert_contains "$(git -C "$T" show HEAD:apps/mobile/listing-review.html)" "Nested description"
rm -rf "$T"

it "installs into the shared hooks dir from a linked worktree"
make_app "Worktree description"
git -C "$T" add fastlane && git -C "$T" commit -qm "initial listing"
WT="$(mktemp -d)/wt"
git -C "$T" worktree add -q "$WT"
bash "$SUT" "$WT" >/dev/null
assert_exec "$T/.git/hooks/pre-commit"
printf 'Worktree update\n' > "$WT/fastlane/metadata/en-US/description.txt"
git -C "$WT" commit -qam "update from worktree" >/dev/null
assert_contains "$(git -C "$WT" show HEAD:listing-review.html)" "Worktree update"
rm -rf "$T" "$(dirname "$WT")"

it "honors core.hooksPath"
make_app "Hooks path description"
git -C "$T" config core.hooksPath .husky
bash "$SUT" "$T" >/dev/null
assert_exec "$T/.husky/pre-commit"
rm -rf "$T"

it "rerunning does not duplicate the hook call or the app entry"
make_app "Idempotent"
bash "$SUT" "$T" >/dev/null
bash "$SUT" "$T" >/dev/null
assert_eq 1 "$(grep -c 'listing-kit review refresh' "$T/.git/hooks/pre-commit")" "one call line"
assert_eq 1 "$(grep -c '^apps+=' "$T/.git/hooks/listing-kit-review")" "one app entry"
rm -rf "$T"

it "a stale build-review path warns instead of blocking the commit"
make_app "Stale path"
bash "$SUT" "$T" >/dev/null
sed -i.bak 's#^build_review=.*#build_review=/no/such/build-review.sh#' "$T/.git/hooks/listing-kit-review"
git -C "$T" add fastlane
OUT="$(git -C "$T" commit -m "listing" 2>&1)"; RC=$?
assert_eq 0 "$RC" "commit still succeeds"
assert_contains "$OUT" "not refreshed"
rm -rf "$T"

# --- existing hooks keep their contract ---
it "an existing failing shell hook still blocks the commit"
make_app "Existing hook"
printf '#!/bin/sh\necho "lint failed" >&2\nfalse\n' > "$T/.git/hooks/pre-commit"; chmod +x "$T/.git/hooks/pre-commit"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane
OUT="$(git -C "$T" commit -m "listing" 2>&1)"; RC=$?
assert_ne 0 "$RC" "commit is still rejected"
assert_contains "$OUT" "lint failed"
rm -rf "$T"

it "an existing hook that ends in 'exit 0' still gets the refresh"
make_app "Exit zero hook"
printf '#!/bin/bash\nexit 0\n' > "$T/.git/hooks/pre-commit"; chmod +x "$T/.git/hooks/pre-commit"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane && git -C "$T" commit -qm "listing" >/dev/null 2>&1
assert_contains "$(git -C "$T" show HEAD:listing-review.html 2>&1)" "Exit zero hook"
rm -rf "$T"

it "a non-shell hook is moved to pre-commit.local and keeps its exit status"
make_app "Python hook"
printf '#!/usr/bin/env python3\nimport sys\nprint("py hook ran", file=sys.stderr)\nsys.exit(3)\n' > "$T/.git/hooks/pre-commit"
chmod +x "$T/.git/hooks/pre-commit"
bash "$SUT" "$T" >/dev/null
assert_exec "$T/.git/hooks/pre-commit.local"
git -C "$T" add fastlane
OUT="$(git -C "$T" commit -m "listing" 2>&1)"; RC=$?
assert_ne 0 "$RC" "python hook's failure still rejects the commit"
assert_contains "$OUT" "py hook ran"
rm -rf "$T"

it "migrates a listing-kit 0.2 inline hook block"
make_app "Legacy"
cat > "$T/.git/hooks/pre-commit" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

# BEGIN listing-kit review hook
listing_kit_build_review=/old/path/build-review.sh
listing_kit_app_rel=''
echo old-block
# END listing-kit review hook
EOF
bash "$SUT" "$T" >/dev/null
assert_not_contains "$(cat "$T/.git/hooks/pre-commit")" "BEGIN listing-kit"
assert_contains "$(cat "$T/.git/hooks/pre-commit")" "listing-kit review refresh"
rm -rf "$T"

# --- what the page is built from ---
it "the page reflects staged content, not unstaged edits"
make_app "Staged text"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane
printf 'Unstaged text\n' > "$T/fastlane/metadata/en-US/description.txt"
git -C "$T" commit -qm "listing" >/dev/null 2>&1
PAGE="$(git -C "$T" show HEAD:listing-review.html)"
assert_contains "$PAGE" "Staged text"
assert_not_contains "$PAGE" "Unstaged text"
rm -rf "$T"

it "deletion-only commits refresh the page"
make_app "Deletions"
printf 'Promo to delete\n' > "$T/fastlane/metadata/en-US/promotional_text.txt"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane && git -C "$T" commit -qm "listing" >/dev/null 2>&1
git -C "$T" rm -q fastlane/metadata/en-US/promotional_text.txt
git -C "$T" commit -qm "drop promo" >/dev/null 2>&1
assert_not_contains "$(git -C "$T" show HEAD:listing-review.html)" "Promo to delete"
rm -rf "$T"

it "registers several app roots in one repo"
T="$(mktemp -d)"; git -C "$T" init -q
git -C "$T" config user.email "listing-kit@example.test"; git -C "$T" config user.name "listing-kit test"
for a in apps/one apps/two; do
  mkdir -p "$T/$a/fastlane/metadata/en-US"
  printf 'App %s\n' "$a" > "$T/$a/fastlane/metadata/en-US/name.txt"
  printf 'Description of %s\n' "$a" > "$T/$a/fastlane/metadata/en-US/description.txt"
  bash "$SUT" "$T/$a" >/dev/null
done
git -C "$T" add apps && git -C "$T" commit -qm "two listings" >/dev/null 2>&1
assert_contains "$(git -C "$T" show HEAD:apps/one/listing-review.html)" "Description of apps/one"
assert_contains "$(git -C "$T" show HEAD:apps/two/listing-review.html)" "Description of apps/two"
rm -rf "$T"

summary
