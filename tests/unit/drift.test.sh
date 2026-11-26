#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir area
cp -R "$ROOT/tests/fixtures/drift" "$area/pages"
pages="$area/pages"
export LK_DRIFT_TEST_ROOT="$area/allowed"
mkdir -p "$LK_DRIFT_TEST_ROOT"
digests="$LK_DRIFT_TEST_ROOT/digests"
script="$SCRIPTS/specs/drift.py"
run_drift() {
  out="$(python3 -I -B "$script" "$@" 2>&1)"
  rc=$?
}

it "watch manifest lists the ten upstream pages and keeps the Play limits source"
out="$(python3 - "$SKILL_DIR/specs/stores.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
sources = s["sources"]
assert sources["appleUpcomingRequirements"] == "https://developer.apple.com/news/upcoming-requirements/"
assert sources["playStoreListingFields"] == sources["playListing"] == "https://support.google.com/googleplay/android-developer/answer/9859152"
assert not any("play" in u.lower() and "description" in u.lower() and "limit" in u.lower()
               for u in s["unverified"])
html = (("apple-screenshots", "appleScreenshots", "pixel-sizes"),
        ("apple-version-info", "appleVersionInfo", "limits"),
        ("apple-app-info", "appleAppInfo", "limits"),
        ("apple-creative-assets", "appleCreativeAssets", "pixel-sizes"),
        ("apple-upcoming-requirements", "appleUpcomingRequirements", "dated-list"),
        ("play-preview-assets", "playPreviewAssets", "pixel-sizes"),
        ("play-store-listing-fields", "playStoreListingFields", "limits"))
expected = [(i, sources[k], "html", e) for i, k, e in html]
for i, path in (("screenshots", "deliver/lib/deliver/app_screenshot"),
                ("supply", "supply/lib/supply"),
                ("languages", "fastlane_core/lib/fastlane_core/languages")):
    expected.append(("fastlane-" + i, "https://raw.githubusercontent.com/fastlane/fastlane/master/" + path + ".rb", "source", "ruby-constants"))
assert sorted(expected) == sorted((w["id"], w["url"], w["kind"], w["extract"]) for w in s["watch"])
PY
)" && pass || fail "$out"

expect_digest() {
  it "extracts sorted, unique facts from $1"
  run_drift extract "${1%.*}" "$pages/$1"
  assert_eq 0 "$rc"
  if [ "$rc" = 0 ]; then
    python3 -c 'import json,sys; sys.exit(json.loads(sys.argv[1]) != json.loads(sys.argv[2]))' "$out" "$2" && pass || fail "$out"
  fi
}
expect_digest apple-screenshots.html '["Devices / Phone :: 1170x2532","Devices / tablet :: 2048x2732","Devices / tablet :: 2732x2048","Phone A / Portrait :: 1170x2532","Phone B / Portrait :: 1170x2532","Screenshot sizes / Other sample dates :: 9 April 2027","Screenshot sizes / Other sample dates :: Sept. 9, 2026","Screenshot sizes / Phone A :: 1170x2532","Screenshot sizes / Phone B :: 1080x1920","Screenshot sizes / Phone B :: 1170x2532","Screenshot sizes / starting in :: April 2027","Screenshot sizes :: 1284x2778","Screenshot sizes :: 2778x1284","Screenshot sizes :: 512x512","Screenshot sizes :: September 9, 2026"]'
expect_digest apple-version-info.html '["Keywords :: up to 100 bytes","Listing fields / Description :: 80 characters","Listing fields / Metadata / Caption :: between 2 and 30 characters","Listing fields / Metadata / Summary :: 80 characters","Listing fields / Name :: 30 characters","Promotional text :: 170 characters"]'
expect_digest apple-app-info.html '["App / Name :: 30 characters","Bundle / Name :: 50 characters","Fields / Name :: 30 characters","Fields / Subtitle :: 50 characters","Name :: 30 characters","Subtitle :: 30 characters"]'
expect_digest apple-creative-assets.html '["App icon :: 1024x1024"]'
expect_digest play-preview-assets.html '["Artwork / Feature graphic :: 1024x500","Artwork / Icon :: 512x512","Phone screenshots / Each side must be :: between 320 px and 3,840 px","Phone screenshots / The long side is :: at most 2.3 times","Phone screenshots / The short side has a :: minimum 1080px","Phone screenshots / the short side. Use :: 16:9"]'
expect_digest play-store-listing-fields.html '["Store listing / App name :: 30 characters","Store listing / Full description :: up to 4000 characters","Store listing / Short description :: 80 characters","Tags / Select :: up to 5"]'
expect_digest apple-upcoming-requirements.html '["App icon requirements :: May 2027","Icon updates :: June 2027 :: Explanatory copy goes here. June 2027","SDK :: April 2027 :: Beta April 2027, mandatory June 2027","SDK :: June 2027 :: Beta April 2027, mandatory June 2027","SDK requirements :: September 9, 2026","Screenshot requirements :: April 2027"]'
expect_digest fastlane-screenshots.rb '["DisplayType::APPLE_TV :: [[1920,1080]]","DisplayType::IOS_65 :: [[1284,2778],[2778,1284]]","DisplayType::IPAD :: [1024,768]","IOS_55 :: [[1242,2208]]","IOS_61 :: [[1170,2532],[2532,1170]]"]'
expect_digest fastlane-supply.rb '["IMAGES_TYPES :: [\"icon\",\"featureGraphic\"]","IMAGE_TYPES :: [\"icon\",\"featureGraphic\"]","METADATA_UPLOAD_FIELDS :: [\"title\",\"short_description\"]","SCREENSHOT_TYPES :: [\"phoneScreenshots\",\"sevenInchScreenshots\"]"]'
expect_digest fastlane-languages.rb '["ALL_LANGUAGES :: [\"en-US\",\"de-DE\"]"]'

