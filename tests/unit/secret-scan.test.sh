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

summary
