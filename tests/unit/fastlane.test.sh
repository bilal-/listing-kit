#!/usr/bin/env bash
source "$(dirname "$0")/../helpers.sh"
new_tempdir fixture
new_stubdir
export FL_FIXTURE="$fixture"
export PATH="$STUB_BIN:$PATH"
unset APP_STORE_CONNECT_API_KEY_PATH SUPPLY_JSON_KEY LK_PUBLISH_UNVERIFIED
export LK_SUPPORTS_IPHONE=0
app="$fixture/repo/mobile"
remote="$fixture/remote"
lk="$SCRIPTS/listing-kit"
mkdir -p "$app" "$remote/apple/screenshots" "$remote/apple/metadata/en-US"
git init -q "$fixture/repo"
printf '%s\n' '{"key":"SECRET-stub-apple-material","issuer_id":"issuer"}' > "$fixture/apple.json"
printf '%s\n' '{"type":"service_account","private_key":"SECRET-stub-play-material","client_email":"test@example.org"}' > "$fixture/play.json"
cat > "$STUB_BIN/fastlane" <<'PY'
#!/usr/bin/env python3
import json, os, shutil, sys
from pathlib import Path
base = Path(os.environ["FL_FIXTURE"])
args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    print(json.dumps(args), file=log)
def opt(key):
    return Path(args[args.index("--" + key) + 1])
if args == ["--version"]:
    print("fastlane 2.242.0")
elif args[1] in ("init", "download_metadata", "download_screenshots"):
    store = "apple" if args[0] == "deliver" else "play"
    kind = "screenshots" if args[1] == "download_screenshots" else "metadata"
    dest = opt(kind + "_path")
    if store == "play":
        assert not dest.exists()
    assert base / "repo" not in dest.parents
    shutil.copytree(base / "remote" / store / kind, dest, dirs_exist_ok=True)
    if kind == "metadata" and (base / "race").exists():
        (base / "remote/apple/metadata/en-US/name.txt").write_text("Other editor")
else:
    store = "apple" if args[0] == "deliver" else "play"
    if (base / ("fail-" + store)).exists():
        sys.exit(1)
    dest = base / "remote" / store
    for kind in ("metadata", "screenshots"):
        if "--" + kind + "_path" in args:
            for path in opt(kind + "_path").rglob("*"):
                if path.is_file():
                    rel = path.relative_to(opt(kind + "_path"))
                    with open(base / "sent", "a") as log:
                        print(store, rel, file=log)
                    (dest / kind / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, dest / kind / rel)