check_pages() { run_drift check --pages "$pages" --digests "$digests"; }
update_pages() { run_drift update --pages "$pages" --digests "$digests"; }
it "check identifies unseeded sources"
check_pages
assert_eq 2 "$rc"
assert_contains "$out" 'apple-screenshots:'
assert_contains "$out" 'baseline'

it "offline update produces ten byte-stable baselines"
update_pages
assert_eq 0 "$rc"
if [ -d "$digests" ]; then cp -R "$digests" "$area/first"; fi
assert_eq 10 "$(find "$digests" -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
update_pages
assert_eq 0 "$rc"
diff -r "$digests" "$area/first" >/dev/null 2>&1 && pass || fail 'baselines differ'
it "check reports unchanged for matching facts"
check_pages
assert_eq 0 "$rc"
assert_contains "$out" 'apple-screenshots: unchanged'

# Change just one rule against the same reviewed snapshot each time.
changed_rule() {
  local file="$1" old="$2" new="$3"
  it "$4"
  python3 - "$pages/$file" "$old" "$new" <<'PYEDIT'
from pathlib import Path
import sys
path, old, new = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
text = path.read_text()
assert text.count(old) == 1
path.write_text(text.replace(old, new))
PYEDIT
  check_pages
  assert_eq 1 "$rc"
  assert_contains "$out" "${file%.*}: changed"
  cp "$ROOT/tests/fixtures/drift/$file" "$pages/$file"
}
changed_rule apple-screenshots.html '<h2>Phone A</h2><p>Portrait: 1170x2532' '<h2>Phone A</h2><p>Portrait: not accepted' 'one heading loses a shared portrait size'
changed_rule apple-app-info.html '<p>Name: 30 characters</p><h2>Bundle</h2><p>Name: 50 characters' '<p>Name: 50 characters</p><h2>Bundle</h2><p>Name: 30 characters' 'identically named fields swap limits across headings'
changed_rule apple-app-info.html '(30 characters)<br><b>Subtitle</b> (50 characters)' '(50 characters)<br><b>Subtitle</b> (30 characters)' 'inline fields swap limits across a line break'
changed_rule apple-screenshots.html 'Phone 1170x2532, tablet 2048x2732' 'Phone 2048x2732, tablet 1170x2532' 'device sizes swap within a list item'
changed_rule play-preview-assets.html '500 px' '600 px' 'unit-bearing dimensions change'
changed_rule apple-screenshots.html '<td>1170x2532</td>' '<td>unavailable</td>' 'one device loses a shared size'
changed_rule apple-screenshots.html '1170x2532</td></tr>
<tr><th>Phone B</th><td>1170x2532 and 1080 by 1920' '1170x2532 and 1080 by 1920</td></tr>
<tr><th>Phone B</th><td>1170x2532' 'a size moves between devices'
changed_rule play-preview-assets.html '320 px' '360 px' 'standalone side range changes'
changed_rule play-preview-assets.html '1080px' '1440px' 'minimum side changes'
changed_rule play-preview-assets.html '2.3 times' '2.4 times' 'ratio multiplier changes'
changed_rule play-preview-assets.html '16:9' '16:10' 'aspect ratio changes'
changed_rule apple-version-info.html 'Between 2' 'Between 3' 'lower character bound changes'
changed_rule apple-version-info.html 'Name: 30 characters</p><p>Description: 80' 'Name: 80 characters</p><p>Description: 30' 'paragraph fields swap limits'
changed_rule apple-version-info.html 'Caption: Between 2 and 30 characters</td>
<td>Summary: 80 characters' 'Caption: 80 characters</td>
<td>Summary: Between 2 and 30 characters' 'table cells swap limits'
changed_rule apple-upcoming-requirements.html 'mandatory June' 'mandatory July' 'second deadline changes under the same heading'
changed_rule apple-upcoming-requirements.html 'mandatory June' 'optional June' 'milestone wording changes'
changed_rule fastlane-screenshots.rb '[1170,2532]' '[1179,2556]' 'symbol-label display changes size'
changed_rule fastlane-supply.rb '%w|icon featureGraphic|' '%w|icon|' 'pipe-delimited Ruby list changes'
changed_rule fastlane-supply.rb '%w(title short_description)' '%w(short_description title)' 'constant retains complete ordered value'

