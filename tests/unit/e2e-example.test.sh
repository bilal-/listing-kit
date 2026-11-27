#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

# Exercise the actual entry point with local edits in a disposable example.
new_tempdir repo
example="$repo/examples/expo-recipe-box"
kit="$repo/skills/listing-kit"
mkdir -p "$repo/tests/e2e" "$repo/tools" "$kit/bin" "$example/.listing-kit/flows"
cp "$ROOT/tests/e2e/example.sh" "$repo/tests/e2e/"
cp "$ROOT/tests/helpers.sh" "$repo/tests/"
ln -s "$SCRIPTS" "$kit/scripts"
# Only the fixture setup runs. Provide the two executable probes locally so
# these tests also run on hosts that lack either render dependency.
export LK_BROWSER="$BASH_BIN"
unset LK_NO_IMAGEMAGICK
ln -s "$BASH_BIN" "$kit/bin/magick"
export PATH="$kit/bin:$PATH"
for tool in bash dirname git mkdir python3; do
    ln -s "$(command -v "$tool")" "$repo/tools/$tool"
done
cat > "$kit/bin/listing-kit" <<'STUB'
#!/usr/bin/env bash
case "$1" in
    doctor) exit 0 ;;
    plan)
        [ -f .listing-kit/listing.json ] && [ ! -L .listing-kit/listing.json ] &&
            [ ! -L .listing-kit/raw ] && [ ! -e private.txt ] &&
            [ -f .listing-kit/raw/ipad/en-US/recipes.png ] && echo 'fresh fixture ready'
        exit 77 ;;
esac
STUB
chmod +x "$kit/bin/listing-kit"
printf 'local plan\n' > "$repo/local-plan"
ln -s "$repo/local-plan" "$example/.listing-kit/listing.json"
mkdir -p "$example/.listing-kit/raw"/{iphone-medium,ipad,play-phone}/en-US
touch "$example/private.txt" "$example/app.json"
metadata="$example/fastlane/metadata"
play="$metadata/android/en-US"
mkdir -p "$metadata/en-US" "$play/images"
touch "$metadata/"{copyright,primary_category}.txt
touch "$metadata/en-US/"{description,keywords,marketing_url,name,privacy_url,promotional_text,release_notes,subtitle,support_url}.txt
touch "$play/"{title,short_description,full_description}.txt "$play/images/"{icon,featureGraphic}.png
for stem in 01_recipes 02_recipe-detail 03_shopping 04_settings; do
    touch "$example/.listing-kit/flows/${stem#*_}.yaml"
    touch "$example/.listing-kit/raw"/{iphone-medium,ipad,play-phone}/en-US/"${stem#*_}.png"
done

run_example() {
    bash "$repo/tests/e2e/example.sh" --suite-root "$SUITE_ROOT"
}

it "e2e skips missing render dependencies visibly unless rendering is required"
for strict in 0 1; do
    out="$(LK_BROWSER="$repo/missing-browser" LK_REQUIRE_RENDER="$strict" run_example 2>&1)"
    assert_eq "$strict" "$?"
    assert_contains "$out" "skipped: no browser"
    out="$(PATH="$repo/tools" LK_REQUIRE_RENDER="$strict" run_example 2>&1)"
    assert_eq "$strict" "$?"
    assert_contains "$out" "skipped: no ImageMagick"
done

it "e2e builds a fresh listing from named example inputs"
out="$(run_example 2>&1)"
assert_contains "$out" "fresh fixture ready"
assert_eq 'local plan' "$(cat "$repo/local-plan")"

it "e2e refuses symlinks at a named input or its parent"
for path in "$example/app.json" "$example/.listing-kit/flows" "$example/.listing-kit/raw"; do
    mv "$path" "$path.original"
    ln -s "$path.original" "$path"
    out="$(run_example 2>&1)"
    assert_ne 0 "$?"
    assert_not_contains "$out" "fresh fixture ready"
    assert_contains "$out" "${path##*/}"
    rm "$path"
    mv "$path.original" "$path"
done
summary
