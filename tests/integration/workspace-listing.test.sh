#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir app
git -C "$app" init -q
export LK_NO_IMAGEMAGICK=1
lk="$SKILL_DIR/bin/listing-kit"
cp -R "$ROOT/tests/fixtures/layouts/monorepo-module/." "$app/"
android="$app/apps/handset"
it "workspace discovery names both native apps and shows one two-store root plan"
out="$("$lk" detect "$app" 2>&1)"; assert_ne 0 "$?"
assert_contains "$out" "apps/handset, apps/tablet"
assert_contains "$out" '"fastlaneDir": "apps/handset/fastlane"'
assert_contains "$out" '"fastlaneDir": "apps/tablet/fastlane"'

it "single-store app folders only print paths for their store"
out="$("$lk" detect "$app/apps/tablet")"
assert_not_contains "$out" 'play.metadata'
for plugin in 'id("com.android.application")' "apply plugin: 'com.android.application'" "id 'com.android.application'" 'alias(libs.plugins.android.application)'; do
  case "$plugin" in *"'"*) build=build.gradle ;; *) build=build.gradle.kts ;; esac
  rm -f "$android/build.gradle" "$android/build.gradle.kts"
  case "$plugin" in
    "apply plugin:"*) echo "$plugin" > "$android/$build" ;;
    *) echo "plugins { $plugin }" > "$android/$build" ;;
  esac
  out="$("$lk" detect "$android")"; assert_contains "$out" $'stores\tplay'
  assert_not_contains "$out" 'apple.metadata'
  out="$("$lk" detect "$app" 2>&1)"; assert_contains "$out" 'apps/handset, apps/tablet'
done
for plugin in 'alias(libs.plugins.android.library)' 'alias(libs.plugins.android.application) apply false'; do
  echo "plugins { $plugin }" > "$android/build.gradle.kts"
  out="$("$lk" detect "$app" 2>&1)"; assert_not_contains "$out" 'apps/handset'
done

it "version catalog aliases identify the applied Android plugin by ID"
mkdir -p "$app/gradle"
cat > "$app/gradle/libs.versions.toml" <<'TOML'
[plugins]
mobile-client = { id = "com.android.application", version.ref = "agp" }
android-application = { id = "com.android.library", version.ref = "agp" }
TOML
echo 'plugins { alias(libs.plugins.mobile.client) }' > "$android/build.gradle.kts"
out="$("$lk" detect "$app" 2>&1)"; assert_contains "$out" 'apps/handset, apps/tablet'
echo 'plugins { alias(libs.plugins.android.application) }' > "$android/build.gradle.kts"
out="$("$lk" detect "$app" 2>&1)"; assert_not_contains "$out" 'apps/handset'

mkdir -p "$app/.listing-kit"
cp "$ROOT/tests/fixtures/workspace-listing/listing.json" "$app/.listing-kit/"
it "explicit trees select both stores before listing content exists"
out="$("$lk" detect "$app")"; assert_contains "$out" $'stores\tapple play'
assert_contains "$out" $'play.metadata\tartwork'

it "flat Play artwork has a concrete destination in plan check"
fake_png "$app/artwork/icon.png" 512 512 8 6
dest=artwork/en-US/images/icon.png
out="$("$lk" plan check "$app" 2>&1)"
assert_contains "$out" "copy artwork/icon.png to $dest"

python3 - "$app/.listing-kit/listing.json" <<'PYPLAN'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
data = json.loads(path.read_text())
del data["graphics"]
path.write_text(json.dumps(data))
PYPLAN
out="$("$lk" plan check "$app" 2>&1)"
assert_contains "$out" "move artwork/icon.png to $dest"
cp "$ROOT/tests/fixtures/workspace-listing/listing.json" "$app/.listing-kit/"

it "validation and review identify the exact missing upload"
out="$("$lk" validate "$app" 2>&1)"; assert_ne 0 "$?"
assert_not_contains "$out" 'LISTING VALID'
assert_contains "$out" "$dest"
"$lk" review "$app" >/dev/null 2>&1
assert_contains "$(cat "$app/listing-review.html")" "$dest"

it "handoff explains empty and partial packages and preserves the index"
out="$("$lk" handoff "$app" 2>&1)"; assert_ne 0 "$?"
assert_contains "$out" "$dest"
assert_contains "$out" '0 listing files'
assert_contains "$(cat "$app/.listing-kit/upload/INDEX.md")" "$dest"
mkdir -p "$app/artwork/en-US"
echo Example > "$app/artwork/en-US/title.txt"
out="$("$lk" handoff "$app" 2>&1)"; assert_ne 0 "$?"
assert_contains "$out" "$dest"
assert_file "$app/.listing-kit/upload/play/en-US/text/title.txt"

it "the resolved icon is reviewed, validated and packaged from the same path"
mkdir -p "$app/artwork/en-US/images"
cp "$app/artwork/icon.png" "$app/$dest"
out="$("$lk" plan check "$app" 2>&1)"; assert_eq 0 "$?"
assert_not_contains "$out" "$dest"
out="$("$lk" validate "$app" 2>&1)"
assert_not_contains "$out" "$dest: MISSING"
"$lk" review "$app" >/dev/null 2>&1
assert_contains "$(cat "$app/listing-review.html")" "$dest"
out="$("$lk" handoff "$app" 2>&1)"; assert_eq 0 "$?"
cmp -s "$app/$dest" "$app/.listing-kit/upload/play/en-US/graphics/icon.png" && pass || fail "$out"

it "validation catches a planned upload even without a metadata directory"
mv "$app/artwork" "$app/source"
sed 's|"from": "artwork/icon.png"|"from": "source/icon.png"|' "$ROOT/tests/fixtures/workspace-listing/listing.json" > "$app/.listing-kit/listing.json"
echo '.listing-kit/local.json' > "$app/.gitignore"
echo '{}' > "$app/.listing-kit/local.json"
out="$("$lk" validate "$app" 2>&1)"; assert_ne 0 "$?"
assert_not_contains "$out" 'LISTING VALID'
assert_contains "$out" "$dest"

out="$("$lk" review "$app" 2>&1)"; assert_eq 0 "$?"
assert_contains "$(cat "$app/listing-review.html")" "$dest: MISSING"

it "an active target without screens or listing files has nothing to validate"
new_tempdir empty
mkdir "$empty/.listing-kit"
cat > "$empty/.listing-kit/listing.json" <<'JSON'
{"format":2,"app":"org.example.mobile","locales":["en-US"],"targets":[{"id":"mobile","store":"play","slot":"phone","state":"active","size":[1080,1920]}],"screens":[]}
JSON
out="$("$lk" validate "$empty" 2>&1)"; assert_ne 0 "$?"
assert_contains "$out" 'nothing to validate'
assert_not_contains "$out" 'LISTING VALID'
summary