it "a device heading survives prose inside an article or a labelled list item"
cat > "$area/contexts.html" <<'HTML'
<article><h2>Tablet</h2><p>Required size is 1200x1800.</p></article>
<ul><li><p>Phone</p><p>Required size is 1080x1920.</p></li></ul>
HTML
run_drift extract apple-screenshots "$area/contexts.html"
assert_contains "$out" 'Tablet / Required size is :: 1200x1800'
assert_contains "$out" 'Phone / Required size is :: 1080x1920'

it "repeated orientation labels retain their device row"
cat > "$area/contexts.html" <<'HTML'
<table><tr><th>Phone A</th><td>Portrait: 1170x2532</td></tr>
<tr><th>Phone B</th><td>Portrait: 1170x2532</td></tr></table>
HTML
run_drift extract apple-screenshots "$area/contexts.html"
assert_contains "$out" 'Phone A / Portrait :: 1170x2532'
assert_contains "$out" 'Phone B / Portrait :: 1170x2532'

it "row and item labels keep their heading and each inline orientation"
cat > "$area/contexts.html" <<'HTML'
<h2>Artwork</h2>
<table><tr><th>Phone</th><td>Portrait: 1170x2532</td></tr></table>
<li><p>Tablet</p><p>Portrait: 2048x2732</p><p>Landscape: 2732x2048</p></li>
HTML
run_drift extract apple-screenshots "$area/contexts.html"
assert_contains "$out" 'Artwork / Phone / Portrait :: 1170x2532'
assert_contains "$out" 'Artwork / Tablet / Portrait :: 2048x2732'
assert_contains "$out" 'Artwork / Tablet / Landscape :: 2732x2048'

it "nested lists retain the nearest device label"
echo '<ul><li>Devices<ul><li><p>Tablet</p><p>1200x1800</p></li></ul></li></ul>' > "$area/contexts.html"
run_drift extract apple-screenshots "$area/contexts.html"
assert_contains "$out" 'Tablet :: 1200x1800'

it "an outer device label scopes values in unlabelled nested items"
echo '<h2>Sizes</h2><li>Phone<ul><li>Portrait: 1170x2532</li><li>Landscape: 2532x1170</li></ul></li>' > "$area/contexts.html"
run_drift extract apple-screenshots "$area/contexts.html"
assert_contains "$out" 'Sizes / Phone / Portrait :: 1170x2532'
assert_contains "$out" 'Sizes / Phone / Landscape :: 2532x1170'

it "inline field labels can introduce limits without a colon"
echo '<h2>Metadata</h2><p><b>Name</b> (30 characters)</p><p><b>Subtitle</b> (30 characters)</p>' > "$area/fields.html"
run_drift extract apple-app-info "$area/fields.html"
assert_contains "$out" 'Name :: 30 characters'
assert_contains "$out" 'Subtitle :: 30 characters'

