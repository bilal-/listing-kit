#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir area
new_stubdir
export LK_NO_IMAGEMAGICK=1
unset LK_PUBLISH_UNVERIFIED
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
    directory = Path(args[args.index("--metadata_path") + 1]) / "en-US"
    directory.mkdir(parents=True)
    if "download_metadata" in args:
        (directory / "name.txt").write_text("Downloaded name")
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

# Reuse the example copy and Play assets. Generate one small-on-disk Apple screenshot.
listing() {
  local app="$1" apple="$2" play="$3" meta
  if [ "$apple" != '—' ]; then
    meta="$app/$apple/metadata"
    mkdir -p "$meta/en-US" "$app/$apple/screenshots/en-US"
    cp "$example/metadata/"*.txt "$meta/"
    cp "$example/metadata/en-US/"{description,keywords,support_url,privacy_url}.txt "$meta/en-US/"
    fake_png "$app/$apple/screenshots/en-US/01.png" 1206 2622
    [ -f "$meta/en-US/name.txt" ] || echo 'Layout Apple' > "$meta/en-US/name.txt"
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
  local title="Layout Apple"
  [ "$name" != existing-root-fastlane ] || title="Existing title"
  copy_fixture "$name"
  app="$(cd "$repo/$folder" && pwd -P)"
  it "$name ($folder) detects its stack, stores and app root"
  out="$("$lk" detect "$app" 2>&1)"
  assert_eq "$stack" "$(printf '%s\n' "$out" | awk -F '\t' '$1=="stack" {print $2}')"
  assert_eq "$stores" "$(printf '%s\n' "$out" | awk -F '\t' '$1=="stores" {print $2}')"
  assert_eq "$app" "$(printf '%s\n' "$out" | awk -F '\t' '$1=="appRoot" {print $2}')"
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
  [ "$apple" = '—' ] || assert_contains "$out" "== Apple App Store =="
  [ "$play" = '—' ] || assert_contains "$out" "== Google Play =="
  it "$name handoff reads each store's copy"
  out="$("$lk" handoff "$app" 2>&1)" || fail "$out"
  for store in $stores; do
    if [ "$store" = apple ]; then
      path="apple/en-US/text/name.txt"; directory="$apple"; action=deliver
      assert_eq "$title" "$(cat "$app/.listing-kit/upload/$path")"
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
  echo "| $name | $folder | $stores | $apple | $play |" >> "$area/rows.md"
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
  echo "| $name | workspace root | choose $candidates | — | — |" >> "$area/rows.md"
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

for name in root-listing-build-ios android-lanes-only; do
  copy_fixture "$name"
  out="$("$lk" detect "$repo")" || fail "$out"
  apple="$(awk -F '\t' '$1=="apple.fastlaneDir" {print $2}' <<< "$out")"
  play="$(awk -F '\t' '$1=="play.fastlaneDir" {print $2}' <<< "$out")"
  echo "| $name | . | apple play | $apple | $play |" >> "$area/rows.md"
done
copy_fixture duplicate-apple
it "duplicate Apple content requires a tree selection"
out="$("$lk" detect "$repo" 2>&1)"
assert_ne 0 "$?"
assert_contains "$out" "trees.apple.fastlaneDir"
echo '| duplicate-apple | . | choose Apple trees | — | — |' >> "$area/rows.md"

it "the complete reference table matches the tested layouts"
table="$(awk '/^\| Layout \| App directory / { rows=1; next } rows && /^\| ---/ { next }
             rows && /^\|/ { print; next } rows { exit }' "$reference")"
assert_eq "$(cat "$area/rows.md")" "$table"

# Exercise precedence before the test creates metadata. A Fastfile at the app
# root wins even when both platform Fastfiles exist. Empty platform fastlane directories
# do not select a native root.
manifest_dirs() {
  "$lk" plan manifest "$repo" | python3 -c 'import json,sys
trees=json.load(sys.stdin)["trees"]
print(trees["apple"]["fastlaneDir"], trees["play"]["fastlaneDir"])'
}

it "root Fastfile wins over platform Fastfiles"
copy_fixture react-native-bare
mkdir -p "$repo/fastlane" "$repo/.listing-kit"
echo '# root lanes' > "$repo/fastlane/Fastfile"
echo '{"format":2,"app":"org.example.layout","locales":["en-US"],"targets":[],"screens":[]}' > "$repo/.listing-kit/listing.json"
assert_eq "fastlane fastlane" "$(manifest_dirs)"

it "empty native folders leave both stores at root"
copy_fixture flutter
mkdir -p "$repo/ios/fastlane" "$repo/.listing-kit" "$repo/fastlane"
echo '{"format":2,"app":"org.example.layout","locales":["en-US"],"targets":[],"screens":[]}' > "$repo/.listing-kit/listing.json"
assert_eq "fastlane fastlane" "$(manifest_dirs)"

it "a planless pull creates its downloaded Apple field in the existing platform tree"
copy_fixture react-native-bare
echo 'gem "fastlane"' > "$repo/ios/Gemfile"
out="$("$lk" pull "$repo" --store apple --app-identifier org.example.layout 2>&1)" || fail "$out"
assert_eq 'Downloaded name' "$(cat "$repo/ios/fastlane/metadata/en-US/name.txt")"
if [ -d "$repo/fastlane" ]; then fail "pull duplicated the native tree"; else pass; fi

it "explicit trees take precedence and validate and handoff read custom metadata and screenshot paths"
copy_fixture react-native-bare
listing "$repo" apple-lanes play-lanes
mv "$repo/apple-lanes/metadata" "$repo/apple-copy"
mv "$repo/apple-lanes/screenshots" "$repo/apple-shots"
mv "$repo/play-lanes/metadata/android" "$repo/play-copy"
mkdir -p "$repo/.listing-kit"
cat > "$repo/.listing-kit/listing.json" <<'JSON'
{"format":2,"app":"org.example.layout","locales":["en-US"],"targets":[],"screens":[],
 "platforms":{"supportsIphone":true,"supportsIpad":false},
 "trees":{"apple":{"fastlaneDir":"apple-lanes","metadata":"apple-copy","screenshots":"apple-shots"},
          "play":{"fastlaneDir":"play-lanes","metadata":"play-copy"}}}
JSON
assert_eq "apple-lanes play-lanes" "$(manifest_dirs)"
# An ignored private file forces validation to prepare a filtered input directory.
echo .listing-kit/local.json > "$repo/.gitignore"
echo '{}' > "$repo/.listing-kit/local.json"
out="$("$lk" validate "$repo" --as-of 2026-01-01 2>&1)" || fail "$out"
assert_contains "$out" "== Apple App Store =="
assert_contains "$out" "== Google Play =="
out="$("$lk" handoff "$repo" 2>&1)" || fail "$out"
assert_eq "Layout Apple" "$(cat "$repo/.listing-kit/upload/apple/en-US/text/name.txt")"
assert_eq "Layout Play" "$(cat "$repo/.listing-kit/upload/play/en-US/text/title.txt")"

shot_dir='apple/en-US/01 iPhone Dynamic Island (medium display)'
upload="$repo/.listing-kit/upload"
cmp -s "$repo/apple-shots/en-US/01.png" "$upload/$shot_dir/01-01.png" && pass || fail "exported Apple screenshot differs or is missing"
assert_contains "$(cat "$upload/INDEX.md")" "$shot_dir/"
summary
