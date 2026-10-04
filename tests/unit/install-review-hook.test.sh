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

it "rerunning replaces the listing-kit block instead of duplicating it"
make_app "Idempotent"
bash "$SUT" "$T" >/dev/null
bash "$SUT" "$T" >/dev/null
assert_eq 1 "$(grep -c 'BEGIN listing-kit review hook' "$T/.git/hooks/pre-commit")"
rm -rf "$T"

it "a stale build-review path warns instead of blocking the commit"
make_app "Stale path"
bash "$SUT" "$T" >/dev/null
sed -i.bak 's#^listing_kit_build_review=.*#listing_kit_build_review=/no/such/build-review.sh#' "$T/.git/hooks/pre-commit"
git -C "$T" add fastlane
OUT="$(git -C "$T" commit -m "listing" 2>&1)"; RC=$?
assert_eq 0 "$RC" "commit still succeeds"
assert_contains "$OUT" "not refreshed"
rm -rf "$T"

summary