it "deadline context includes words following a standalone date"
echo '<li><h3>SDK</h3><time>June 2027</time><p>Beta starts</p></li>' > "$area/date-first.html"
run_drift extract apple-upcoming-requirements "$area/date-first.html"
assert_contains "$out" 'SDK :: June 2027'
assert_contains "$out" 'Beta starts'

it "display names and constant-keyed hash values are facts"
cat > "$pages/fastlane-screenshots.rb" <<'RB'
IOS_35 = "iOS-3.5-in"
IOS_40 = 'iOS-4-in'.freeze
WATCH = 'Series #3' # device name
display_names = { DisplayType::IOS_35 => "iPhone 3.5", DisplayType::IOS_40 => IOS_40, DisplayType::WATCH => ["watch", "watchOS"] }
RB
expect_digest fastlane-screenshots.rb '["DisplayType::IOS_35 :: \"iPhone 3.5\"","DisplayType::IOS_40 :: IOS_40","DisplayType::WATCH :: [\"watch\",\"watchOS\"]","IOS_35 :: \"iOS-3.5-in\"","IOS_40 :: \"iOS-4-in\"","WATCH :: \"Series #3\""]'
cp "$ROOT/tests/fixtures/drift/fastlane-screenshots.rb" "$pages/"

it "unsupported Ruby declarations leave other literal facts available"
echo 'lookup = { generated_size => DisplayType::IOS_61 }' >> "$pages/fastlane-screenshots.rb"
echo 'sizes = { IOS_70: [[100,200], computed] }' >> "$pages/fastlane-screenshots.rb"
echo 'METADATA_FIELDS = build_fields()' >> "$pages/fastlane-supply.rb"
check_pages
assert_eq 0 "$rc"
cp "$ROOT/tests/fixtures/drift/fastlane-screenshots.rb" "$ROOT/tests/fixtures/drift/fastlane-supply.rb" "$pages/"

it "dated facts include at most eight words on either side across paragraph boundaries"
cat > "$area/window.html" <<'HTML'
<li><h3>SDK</h3><p>Before one two three four five six seven eight</p><time>June 2027</time>
<p>nine ten eleven twelve thirteen fourteen fifteen sixteen After</p></li>
HTML
run_drift extract apple-upcoming-requirements "$area/window.html"
assert_contains "$out" 'SDK :: June 2027'
assert_contains "$out" 'one two three four five six seven eight'
assert_contains "$out" 'nine ten eleven twelve thirteen fourteen fifteen sixteen'
before="$out"
sed -e 's/Before/Changed introduction/' -e 's/After/Changed ending/' "$area/window.html" > "$area/edited.html"
run_drift extract apple-upcoming-requirements "$area/edited.html"
assert_eq "$before" "$out"

it "distant edits in a dated paragraph without a heading leave the digest unchanged"
echo '<li>Old one two three four five six seven eight June 2027 nine ten eleven twelve thirteen fourteen fifteen sixteen End</li>' > "$area/window.html"
run_drift extract apple-upcoming-requirements "$area/window.html"
assert_eq 0 "$rc"
before="$out"
sed 's/Old/Revised/' "$area/window.html" > "$area/edited.html"
run_drift extract apple-upcoming-requirements "$area/edited.html"
assert_eq "$before" "$out"

it "a deeply nested baseline is a problem and later sources still run"
python3 -c 'print("[" * 2000 + "]" * 2000)' > "$digests/apple-screenshots.json"
check_pages
assert_eq 2 "$rc"
assert_contains "$out" 'apple-screenshots: problem'
assert_contains "$out" 'fastlane-languages: unchanged'
assert_not_contains "$out" 'Traceback'
cp "$area/first/apple-screenshots.json" "$digests/"

it "check and update confine digests to the kit or explicit test directory"
cp -R "$SKILL_DIR" "$area/kit"
outside="$area/outside"
cp -R "$digests" "$outside"
ln -s "$outside" "$LK_DRIFT_TEST_ROOT/link"
for command in check update; do
  for path in "$outside" "$LK_DRIFT_TEST_ROOT/../outside" "$LK_DRIFT_TEST_ROOT/link"; do
    run_drift "$command" --pages "$pages" --digests "$path"
    assert_eq 2 "$rc"
  done
  (unset LK_DRIFT_TEST_ROOT
   python3 -I -B "$script" "$command" --pages "$pages" --digests "$digests") >/dev/null 2>&1
  assert_eq 2 "$?"