PY
chmod +x "$STUB_BIN/fastlane"
export STUB_LOG
cat > "$STUB_BIN/bundle" <<'SH2'
#!/usr/bin/env bash
echo "bundle $* $BUNDLE_GEMFILE" >> "$STUB_LOG"
shift
exec "$@"
SH2
chmod +x "$STUB_BIN/bundle"
run_lk() {
  rc=0
  out="$(cd "$app" && "$lk" "$@" 2>&1 </dev/null)" || rc=$?
  printf '%s\n' "$out" >> "$fixture/console"
}
a=(--store apple --app-identifier example.apple)
p=(--store play --package-name example.play)
setup_key=--apple-api-key-path
name='en-US/name.txt'
meta="$app/fastlane/metadata"
shots="$app/fastlane/screenshots"
ra="$remote/apple/metadata"
rs="$remote/apple/screenshots"
example="$ROOT/examples/expo-recipe-box/fastlane"
cp -R "$example/metadata/." "$ra/"
rm -rf "$ra/android"
cp -R "$example/screenshots/." "$rs/"
it "setup refuses an in-repository credential (even above app root)"
cp "$fixture/apple.json" "$fixture/repo/k.json"
run_lk fastlane setup "${a[@]}" "$setup_key" "$fixture/repo/k.json"
assert_eq "$rc" 1
assert_contains "$out" "move"
rm "$fixture/repo/k.json"
it "setup checks selected app, pins Gemfile and stores only a private path"
echo 'gem "fastlane"' > "$app/Gemfile"
run_lk fastlane setup "${a[@]}" "$setup_key" "$fixture/apple.json"
assert_eq "$rc" 0
assert_contains "$out" "2.242.0"
assert_contains "$(cat "$STUB_LOG")" "bundle exec fastlane"
assert_contains "$(cat "$STUB_LOG")" "example.apple"
assert_eq "$(python3 -c 'import os,sys;print(oct(os.stat(sys.argv[1]).st_mode & 511))' "$app/.listing-kit/local.json" 2>/dev/null)" 0o600
assert_eq "$(cat "$app/.gitignore" 2>/dev/null)" ".listing-kit/local.json"
it "pull bootstraps text and keeps downloaded images separate"
run_lk pull "${a[@]}"
assert_eq "$rc" 0
assert_file "$meta/$name"
assert_file "$app/.listing-kit/remote.lock.json"
assert_eq "$(find "$app/.listing-kit/remote/apple" -name '*.png' 2>/dev/null | wc -l | tr -d ' ')" 8
assert_ne "$(test -d "$shots" && echo yes)" yes
mkdir -p "$shots/en-US" "$meta/en-US" "$app/.listing-kit/flows"
echo keep > "$shots/en-US/01-hand.png"
echo flow > "$app/.listing-kit/flows/open.yaml"
cat > "$app/.listing-kit/listing.json" <<'JSON'
{"format":2,"app":{"ios":"example.apple"},"locales":["en-US"],"targets":[{"id":"phone","store":"apple","state":"active","slot":"iphone-di-medium","size":[1206,2622]}],"screens":[{"id":"one","flow":".listing-kit/flows/open.yaml"}]}
JSON
cp "$app/.listing-kit/listing.json" "$fixture/saved"
echo Remote > "$ra/$name"
echo 'local only' > "$meta/en-US/subtitle.txt"
git -C "$app" add fastlane/metadata/en-US/subtitle.txt
echo 'local conflict' > "$meta/en-US/keywords.txt"
echo 'store conflict' > "$ra/en-US/keywords.txt"
cp "$meta/en-US/marketing_url.txt" "$fixture/url" 2>/dev/null
rm "$ra/en-US/marketing_url.txt"
it "three-way pull applies independent changes and preserves user work"
run_lk pull --store apple
assert_eq "$rc" 1
assert_contains "$out" conflict
assert_eq "$(cat "$meta/$name" 2>/dev/null)" Remote
assert_eq "$(cat "$meta/en-US/subtitle.txt")" "local only"
assert_eq "$(cat "$meta/en-US/keywords.txt")" "local conflict"
cmp -s "$app/.listing-kit/listing.json" "$fixture/saved" && pass "plan untouched" || fail "plan changed"
cmp -s "$meta/en-US/marketing_url.txt" "$fixture/url" && pass "missing download retained" || fail "missing download deleted"
assert_eq "$(cat "$shots/en-US/01-hand.png")" keep
assert_eq "$(cat "$app/.listing-kit/flows/open.yaml")" flow
rm "$app/.listing-kit/listing.json" "$shots/en-US/01-hand.png"
mkdir -p "$remote/play" "$app/fastlane"
cp -R "$example/metadata/android" "$remote/play/metadata"
cp -R "$example/." "$app/fastlane/"
cp -R "$example/metadata/en-US/." "$ra/en-US/"
echo 'New name' > "$meta/$name"
it "disabled preview lists exact upload command without uploading"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 0
assert_contains "$out" "publishing to apple is not enabled"
assert_contains "$out" "--skip_screenshots"
assert_ne "$(test -e "$fixture/sent" && echo yes)" yes
export LK_PUBLISH_UNVERIFIED=1
it "noninteractive live publish needs approval"
run_lk publish "${a[@]}"
assert_eq "$rc" 1
it "changed remote invalidates approval before transfer"
touch "$fixture/race"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 1
assert_contains "$out" "confirm"
assert_ne "$(test -e "$fixture/sent" && echo yes)" yes
rm "$fixture/race"
it "partial failure is resumable, text-only Apple upload contains only title"
export SUPPLY_JSON_KEY="$fixture/play.json"
echo 'New title' > "$meta/android/en-US/title.txt"
touch "$fixture/fail-play"
both=(--app-identifier example.apple --package-name example.play --yes)
run_lk publish "${both[@]}"
assert_eq "$rc" 1
assert_eq "$(cat "$fixture/sent" 2>/dev/null)" "apple $name"
assert_file "$app/.listing-kit/publish.approved.json"
assert_file "$app/.listing-kit/publish.receipt.json"
assert_contains "$(cat "$STUB_LOG")" '"--skip_screenshots"'
assert_not_contains "$(cat "$STUB_LOG")" '"--overwrite_screenshots"'
rm "$fixture/fail-play"
run_lk publish "${both[@]}"
assert_eq "$rc" 0
assert_eq "$(cat "$fixture/sent" 2>/dev/null)" "$(printf 'apple %s\nplay en-US/title.txt' "$name")"
for flag in skip_upload_apk skip_upload_aab skip_upload_images skip_upload_changelogs skip_upload_screenshots; do
  assert_contains "$(cat "$STUB_LOG")" "\"--$flag\""
