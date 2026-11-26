#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir area
cp -R "$ROOT/tests/fixtures/drift" "$area/pages"
pages="$area/pages"
digests="$area/digests"
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
assert not any("description" in u.lower() for u in s["unverified"])
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
expect_digest apple-screenshots.html '["1284x2778","2778x1284","April 2027"]'
expect_digest apple-version-info.html '["Keywords: up to 100 bytes","Promotional text: 170 characters"]'
expect_digest apple-app-info.html '["Name: 30 characters","Subtitle: 30 characters"]'
expect_digest apple-creative-assets.html '["1024x1024"]'
expect_digest play-preview-assets.html '["1024x500","512x512"]'
expect_digest play-store-listing-fields.html '["App name: 30 characters","Full description: up to 4000 characters","Short description: 80 characters","Tags: up to 5"]'
expect_digest apple-upcoming-requirements.html '["SDK requirements: September 9, 2026","Screenshot requirements: April 2027"]'
expect_digest fastlane-screenshots.rb '["APPLE_TV: 1920x1080","IOS_65: 1284x2778","IOS_65: 2778x1284"]'
expect_digest fastlane-supply.rb '["IMAGES_TYPES: featureGraphic","IMAGES_TYPES: icon","METADATA_UPLOAD_FIELDS: short_description","METADATA_UPLOAD_FIELDS: title","SCREENSHOT_TYPES: phoneScreenshots","SCREENSHOT_TYPES: sevenInchScreenshots"]'
expect_digest fastlane-languages.rb '["ALL_LANGUAGES: de-DE","ALL_LANGUAGES: en-US"]'

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

it "check names added and removed facts per source"
echo '<p>1290 x 2796</p>' > "$pages/apple-screenshots.html"
echo '<article><h3>New SDK</h3><time>May 2028</time></article>' >> "$pages/apple-upcoming-requirements.html"
check_pages
assert_eq 1 "$rc"
assert_contains "$out" '+ 1290x2796'
assert_contains "$out" '- 1284x2778'
assert_contains "$out" '- 2778x1284'
assert_contains "$out" '+ New SDK: May 2028'

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
it "an incomplete update preserves the old baselines"
update_pages
assert_eq 2 "$rc"
diff -r "$digests" "$area/first" >/dev/null 2>&1 && pass || fail 'incomplete update changed baselines'

it "urllib fetch and redirect policy works without network access"
python3 -I -B "$ROOT/tests/unit/drift_fetch.py" && pass || fail "fetch policy"

it "weekly workflow can update one issue with only its built-in token"
workflow="$ROOT/.github/workflows/drift.yml"
out="$(cat "$workflow" 2>/dev/null)"
for literal in 'workflow_dispatch:' 'cron:' 'contents: read' 'issues: write' 'drift.py check --fetch' 'gh issue list' 'gh issue create' 'gh issue edit' 'Store rules drift detected' '--body-file'; do
  assert_contains "$out" "$literal"
done
pin="$(sed -n 's/.*uses: \(actions\/checkout@[0-9a-f]*\).*/\1/p' "$ROOT/.github/workflows/tests.yml")"
assert_contains "$out" "$pin"
assert_eq 'secrets.GITHUB_TOKEN' "$(printf '%s\n' "$out" | grep -Eo 'secrets\.[[:alnum:]_]+' | sort -u)"
if printf '%s\n' "$out" | grep -Eiq 'git[[:space:]]+(commit|push)|contents: write|drift\.py update|secrets\['; then fail "unexpected write or secret"; else pass; fi

it "doctor reports bundled age after 120 days and keeps the verification date"
cp -R "$SKILL_DIR" "$area/kit"
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