done
for command in update check; do
  python3 -I -B "$area/kit/scripts/specs/drift.py" "$command" --pages "$pages" >/dev/null
  assert_eq 0 "$?"
done
mv "$area/kit/specs/digests" "$area/kit-baselines"
ln -s "$area/kit-baselines" "$area/kit/specs/digests"
for command in check update; do
  python3 -I -B "$area/kit/scripts/specs/drift.py" "$command" --pages "$pages" >/dev/null 2>&1
  assert_eq 2 "$?"
done

it "a symlinked baseline cannot read outside the selected directory"
mv "$digests/apple-screenshots.json" "$area/real.json"
ln -s "$area/real.json" "$digests/apple-screenshots.json"
check_pages
assert_eq 2 "$rc"
assert_contains "$out" 'apple-screenshots: problem'
assert_contains "$out" 'fastlane-languages: unchanged'
rm "$digests/apple-screenshots.json"
mv "$area/real.json" "$digests/apple-screenshots.json"

it "a computed suffix cannot be mistaken for a complete list"
echo 'METADATA_FIELDS = ["title"] + extra' > "$pages/fastlane-supply.rb"
check_pages
assert_eq 2 "$rc"
assert_contains "$out" 'fastlane-supply: problem'
cp "$ROOT/tests/fixtures/drift/fastlane-supply.rb" "$pages/"

it "fetched field text has no terminal control characters in the report"
printf '<h2>##[warning]field\033[31m</h2><p>7 characters</p>\n' > "$pages/apple-app-info.html"
check_pages
assert_eq 1 "$rc"
assert_contains "$out" '##[warning]field'
assert_not_contains "$out" "$(printf '\033')"
cp "$ROOT/tests/fixtures/drift/apple-app-info.html" "$pages/"

it "check names added and removed facts per source"
echo '<p>1290 x 2796</p>' > "$pages/apple-screenshots.html"
echo '<article><h3>New SDK</h3><time>May 2028</time></article>' >> "$pages/apple-upcoming-requirements.html"
check_pages
assert_eq 1 "$rc"
assert_contains "$out" '+ Page :: 1290x2796'
assert_contains "$out" '- Screenshot sizes :: 1284x2778'
assert_contains "$out" '- Screenshot sizes :: 2778x1284'
assert_contains "$out" '+ New SDK :: May 2028'

it "zero facts and missing pages take priority over changes"
echo '<script>const ignored = "512 x 512"</script>' > "$pages/play-preview-assets.html"
check_pages
assert_eq 2 "$rc"
assert_contains "$out" 'play-preview-assets: problem'
assert_contains "$out" 'zero facts'
assert_not_contains "$out" 'play-preview-assets: unchanged'
rm "$pages/fastlane-languages.rb"
check_pages
assert_eq 2 "$rc"
assert_contains "$out" 'fastlane-languages: problem'
assert_not_contains "$out" 'fastlane-languages: unchanged'
echo 'ALL_LANGUAGES = build_list()' > "$pages/fastlane-languages.rb"
it "an incomplete update writes successful sources and preserves each failed baseline"
update_pages
assert_eq 2 "$rc"
assert_contains "$out" 'play-preview-assets: problem'
assert_contains "$out" 'fastlane-languages: problem'
assert_contains "$out" 'apple-screenshots: updated'
assert_contains "$(cat "$digests/apple-screenshots.json")" '1290x2796'
for id in play-preview-assets fastlane-languages; do
  cmp -s "$digests/$id.json" "$area/first/$id.json" && pass || fail "$id baseline changed"
done

it "update accepts reviewed changes into an existing baseline"
cp "$ROOT/tests/fixtures/drift/play-preview-assets.html" "$ROOT/tests/fixtures/drift/fastlane-languages.rb" "$pages/"
update_pages
assert_eq 0 "$rc"
assert_contains "$(cat "$digests/apple-screenshots.json" 2>/dev/null)" '1290x2796'
check_pages
assert_eq 0 "$rc"

it "urllib fetch and redirect policy works without network access"
python3 -I -B "$ROOT/tests/unit/drift_fetch.py" && pass || fail "fetch policy"

