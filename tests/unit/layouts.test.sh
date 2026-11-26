#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir area
new_stubdir
export LK_NO_IMAGEMAGICK=1
lk="$SKILL_DIR/bin/listing-kit"
reference="$SKILL_DIR/references/metadata/fastlane-layout.md"
example="$ROOT/examples/expo-recipe-box/fastlane"
export layout_log="$area/fastlane.log"
cat > "$STUB_BIN/bundle" <<'PY'
#!/usr/bin/env python3
import os, sys
from pathlib import Path
args = sys.argv[1:]
assert args[:2] == ["exec", "fastlane"]
with open(os.environ["layout_log"], "a") as log:
    print(os.environ["BUNDLE_GEMFILE"], Path.cwd(), args[2], sep="\t", file=log)
if "--metadata_path" in args:
    Path(args[args.index("--metadata_path") + 1]).mkdir()
PY
chmod +x "$STUB_BIN/bundle"
stub fastlane 1
export PATH="$STUB_BIN:$PATH"
export APP_STORE_CONNECT_API_KEY_PATH="$area/apple.json" SUPPLY_JSON_KEY="$area/play.json"
echo '{}' > "$APP_STORE_CONNECT_API_KEY_PATH"
echo '{}' > "$SUPPLY_JSON_KEY"

copy_fixture() {
  new_tempdir repo
  cp -R "$ROOT/tests/fixtures/layouts/$1/." "$repo/"
  git -C "$repo" init -q
}

# Copy the required text and one Apple / two Play screenshots from the validated example.
listing() {
  local app="$1" apple="$2" play="$3" meta
  if [ "$apple" != '—' ]; then
    meta="$app/$apple/metadata"
    mkdir -p "$meta/en-US" "$app/$apple/screenshots/en-US"
    cp "$example/metadata/"*.txt "$meta/"
    cp "$example/metadata/en-US/"*.txt "$meta/en-US/"
    fake_png "$app/$apple/screenshots/en-US/01.png" 1206 2622
    echo 'Layout Apple' > "$meta/en-US/name.txt"
  fi
  if [ "$play" != '—' ]; then
    meta="$app/$play/metadata/android/en-US"
    mkdir -p "$meta/images/phoneScreenshots"
    cp "$example/metadata/android/en-US/"*.txt "$meta/"
    cp "$example/metadata/android/en-US/images/"*.png "$meta/images/"
    cp "$example/metadata/android/en-US/images/phoneScreenshots/0"[12]* "$meta/images/phoneScreenshots/"
    echo 'Layout Play' > "$meta/title.txt"
  fi
}

# Rows are app-relative here and in the reference. A dash means the store is absent.
layout() {
  local name="$1" folder="$2" stack="$3" stores="$4" apple="$5" play="$6"
  local app out manifest store directory gemfile action path roots
  copy_fixture "$name"
  app="$(cd "$repo/$folder" && pwd -P)"
  it "$name ($folder) detects its stack, stores and app root"
  out="$("$lk" detect "$app" 2>&1)"
  assert_contains "$out" "$(printf 'stack\t%s\n' "$stack")"
  assert_contains "$out" "$(printf 'stores\t%s\n' "$stores")"
  assert_contains "$out" "$(printf 'appRoot\t%s\n' "$app")"
  mkdir -p "$app/.listing-kit"
  echo '{"format":2,"app":"org.example.layout","platforms":{"supportsIphone":true,"supportsIpad":false},"locales":["en-US"],"targets":[],"screens":[]}' > "$app/.listing-kit/listing.json"
  manifest="$("$lk" plan manifest "$app")" || { fail "$manifest"; return; }
  for store in $stores; do
    directory="$apple"; [ "$store" != play ] || directory="$play"
    it "$name resolves $store before a listing is written"
    path="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["trees"][sys.argv[1]]["fastlaneDir"])' "$store" <<< "$manifest")"
    assert_eq "$directory" "$path"
  done
  listing "$app" "$apple" "$play"
  it "$name validates the listing at the expected locations"
  out="$("$lk" validate "$app" --as-of 2026-01-01 2>&1)" || fail "$out"
  assert_contains "$out" "LISTING VALID"
  it "$name handoff reads each store's copy"
  out="$("$lk" handoff "$app" 2>&1)" || fail "$out"
  for store in $stores; do
    if [ "$store" = apple ]; then
      path="apple/en-US/text/name.txt"; directory="$apple"; action=deliver
      assert_eq "Layout Apple" "$(cat "$app/.listing-kit/upload/$path")"
    else
      path="play/en-US/text/title.txt"; directory="$play"; action=supply
      assert_eq "Layout Play" "$(cat "$app/.listing-kit/upload/$path")"
    fi
    it "$name fastlane uses the $store project's Gemfile from a clean working directory"
    gemfile="$(dirname "$app/$directory")/Gemfile"
    echo 'gem "fastlane"' > "$gemfile"
    : > "$layout_log"
    out="$("$lk" fastlane setup "$app" --store "$store" 2>&1)" || fail "$out"
    assert_contains "$out" "fastlaneDir=$app/$directory "
    awk -F '\t' -v gem="$gemfile" -v root="$TMPDIR/listing-kit-fastlane-" -v action="$action" \
      '$1 == gem && index($2,root)==1 && $3==action {found=1} END {exit !found}' "$layout_log" && pass || fail "$(cat "$layout_log")"
  done
  it "$name reuses the exact fastlane directories"
  roots="$(cd "$app" && find . -type d -name fastlane | sort)"
  assert_eq "$(printf '%s\n' "$apple" "$play" | sed '/^—$/d;s|^|./|' | sort -u)" "$roots"
  it "$name reference row"
  assert_contains "$(cat "$reference")" "| $name | $folder | $stores | $apple | $play |"
}

ambiguous() {
  local name="$1" candidates="$2" cmd out candidate
  copy_fixture "$name"
  for cmd in detect 'plan manifest' validate handoff 'fastlane setup'; do
    it "$name $cmd stops at the workspace root and explains the choice"
    if out="$("$lk" $cmd "$repo" 2>&1)"; then fail "unexpected success"; fi
    for candidate in $candidates; do assert_contains "$out" "$candidate"; done
    assert_contains "$out" "run inside"
  done
  it "$name leaves the workspace root untouched"
  if [ -e "$repo/fastlane" ] || [ -e "$repo/.listing-kit" ]; then fail "created listing at workspace root"; else pass; fi
  assert_contains "$(cat "$reference")" "| $name | workspace root | choose $candidates | — | — |"
}

layout expo-managed . expo-managed 'apple play' fastlane fastlane
layout expo-prebuild . expo-prebuild 'apple play' fastlane fastlane
layout react-native-bare . react-native-bare 'apple play' ios/fastlane android/fastlane
layout flutter . flutter 'apple play' fastlane fastlane
layout native-ios . native-ios apple fastlane —
layout native-android . native-android play — fastlane
ambiguous monorepo-siblings 'apps/android apps/ios'
layout monorepo-siblings apps/ios native-ios apple fastlane —
layout monorepo-siblings apps/android native-android play — fastlane
ambiguous monorepo-js apps/mobile
layout monorepo-js apps/mobile expo-managed 'apple play' fastlane fastlane
layout existing-root-fastlane . expo-prebuild 'apple play' fastlane fastlane
summary
