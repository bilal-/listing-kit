#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

SUT="$SCRIPTS/handoff/handoff.py"
assert_no_file() { if [ -e "$1" ]; then fail "should not exist: $1"; else pass "absent: ${1##*/}"; fi; }
T="$(mktemp -d)"; [ -n "$T" ] && [ -d "$T" ] || { echo "mktemp failed" >&2; exit 1; }
T="$(cd "$T" && pwd -P)" || exit 1
trap 'rm -rf "$T"' EXIT
A="$T/app"; S="$A/fastlane/screenshots/en-US"; M="$A/fastlane/metadata"; P="$M/android/en-US"
mkdir -p "$S" "$M/en-US" "$M/default" "$P/images/phoneScreenshots" "$P/images/tenInchScreenshots" "$P/changelogs" "$A/store-assets/apple/en-US"
fake_png "$S/01_home_iphone-medium.png" 1206 2622
fake_png "$S/02_list_iphone-medium.png" 1206 2622
fake_png "$S/01_home_ipad.png" 2064 2752
fake_png "$S/01_home_duo-outer.png" 1398 2034
fake_png "$S/01_home_duo-inner.png" 2007 2853
printf 'Recipe Box' > "$M/en-US/name.txt"
printf 'https://example.com/help\n' > "$M/default/support_url.txt"
printf '2026 Example' > "$M/copyright.txt"
fake_png "$A/store-assets/apple/en-US/header-16x9.png" 5244 2950
fake_png "$P/images/phoneScreenshots/02_list.png" 1080 1920
fake_png "$P/images/phoneScreenshots/01_home.png" 1080 1920
fake_png "$P/images/tenInchScreenshots/01_home.png" 1920 1080
fake_png "$P/images/icon.png" 512 512 8 6
fake_png "$P/images/featureGraphic.png" 1024 500
printf 'Recipe Box' > "$P/title.txt"
printf 'First release.' > "$P/changelogs/default.txt"
O="$A/.listing-kit/upload"

it "builds one numbered folder per console slot, in console order, plus text, graphics and an index"
OUT="$(python3 "$SUT" "$A" 2>&1)"; RC=$?
assert_eq 0 "$RC" "exit 0"
assert_contains "$OUT" "$O/INDEX.html"
# Expected layout, written out by hand (not derived from the rules file).
EXPECT='.gitignore
.listing-kit-upload
INDEX.html
INDEX.md
apple/en-US/01 iPhone Dynamic Island (medium display)/01-home_iphone-medium.png
apple/en-US/01 iPhone Dynamic Island (medium display)/02-list_iphone-medium.png
apple/en-US/02 iPhone Duo (outer display)/01-home_duo-outer.png
apple/en-US/03 iPhone Duo (inner display)/01-home_duo-inner.png
apple/en-US/04 iPad 13in/01-home_ipad.png
apple/en-US/graphics/header-16x9.png
apple/app-wide/copyright.txt
apple/en-US/text/name.txt
apple/en-US/text/support_url.txt
play/en-US/01 Phone/01-home.png
play/en-US/01 Phone/02-list.png
play/en-US/02 10-inch tablet/01-home.png
play/en-US/graphics/featureGraphic.png
play/en-US/graphics/icon.png
play/en-US/text/release-notes-default.txt
play/en-US/text/title.txt'
GOT="$(cd "$O" && find . -type f | sed 's|^\./||' | LC_ALL=C sort)"
assert_eq "$(printf '%s\n' "$EXPECT" | LC_ALL=C sort)" "$GOT" "exact file inventory"

it "copies are byte-identical and text falls back to metadata/default as deliver does"
if cmp -s "$S/01_home_ipad.png" "$O/apple/en-US/04 iPad 13in/01-home_ipad.png"; then pass "screenshot bytes"; else fail "screenshot differs"; fi
if cmp -s "$P/images/featureGraphic.png" "$O/play/en-US/graphics/featureGraphic.png"; then pass "feature graphic bytes"; else fail "feature graphic differs"; fi
assert_eq "https://example.com/help" "$(cat "$O/apple/en-US/text/support_url.txt")" "default fallback"

it "the index groups screenshots by slot and names each console field"
IDX="$(cat "$O/INDEX.md")"
assert_contains "$IDX" 'apple/en-US/02 iPhone Duo (outer display)/'
assert_contains "$IDX" "1.0 Prepare for Submission) > Screenshots > iPhone Duo (outer display)"
assert_contains "$IDX" "Main store listing > Feature graphic"
assert_contains "$IDX" "drag all 2 files in file-name order"
assert_eq 14 "$(grep -c '^| `' "$O/INDEX.md")" "one row per text file, graphic, or screenshot folder"

it "a rebuild replaces the folder, so a file removed from the listing does not linger"
rm "$S/02_list_iphone-medium.png"
touch "$O/stale.txt"
OUT="$(python3 "$SUT" "$A" 2>&1)"; RC=$?
assert_eq 1 "$RC" "refused user file"
assert_contains "$OUT" "stale.txt"
assert_file "$O/stale.txt"
rm "$O/stale.txt"
python3 "$SUT" "$A" >/dev/null 2>&1
assert_no_file "$O/stale.txt"
assert_no_file "$O/apple/en-US/01 iPhone Dynamic Island (medium display)/02-list_iphone-medium.png"
assert_eq "" "$(ls -a "$A/.listing-kit" | grep '^\.upload' || true)" "no temporary folders left behind"

it "a screenshot that fits no slot stops the build and leaves the previous folder untouched"
fake_png "$S/09_odd.png" 1000 1000
BEFORE="$(cat "$O/INDEX.md")"
OUT="$(python3 "$SUT" "$A" 2>&1)"; RC=$?
assert_eq 1 "$RC" "exit 1"
assert_contains "$OUT" "1000x1000 matches no App Store slot"
assert_eq "$BEFORE" "$(cat "$O/INDEX.md")" "previous folder kept"
rm "$S/09_odd.png"

it "a folder with no listing exits 1 and writes nothing"
mkdir -p "$T/empty"
python3 "$SUT" "$T/empty" >/dev/null 2>&1; assert_eq 1 "$?" "exit 1"
assert_no_file "$T/empty/.listing-kit"

it "rejects --out and other bad usage with exit 2"
OUT="$(python3 "$SUT" "$A" --out "$T/elsewhere" 2>&1)"; RC=$?
assert_eq 2 "$RC" "removed --out flag"
assert_contains "$OUT" "usage:"
assert_no_file "$T/elsewhere"
python3 "$SUT" >/dev/null 2>&1; assert_eq 2 "$?" "no args"
python3 "$SUT" "$T/nope" >/dev/null 2>&1; assert_eq 2 "$?" "missing dir"

it "--open prints the index path when the browser cannot start"
OUT="$(PATH="/usr/bin:/bin" python3 -c "
import sys; sys.argv=['x']; sys.path.insert(0,'$SCRIPTS/handoff')
import handoff, shutil
handoff.shutil.which=lambda c: None
sys.exit(handoff.main(['$A','--open']))" 2>&1)"; RC=$?
assert_eq 0 "$RC" "exit 0"
assert_contains "$OUT" "Could not open the instructions"

it "passes the adversarial handoff regression cases"
python3 "$(dirname "${BASH_SOURCE[0]}")/handoff_cases.py"
assert_eq 0 "$?" "handoff regressions"

assert_eq 1 "${PYTHONDONTWRITEBYTECODE:-}" "test helpers disable Python bytecode"
summary