it "malformed HTML identifies the source as a parse problem"
echo '<![not-a-section]>' > "$area/broken.html"
run_drift extract apple-screenshots "$area/broken.html"
assert_eq 2 "$rc"
assert_contains "$out" 'apple-screenshots: problem'
assert_not_contains "$out" 'Traceback'

it "computed Ruby expressions and unrelated constants cannot masquerade as literal data"
cat > "$area/computed.rb" <<'RB'
ALL_LANGUAGES = [*Language::CODES]
IMAGES_TYPES = %w(icon)
RB
run_drift extract fastlane-languages "$area/computed.rb"
assert_eq 2 "$rc"
assert_contains "$out" 'fastlane-languages: problem'

it "weekly workflow can update one issue with only its built-in token"
workflow="$ROOT/.github/workflows/drift.yml"
out="$(cat "$workflow" 2>/dev/null)"
for literal in 'workflow_dispatch:' 'cron:' 'contents: read' 'issues: write' 'drift.py check --fetch' 'gh issue list' "--author 'github-actions[bot]'" 'gh issue create' 'gh issue edit' '.title == "Store rules drift detected"' '--body-file'; do
  assert_contains "$out" "$literal"
done
pin="$(sed -n 's/.*uses: \(actions\/checkout@[0-9a-f]*\).*/\1/p' "$ROOT/.github/workflows/tests.yml")"
assert_contains "$out" "$pin"
assert_eq 'secrets.GITHUB_TOKEN' "$(printf '%s\n' "$out" | grep -Eo 'secrets\.[[:alnum:]_]+' | sort -u)"
if printf '%s\n' "$out" | grep -Eiq 'git[[:space:]]+(commit|push)|contents: write|drift\.py update|secrets\['; then fail "unexpected write or secret"; else pass; fi

it "workflow suspends runner commands for the entire report with a fresh token"
mkdir -p "$area/bin"
cat > "$area/bin/python3" <<'SH'
#!/bin/sh
echo '  + ##[warning]fixture'
echo '::notice::fixture' >&2
exit 1
SH
chmod +x "$area/bin/python3"
sed -n '/^        run: |/,$p' "$workflow" | sed '1d; /^      - name:/,$d; s/^          //' > "$area/compare.sh"
previous=''
for attempt in 1 2; do
  log="$(RUNNER_TEMP="$area" GITHUB_OUTPUT="$area/output" PATH="$area/bin:$PATH" bash -e "$area/compare.sh")"
  token="$(printf '%s\n' "$log" | sed -n 's/^::stop-commands:://p')"
  [ -n "$token" ] && pass || fail 'missing stop token'
  assert_ne "$previous" "$token"
  assert_eq "$(printf '::stop-commands::%s\n  + ##[warning]fixture\n::notice::fixture\n::%s::' "$token" "$token")" "$log"
  assert_contains "$(cat "$area/drift.txt")" '  + ##[warning]fixture'
  previous="$token"
done

it "standalone fetch tests leave no bytecode in a clean checkout"
mkdir -p "$area/copy/tests/unit" "$area/copy/skills/listing-kit"
cp "$ROOT/tests/unit/drift_fetch.py" "$area/copy/tests/unit/"
cp -R "$SCRIPTS" "$area/copy/skills/listing-kit/"
find "$area/copy" -name __pycache__ -type d -prune -exec rm -rf {} +
python3 -I "$area/copy/tests/unit/drift_fetch.py" >/dev/null 2>&1
assert_eq 0 "$?"
assert_eq '' "$(find "$area/copy" -name __pycache__ -print)"

it "doctor reports bundled age after 120 days and keeps the verification date"
for age in 120 121; do
  date="$(python3 - "$area/kit/specs/stores.json" "$age" <<'PY'
import datetime, json, sys
from pathlib import Path
path = Path(sys.argv[1])
data = json.loads(path.read_text())
data["verified"] = (datetime.date.today() - datetime.timedelta(days=int(sys.argv[2]))).isoformat()
path.write_text(json.dumps(data))
print(data["verified"])
PY
)"
  out="$(cd "$area" && "$area/kit/bin/listing-kit" doctor "$area" 2>&1)"
  assert_contains "$out" "$date"
  if [ "$age" = 121 ]; then assert_contains "$out" 'store rules are 121 days old: update listing-kit'
  else assert_not_contains "$out" 'days old: update listing-kit'; fi
done
summary
