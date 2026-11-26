#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir area
export HOME="$area/home"
unset LISTING_KIT_HOME LK_BROWSER LK_NO_IMAGEMAGICK
channel="$HOME/.codex/plugins/cache/example/listing-kit"
kit="$channel/old/skills/listing-kit"
mkdir -p "$kit" "$area/work" "$area/links"
cp -R "$SKILL_DIR/." "$kit/"
cli="$kit/bin/listing-kit"
cd "$area/work" || exit 1

it "CLI is executable"
assert_exec "$cli"
for name in validate/validate-listing.sh package/build-review.sh handoff/handoff.py capture/capture.py \
    lib/plan.py lib/detect.py package/install-review-hook.sh compose/compose.py fastlane/lk_fastlane.py; do
  target="$kit/scripts/$name"
  mkdir -p "${target%/*}"
  case "$name" in
    *.py) cat > "$target" <<'PY'
from pathlib import Path
import sys
print("\n".join([Path(__file__).name] + sys.argv[1:]))
sys.exit(37)
PY
      ;;
    *) cat > "$target" <<'SH'
#!/bin/bash
printf '%s\n' "${0##*/}" "$@"
exit 37
SH
      chmod +x "$target" ;;
  esac
done
ln -s ../links/kit "$area/work/entry"
ln -s "$cli" "$area/links/kit"
dispatch() {
  local expected="$1" out rc
  shift
  out="$(./entry "$@" 2>&1)"; rc=$?
  it "dispatch $* with argument boundaries and exit status"
  assert_eq 37 "$rc"
  assert_eq "$expected" "$out"
}
dispatch $'handoff.py\n--open\n.' handoff --open
dispatch $'capture.py\n--target\nphone\n--dry-run\n.' capture --target phone --dry-run
dispatch $'plan.py\ncheck\n--for\npublish\n.' plan check --for publish
dispatch $'compose.py\n--screen\nhome\n.' compose --screen home
app='app with spaces'
for pair in 'validate validate-listing.sh' 'review build-review.sh' 'capture capture.py' 'compose compose.py'; do
  dispatch "$(printf '%s\n' "${pair#* }" "$app" --flag 'two words')" "${pair% *}" "$app" --flag 'two words'
done
dispatch "$(printf '%s\n' handoff.py "$app" --open)" handoff "$app" --open
dispatch "$(printf '%s\n' handoff.py "$app" --open)" open "$app"
dispatch "$(printf '%s\n' detect.py "$app")" detect "$app"
dispatch $'detect.py\n.' detect
for op in check manifest outputs; do
  dispatch "$(printf '%s\n' plan.py "$op" "$app")" plan "$op" "$app"
done
dispatch "$(printf '%s\n' install-review-hook.sh "$app")" hook install "$app"
dispatch "$(printf '%s\n' install-review-hook.sh --status "$app")" hook status "$app"
for op in setup pull publish; do
  expected="$(printf '%s\n' lk_fastlane.py "$op" --store apple "$app")"
  dispatch "$expected" fastlane "$op" --store apple "$app"
  [ "$op" = setup ] || dispatch "$expected" "$op" --store apple "$app"
done
rm "$kit/scripts/compose/compose.py" "$kit/scripts/fastlane/lk_fastlane.py"
for words in compose 'fastlane setup' 'fastlane pull' 'fastlane publish' publish pull; do
  it "missing optional command $words"
  out="$("$cli" $words 2>&1)"; assert_eq 3 "$?"
  assert_eq 'this command is not part of this build of listing-kit' "$out"
done
it "version uses bundled rules and kit VERSION"
date="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["verified"])' "$kit/specs/stores.json")"
assert_eq "listing-kit $(cat "$kit/VERSION") (store rules verified $date)" "$("$cli" version)"
it "bare invocation and help list every command"
help="$("$cli" help)"; assert_eq "$help" "$("$cli")"
for cmd in validate review handoff open capture plan detect hook compose fastlane pull publish doctor version ci link help; do
  if printf '%s\n' "$help" | grep -Eq "^  $cmd( |$)"; then pass "$cmd in help"; else fail "$cmd missing"; fi
done
for args in 'bogus' 'plan bogus' 'hook bogus' 'ci bogus' 'fastlane bogus'; do
  "$cli" $args >/dev/null 2>&1; assert_eq 2 "$?" "reject $args"
done

it "link creates a launcher and shows a usable PATH line"
bin="$HOME/.local/bin"
out="$("$cli" link 2>&1)"; assert_eq 0 "$?"; assert_exec "$bin/listing-kit"
assert_contains "$out" 'export PATH='
out="$(PATH="$bin:$PATH" "$cli" link 2>&1)"; assert_eq 0 "$?"; assert_contains "$out" 'on PATH'
make_version() {
  mkdir -p "$1/bin" "$1/scripts/lib"
  : > "$1/scripts/lib/secret_scan.py"
  printf '%s\n' "$2" > "$1/VERSION"
  cat > "$1/bin/listing-kit" <<'SH'
#!/bin/bash
cat "${0%/bin/listing-kit}/VERSION"
printf '<%s>\n' "$@"
SH
  chmod +x "$1/bin/listing-kit"
}
it "linked doctor can diagnose missing Python"
new_stubdir
for name in bash dirname cat uname; do ln -s "$(command -v "$name")" "$STUB_BIN/$name"; done
out="$(PATH="$STUB_BIN" "$bin/listing-kit" doctor 2>&1)"; assert_eq 3 "$?"
assert_contains "$out" "MISSING python3"
make_version "$channel/a/skills/listing-kit" 0.9.0
make_version "$channel/b/skills/listing-kit" 0.12.0
it "launcher prefers recorded install and honors explicit override"
assert_eq "$("$cli" version)" "$("$bin/listing-kit" version)"
assert_eq $'0.9.0\n<two words>' "$(LISTING_KIT_HOME="$channel/a/skills/listing-kit" "$bin/listing-kit" 'two words')"
mv "$kit" "$area/retired"
it "launcher recovers the highest sibling VERSION after its source is removed"
assert_eq $'0.12.0\n<one>\n<two words>' "$("$bin/listing-kit" one 'two words')"
cli="$area/retired/bin/listing-kit"
it "remove deletes the generated launcher only"
"$cli" link --remove >/dev/null; assert_eq 0 "$?"
[ ! -e "$bin/listing-kit" ] && pass || fail "launcher still present"
it "link keeps the kit entry point, even when the destination is forced"
"$cli" link --dir "${cli%/*}" --force >/dev/null 2>&1
assert_ne 0 "$?"
# The remaining cases still use an intact dispatcher if this check regresses.
cp "$SKILL_DIR/bin/listing-kit" "$cli"
custom="$area/custom dir"
mkdir "$custom"; printf 'foreign\n' > "$custom/listing-kit"
for arg in '' '--remove' '--remove --force'; do
  "$cli" link --dir "$custom" $arg >/dev/null 2>&1
  assert_ne 0 "$?"; assert_eq foreign "$(cat "$custom/listing-kit")"
done
it "a marker inside a long first line does not claim a foreign file"
python3 - "$custom/listing-kit" <<'PYMARK'
from pathlib import Path
import sys
Path(sys.argv[1]).write_text("x" * 256 + "# Generated by listing-kit link\n")
PYMARK
"$cli" link --remove --dir "$custom" >/dev/null 2>&1; assert_ne 0 "$?"
assert_file "$custom/listing-kit"
"$cli" link --force --dir "$custom" >/dev/null; assert_eq 0 "$?"
"$cli" link --dir "$custom" --remove >/dev/null; assert_eq 0 "$?"
[ ! -e "$custom/listing-kit" ] && pass || fail "launcher still present"

it "doctor probes tools, plan and hook with an isolated PATH"
new_stubdir
for name in bash dirname cat uname; do ln -s "$(command -v "$name")" "$STUB_BIN/$name"; done
ln -s "$(command -v python3)" "$STUB_BIN/python3"
for name in magick chromium maestro adb fastlane xcrun; do stub "$name"; done
mkdir -p .listing-kit
echo '{}' > .listing-kit/listing.json
printf 'import sys\nsys.exit(sys.argv[1:] != ["check", "."])\n' > "$area/retired/scripts/lib/plan.py"
cat > "$area/retired/scripts/package/install-review-hook.sh" <<'SH'
#!/bin/bash
[ "$*" = '--status .' ] && echo active
SH
out="$(PATH="$STUB_BIN" "$cli" doctor 2>&1)"; assert_eq 0 "$?"
for name in python3 ImageMagick Chromium maestro adb fastlane .listing-kit/listing.json hook; do
  assert_contains "$out" "OK $name"
done
if [ "$(uname -s)" = Darwin ]; then assert_contains "$out" 'OK xcrun simctl'; fi
it "relative dispatcher and doctor invocations ignore exported CDPATH"
ln -s "$area/retired" tools
out="$(CDPATH=. PATH="$STUB_BIN" tools/bin/listing-kit version 2>&1)"
assert_eq 0 "$?"
assert_eq "$("$cli" version)" "$out"
out="$(CDPATH=. PATH="$STUB_BIN" tools/scripts/doctor/doctor.sh 2>&1)"
assert_eq 0 "$?"
assert_contains "$out" "OK ImageMagick"
assert_contains "$out" "OK .listing-kit/listing.json"

rm "$STUB_BIN/python3" "$STUB_BIN/adb" .listing-kit/listing.json
out="$(PATH="$STUB_BIN" "$cli" doctor 2>&1)"; assert_eq 3 "$?"
for name in python3 adb .listing-kit/listing.json; do assert_contains "$out" "MISSING $name"; done
stub python3 1
out="$(PATH="$STUB_BIN" "$cli" doctor 2>&1)"; assert_eq 3 "$?" "unusable Python 3.8+"
ln -sf "$(command -v python3)" "$STUB_BIN/python3"
echo '{}' > .listing-kit/listing.json
echo 'raise SystemExit(1)' > "$area/retired/scripts/lib/plan.py"
echo 'exit 1' >> "$area/retired/scripts/package/install-review-hook.sh"
out="$(PATH="$STUB_BIN" "$cli" doctor 2>&1)"; assert_eq 0 "$?"
assert_contains "$out" 'MISSING .listing-kit/listing.json'
assert_contains "$out" 'MISSING hook'
summary