done
it "unchanged Apple whitespace does not send copy; changed screenshot restores whole locale"
printf '  New name \n' > "$meta/$name"
cp "$shots/en-US/02_recipe-detail.png" "$shots/en-US/01_recipes.png"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 0
assert_contains "$out" "every screenshot set"
assert_contains "$(cat "$STUB_LOG")" '"--overwrite_screenshots"'
assert_eq "$(grep -c '^apple en-US/.*png$' "$fixture/sent" 2>/dev/null)" 8
it "Play gallery and release-note operations isolate replacement scopes"
mkdir -p "$meta/android/en-US/changelogs"
echo notes > "$meta/android/en-US/changelogs/44.txt"
echo unrelated > "$meta/android/en-US/changelogs/45.txt"
cp "$meta/android/en-US/images/phoneScreenshots/02_recipe-detail.png" "$meta/android/en-US/images/phoneScreenshots/01_recipes.png"
: > "$fixture/sent"
run_lk publish "${p[@]}" --version-code 44 --yes
assert_eq "$rc" 0
assert_contains "$(cat "$fixture/sent")" "changelogs/44.txt"
assert_not_contains "$(cat "$fixture/sent")" "45.txt"
assert_not_contains "$(cat "$fixture/sent")" "featureGraphic"
assert_contains "$(cat "$STUB_LOG")" '"--skip_upload_metadata"'
it "active console target protects every Apple set in its locale"
cp "$fixture/saved" "$app/.listing-kit/listing.json"
python3 - "$app/.listing-kit/listing.json" <<'PYPLAN'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d["targets"].append(dict(d["targets"][0], id="manual", upload="console"))
json.dump(d, open(p, "w"))
PYPLAN
fake_png "$shots/en-US/01_one_iphone-di-medium.png" 1206 2622
: > "$fixture/sent"
run_lk publish --store apple --yes
assert_eq "$rc" 1
assert_contains "$out" "hand-upload folder"
assert_eq "$(cat "$fixture/sent")" ""
rm "$app/.listing-kit/listing.json"
it "repo-wide scan finds even ignored unrelated credential files"
touch "$fixture/repo/elsewhere.p8"
run_lk pull "${p[@]}"
assert_eq "$rc" 1
rm "$fixture/repo/elsewhere.p8"
cp "$fixture/play.json" "$fixture/repo/renamed.json"
run_lk pull "${a[@]}"
assert_eq "$rc" 1
assert_not_contains "$(cat "$STUB_LOG" "$fixture/console")" SECRET-stub
it "missing fastlane returns installation and manual instructions"
printf '#!/bin/sh\nexit 127\n' > "$STUB_BIN/fastlane"
rm "$fixture/repo/renamed.json"
run_lk fastlane setup "${a[@]}"
assert_eq "$rc" 3
assert_contains "$out" "install"
assert_contains "$out" "scripts/handoff/handoff.py"
summary
