#!/usr/bin/env bash
source "$(dirname "$0")/../helpers.sh"
new_tempdir fixture
new_stubdir
export FL_FIXTURE="$fixture"
for tool in bash basename cat chmod cmp cp dirname find git grep head mkdir mktemp mv od python3 rm sleep sort tail touch tr uniq wc; do
  executable="$(type -P "$tool")" && [ "${executable#/}" != "$executable" ] &&
    ln -s "$executable" "$STUB_BIN/$tool" || exit 1
done
export PATH="$STUB_BIN"
export LK_TEST_FASTLANE="$STUB_BIN/fastlane"
unset APP_STORE_CONNECT_API_KEY_PATH SUPPLY_JSON_KEY LK_PUBLISH_UNVERIFIED LK_FASTLANE_TIMEOUT
export LK_SUPPORTS_IPHONE=0
app="$fixture/repo/mobile"
remote="$fixture/remote"
lk="$SKILL_DIR/bin/listing-kit"
mkdir -p "$app" "$remote/apple/screenshots" "$remote/apple/metadata/en-US"
git init -q "$fixture/repo"
printf '%s\n' '{"key":"SECRET-stub-apple-material","issuer_id":"12345678-1234-1234-1234-123456789012"}' > "$fixture/apple.json"
printf '%s\n' '{"type":"service_account","private_key":"SECRET-stub-play-material","client_email":"test@example.org"}' > "$fixture/play.json"
cat > "$STUB_BIN/fastlane" <<'PY'
#!/usr/bin/env python3
import json, os, shutil, sys
from pathlib import Path
base = Path(os.environ["FL_FIXTURE"])
args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    print(json.dumps(args), file=log)
def stall(marker):
    if (base / marker).exists():
        import subprocess
        subprocess.run([sys.executable, "-c",
            "import time,sys;from pathlib import Path;time.sleep(4);Path(sys.argv[1]).touch()",
            str(base / "orphan")], check=True)

def opt(key):
    return Path(args[args.index("--" + key) + 1])
if args == ["--version"]:
    if (base / "bad-version").exists():
        sys.exit(1)
    print("fastlane 2.242.0")
elif args[1] in ("init", "download_metadata", "download_screenshots"):
    if (base / "deny").exists():
        print("forbidden", opt("api_key_path").read_text())
        sys.exit(1)
    store = "apple" if args[0] == "deliver" else "play"
    kind = "screenshots" if args[1] == "download_screenshots" else "metadata"
    stall("hang-download")
    dest = opt(kind + "_path")
    if store == "play":
        assert not dest.exists()
    assert base / "repo" not in dest.parents
    shutil.copytree(base / "remote" / store / kind, dest, dirs_exist_ok=True)
    if (base / "reencode").exists():
        for image in dest.rglob("*.png"):
            with image.open("ab") as stream:
                stream.write(b"store encoding")
    if "recheck" in dest.parts and (base / "tamper").exists():
        extra = dest.parent.parent / "upload/metadata/en-US/subtitle.txt"
        extra.write_text("outside approved set")
    if kind == "metadata" and (base / "race").exists():
        (base / "remote/apple/metadata/en-US/name.txt").write_text("Other editor")
else:
    store = "apple" if args[0] == "deliver" else "play"
    if (base / "hang-upload").exists() or (base / "interrupt-upload").exists():
        receipt = base / "repo/mobile/.listing-kit/publish.receipt.json"
        shutil.copyfile(receipt, base / "receipt-at-launch")
    stall("hang-upload")
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
    if (base / "interrupt-upload").exists():
        import signal, subprocess, time
        subprocess.Popen([sys.executable, "-c",
                          "import sys,time;time.sleep(2);open(sys.argv[1], 'w').close()",
                          str(base / "interrupted-orphan")])
        os.kill(os.getppid(), signal.SIGINT)
        time.sleep(5)
PY
chmod +x "$STUB_BIN/fastlane"
export STUB_LOG
cat > "$STUB_BIN/bundle" <<'SH2'
#!/usr/bin/env bash
echo "bundle $* $BUNDLE_GEMFILE" >> "$STUB_LOG"
[ "$1" = exec ] && [ "$2" = fastlane ] || exit 2
shift 2
exec "$LK_TEST_FASTLANE" "$@"
SH2
chmod +x "$STUB_BIN/bundle" || exit 1
[ "$(command -v fastlane)" = "$LK_TEST_FASTLANE" ] && "$LK_TEST_FASTLANE" --version >/dev/null || exit 1
it "Git tracing is cleared before helpers invoke Git"
GIT_TRACE2_EVENT="$fixture/trace" GIT_TRACE_PACKET="$fixture/packet" "$BASH_BIN" -c '
  cd "$1" && source "$2" --suite-root "$TMPDIR" &&
    [ -z "${GIT_TRACE2_EVENT+x}${GIT_TRACE_PACKET+x}" ]
' _ "$fixture" "$HELPER_DIR/helpers.sh" && [ ! -e "$fixture/trace" ] && pass || fail "inherited Git tracing"

it "only the private stub and approved tools are reachable"
[ "$PATH" = "$STUB_BIN" ] && [ "$(command -v fastlane)" = "$STUB_BIN/fastlane" ] && pass || fail "unsafe fastlane PATH"
mkdir "$fixture/decoy"
printf '#!/bin/sh\nexit 19\n' > "$fixture/decoy/fastlane"
chmod +x "$fixture/decoy/fastlane"
PATH="$fixture/decoy:$PATH" BUNDLE_GEMFILE=fixture "$STUB_BIN/bundle" exec fastlane --version >/dev/null && pass || fail "bundle searched PATH for fastlane"
[ "$FAIL" -eq 0 ] || { summary; exit 1; }
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
assert_not_contains "$out" "12345678-1234-1234-1234-123456789012"
assert_contains "$out" "apple.json"
assert_contains "$(cat "$STUB_LOG")" "bundle exec fastlane"
assert_contains "$(cat "$STUB_LOG")" "example.apple"
assert_eq "$(python3 -c 'import os,sys;print(oct(os.stat(sys.argv[1]).st_mode & 511))' "$app/.listing-kit/local.json" 2>/dev/null)" 0o600
assert_eq "$(cat "$app/.gitignore" 2>/dev/null)" ".listing-kit/local.json"
it "failure of the informational version probe permits a documented download"
touch "$fixture/bad-version"
run_lk fastlane setup "${a[@]}" "$setup_key" "$fixture/apple.json"
assert_eq "$rc" 0
assert_contains "$out" "Read-only access confirmed"
rm "$fixture/bad-version"

it "relative credential paths may resolve outside the repository"
run_lk fastlane setup "${a[@]}" "$setup_key" ../../apple.json
assert_eq "$rc" 0
it "pull bootstraps text and keeps downloaded images separate"
run_lk pull "${a[@]}"
assert_eq "$rc" 0
assert_file "$meta/$name"
assert_file "$app/.listing-kit/remote.lock.json"
assert_eq "$(find "$app/.listing-kit/remote/apple" -name '*.png' 2>/dev/null | wc -l | tr -d ' ')" 8
assert_ne "$(test -d "$shots" && echo yes)" yes
it "pull records raw bytes for a working field missing from the download"
mkdir -p "$meta/fr-CA"
echo "Local offer" > "$meta/fr-CA/promotional_text.txt"
run_lk pull "${a[@]}"
python3 - "$app/.listing-kit/remote.lock.json" "$meta/fr-CA/promotional_text.txt" <<'PYRAW'
import hashlib, json, sys
from pathlib import Path
raw = json.loads(Path(sys.argv[1]).read_text())["stores"]["apple"]["workingBytes"]
assert raw["metadata/fr-CA/promotional_text.txt"] == hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()
PYRAW
[ "$?" -eq 0 ] && pass || fail "missing raw working hash"
rm -r "$meta/fr-CA"

it "raw working bytes protect a whitespace-only edit across pulls"
cp "$meta/$name" "$fixture/pulled-title"
printf '\n' >> "$meta/$name"
cp "$meta/$name" "$fixture/edited-title"
run_lk pull "${a[@]}"
echo "Changed remotely" > "$ra/$name"
run_lk pull "${a[@]}"
assert_eq "$rc" 1
cmp -s "$meta/$name" "$fixture/edited-title" && pass || fail "whitespace edit lost"
cp "$fixture/pulled-title" "$meta/$name"
cp "$fixture/pulled-title" "$ra/$name"

mkdir -p "$shots/en-US" "$meta/en-US" "$app/.listing-kit/flows"
echo keep > "$shots/en-US/01-hand.png"
echo flow > "$app/.listing-kit/flows/open.yaml"
cat > "$app/.listing-kit/listing.json" <<'JSON'
{"format":2,"app":{"ios":"example.apple","android":"example.play"},"platforms":{"supportsIpad":false},"locales":["en-US"],"targets":[{"id":"phone","store":"apple","state":"active","slot":"iphone-di-medium","size":[1206,2622]}],"screens":[{"id":"one","flow":".listing-kit/flows/open.yaml"}]}
JSON
cp "$app/.listing-kit/listing.json" "$fixture/saved"
cp "$meta/en-US/release_notes.txt" "$fixture/old-notes"
echo 'Staged notes' > "$meta/en-US/release_notes.txt"
cp "$meta/en-US/release_notes.txt" "$ra/en-US/release_notes.txt"
git -C "$app" add fastlane/metadata/en-US/release_notes.txt
cp "$fixture/old-notes" "$meta/en-US/release_notes.txt"
echo Remote > "$ra/$name"
echo 'local only' > "$meta/en-US/subtitle.txt"
git -C "$app" add fastlane/metadata/en-US/subtitle.txt
echo 'local conflict' > "$meta/en-US/keywords.txt"
echo 'store conflict' > "$ra/en-US/keywords.txt"
cp "$meta/en-US/marketing_url.txt" "$fixture/url" 2>/dev/null
rm "$ra/en-US/marketing_url.txt"
it "A2 rejects a conflicting plan id before contacting fastlane"
: > "$STUB_LOG"
run_lk publish --store apple --app-identifier disposable.apple --yes
assert_eq "$rc" 2
assert_contains "$out" "example.apple"
assert_contains "$out" "disposable.apple"
assert_eq "$(cat "$STUB_LOG")" ""

run_lk publish --store play --package-name disposable.play --yes
assert_eq "$rc" 2
assert_contains "$out" "example.play"
assert_contains "$out" "disposable.play"
assert_eq "$(cat "$STUB_LOG")" ""

it "three-way pull applies independent changes and preserves user work"
run_lk pull --store apple
assert_eq "$rc" 1
assert_contains "$out" conflict
assert_eq "$(cat "$meta/$name" 2>/dev/null)" Remote
assert_eq "$(cat "$meta/en-US/subtitle.txt")" "local only"
assert_eq "$(cat "$meta/en-US/keywords.txt")" "local conflict"
cmp -s "$meta/en-US/release_notes.txt" "$fixture/old-notes" && pass "unstaged edit over staged change preserved" || fail "unstaged edit lost"
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
assert_contains "$out" "APP_IPHONE_67"
assert_ne "$(test -e "$fixture/sent" && echo yes)" yes
assert_file "$app/.listing-kit/publish.approved.json"
[ ! -e "$app/.listing-kit/publish.receipt.json" ] && pass "gated preview has no upload receipt" || fail "gated preview wrote an upload receipt"

it "A1 remote-only differences alongside a title edit never propose an overwrite"
touch "$fixture/reencode"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 0
assert_contains "$out" "never published from this repo"
assert_contains "$out" "--skip_screenshots"
assert_not_contains "$out" "--overwrite_screenshots"
rm "$fixture/reencode"

it "A6 default folders and their fallback values are excluded from publish"
cp -R "$shots/en-US" "$shots/default"
cp -R "$meta/en-US" "$meta/default"
mv "$meta/en-US/promotional_text.txt" "$fixture/concrete-promo"
echo 'default-only promo' > "$meta/default/promotional_text.txt"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 0
assert_contains "$out" "default values are not sent by publish"
assert_not_contains "$out" "metadata/default/"
assert_not_contains "$out" "metadata/en-US/promotional_text.txt changed"
mv "$fixture/concrete-promo" "$meta/en-US/promotional_text.txt"
rm -r "$shots/default" "$meta/default"

export SUPPLY_JSON_KEY="$fixture/play.json"
both=(--app-identifier example.apple --package-name example.play --yes)
it "disabled multi-store publish compares both stores and sends nothing"
echo "Preview title" > "$meta/android/en-US/title.txt"
run_lk publish "${both[@]}"
assert_eq "$rc" 0
assert_contains "$out" "publishing to apple is not enabled"
assert_contains "$out" "publishing to play is not enabled"
assert_ne "$(test -e "$fixture/sent" && echo yes)" yes
cp "$remote/play/metadata/en-US/title.txt" "$meta/android/en-US/title.txt"
it "A3 rejects unscoped, mismatched and multi-store overrides"
for override in 1 apple:disposable.apple play:example.apple; do
    LK_PUBLISH_UNVERIFIED="$override" run_lk publish "${a[@]}" --yes
    assert_ne "$rc" 0
    assert_contains "$out" "LK_PUBLISH_UNVERIFIED"
done
LK_PUBLISH_UNVERIFIED=apple:example.apple run_lk publish "${both[@]}"
assert_ne "$rc" 0
assert_contains "$out" "LK_PUBLISH_UNVERIFIED"
assert_ne "$(test -e "$fixture/sent" && echo yes)" yes
export LK_PUBLISH_UNVERIFIED=apple:example.apple
it "noninteractive live publish needs approval"
run_lk publish "${a[@]}"
assert_eq "$rc" 1
it "A4 a held directory lock fails promptly"
python3 "$ROOT/tests/unit/fastlane_controls.py" lock "$lk" "$app" && pass || fail "lock contention"
for control in eof interrupt; do
    it "A4 $control at the confirmation prompt declines cleanly"
    rc=0
    out="$(python3 "$ROOT/tests/unit/fastlane_controls.py" "$control" "$lk" "$app" 2>&1)" || rc=$?
    assert_eq "$rc" 1
    assert_contains "$out" "not approved"
    assert_not_contains "$out" "Traceback"
done
it "changed remote invalidates approval before transfer"
touch "$fixture/race"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 1
assert_contains "$out" "confirm"
assert_ne "$(test -e "$fixture/sent" && echo yes)" yes
rm "$fixture/race"
it "modified approval copy invalidates the transfer"
touch "$fixture/tamper"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 1
assert_contains "$out" "approved files changed"
assert_ne "$(test -e "$fixture/sent" && echo yes)" yes
rm "$fixture/tamper"
it "A1 scoped Apple upload preserves a console edit and re-encoded images"
cp "$rs/en-US/02_recipe-detail.png" "$rs/en-US/01_recipes.png"
touch "$fixture/reencode"
: > "$STUB_LOG"
: > "$fixture/sent"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 0
assert_contains "$out" "uploads are enabled for this run by LK_PUBLISH_UNVERIFIED"
assert_eq "$(cat "$fixture/sent")" "apple $name"
assert_file "$app/.listing-kit/publish.approved.json"
assert_file "$app/.listing-kit/publish.receipt.json"
assert_contains "$(cat "$STUB_LOG")" '"--skip_screenshots"'
assert_not_contains "$(cat "$STUB_LOG")" '"--overwrite_screenshots"'
cmp -s "$rs/en-US/01_recipes.png" "$rs/en-US/02_recipe-detail.png" && pass || fail "console edit lost"
cp "$example/screenshots/en-US/01_recipes.png" "$rs/en-US/01_recipes.png"
rm "$fixture/reencode"

it "A5 publish advances the pull ancestor and preserves the next local edit"
cp "$example/metadata/$name" "$meta/$name"
run_lk pull "${a[@]}"
assert_eq "$rc" 0
assert_eq "$(cat "$meta/$name")" "$(cat "$example/metadata/$name")"
cp "$ra/$name" "$meta/$name"

it "A1 pull records the whole local locale when the store has fewer screenshot slots"
cp -R "$meta/en-US" "$meta/fr-FR"
cp -R "$meta/fr-FR" "$ra/fr-FR"
cp -R "$shots/en-US" "$shots/fr-FR"
mkdir "$rs/fr-FR"
cp "$rs/en-US/01_recipes.png" "$rs/fr-FR/"
run_lk pull "${a[@]}"
assert_eq "$rc" 0
cp "$fixture/sent" "$fixture/before-publish"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 0
cmp -s "$fixture/sent" "$fixture/before-publish" && pass || fail "unchanged locale was sent"
rm -r "$meta/fr-FR" "$ra/fr-FR" "$shots/fr-FR" "$rs/fr-FR"

play_gallery="$remote/play/metadata/en-US/images/phoneScreenshots"
mv "$play_gallery" "$fixture/remote-gallery"
it "Play title-only upload retains a console gallery that was local-only at pull"
export LK_PUBLISH_UNVERIFIED=play:example.play
run_lk pull "${p[@]}"
assert_eq "$rc" 0
mkdir "$play_gallery"
cp "$fixture/remote-gallery/02_recipe-detail.png" "$play_gallery/console.png"
echo 'New title' > "$meta/android/en-US/title.txt"
touch "$fixture/fail-play"
run_lk publish "${p[@]}" --yes
assert_eq "$rc" 1
assert_eq "$(cat "$fixture/sent")" "apple $name"
rm "$fixture/fail-play"
python3 "$ROOT/tests/unit/fastlane_controls.py" resolve-play "$lk" "$app" && pass || fail "resolve failed upload"
run_lk publish "${p[@]}" --yes
assert_eq "$rc" 0
assert_eq "$(cat "$fixture/sent")" "$(printf 'apple %s\nplay en-US/title.txt' "$name")"
for flag in skip_upload_apk skip_upload_aab skip_upload_images skip_upload_changelogs skip_upload_screenshots; do
  assert_contains "$(cat "$STUB_LOG")" "\"--$flag\""
done
rm -r "$play_gallery"
mv "$fixture/remote-gallery" "$play_gallery"
export LK_PUBLISH_UNVERIFIED=apple:example.apple
cp "$app/.listing-kit/remote.lock.json" "$fixture/pre-upload.lock"
it "unchanged Apple whitespace does not send copy; changed screenshot restores whole locale"
printf '  New name \n' > "$meta/$name"
cp "$shots/en-US/02_recipe-detail.png" "$shots/en-US/01_recipes.png"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 0
assert_contains "$out" "every screenshot set"
digest="$(python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest()[:12])' "$shots/en-US/01_recipes.png")"
assert_contains "$out" "changed $digest screenshots/en-US/01_recipes.png"
assert_contains "$out" "screenshots/en-US/02_recipe-detail.png"
assert_contains "$(cat "$STUB_LOG")" '"--overwrite_screenshots"'
assert_eq "$(grep -c '^apple en-US/.*png$' "$fixture/sent" 2>/dev/null)" 8
it "A1 receipt prevents repeat overwrite if the lock predates the successful send"
cp "$fixture/pre-upload.lock" "$app/.listing-kit/remote.lock.json"
touch "$fixture/reencode"
echo 'Another title' > "$meta/$name"
: > "$fixture/sent"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 0
assert_eq "$(cat "$fixture/sent")" "apple $name"
rm "$fixture/reencode"
it "old and unknown state formats refuse pull and preserve working edits"
for file in remote.lock.json publish.receipt.json; do
  mv "$app/.listing-kit/$file" "$fixture/saved-$file"
  for format in 1 999; do
    printf '{"format":%s,"stores":{}}\n' "$format" > "$app/.listing-kit/$file"
    run_lk pull "${a[@]}"
    assert_eq "$rc" 1
    assert_contains "$out" "delete"
    assert_contains "$out" "$file"
    assert_contains "$out" "pull again"
  done
  printf '%s\n' '{"format":2,"stores":{"apple":{"identity":{"app":"example.apple","selector":"editable version (deliver default)"},"files":{}}}}' > "$app/.listing-kit/$file"
  run_lk pull "${a[@]}"
  assert_eq "$rc" 1
  assert_contains "$out" "delete"
  assert_contains "$out" "$file"
  assert_not_contains "$out" "Traceback"
  mv "$fixture/saved-$file" "$app/.listing-kit/$file"
done
export LK_PUBLISH_UNVERIFIED=play:example.play

it "Play gallery and release-note operations isolate replacement scopes"
mkdir -p "$meta/android/en-US/changelogs"
echo notes > "$meta/android/en-US/changelogs/44.txt"
echo unrelated > "$meta/android/en-US/changelogs/45.txt"
cp "$meta/android/en-US/images/phoneScreenshots/02_recipe-detail.png" "$meta/android/en-US/images/phoneScreenshots/01_recipes.png"
: > "$fixture/sent"
mkdir -p "$remote/play/metadata/en-US/changelogs"
echo other > "$remote/play/metadata/en-US/changelogs/45.txt"
run_lk publish "${p[@]}" --version-code 44 --yes
assert_eq "$rc" 1
assert_contains "$out" "complete"
assert_eq "$(cat "$fixture/sent")" ""
rm "$remote/play/metadata/en-US/changelogs/45.txt"
echo old > "$remote/play/metadata/en-US/changelogs/44.txt"
mkdir -p "$remote/play/metadata/fr-FR/changelogs"
echo autre > "$remote/play/metadata/fr-FR/changelogs/45.txt"
run_lk publish "${p[@]}" --version-code 44 --yes
assert_eq "$rc" 1
assert_contains "$out" "fr-FR"
assert_eq "$(cat "$fixture/sent")" ""
mv "$remote/play/metadata/fr-FR/changelogs/45.txt" "$remote/play/metadata/fr-FR/changelogs/44.txt"
run_lk publish "${p[@]}" --version-code 44 --yes
assert_eq "$rc" 1
assert_contains "$out" "would clear another translation"
rm -r "$remote/play/metadata/fr-FR"
run_lk publish "${p[@]}" --version-code 44 --yes
assert_eq "$rc" 0
assert_contains "$(cat "$fixture/sent")" "changelogs/44.txt"
assert_not_contains "$(cat "$fixture/sent")" "45.txt"
assert_not_contains "$(cat "$fixture/sent")" "featureGraphic"
assert_contains "$(cat "$STUB_LOG")" '"--skip_upload_metadata"'
it "A5 the baseline contains every file sent in the Play operation"
python3 - "$app/.listing-kit" <<'PYLOCK'
import json, sys
from pathlib import Path
state = Path(sys.argv[1])
def entry(name):
    return json.loads((state / name).read_text())["stores"]["play"]
sent = entry("publish.receipt.json")["operations"][-1]["files"]
assert sent and sent.items() <= entry("remote.lock.json")["files"].items()
PYLOCK
[ "$?" = 0 ] && pass || fail "incomplete publish baseline"

it "A1 a stale download cannot repeat a completed release-note replacement"
rm "$remote/play/metadata/en-US/changelogs/44.txt"
: > "$fixture/sent"
run_lk publish "${p[@]}" --version-code 44 --yes
assert_eq "$rc" 0
assert_eq "$(cat "$fixture/sent")" ""
export LK_PUBLISH_UNVERIFIED=apple:example.apple
it "an unmapped downloaded Apple gallery blocks destructive replacement"
mkdir -p "$rs/unexpected/gallery"
cp "$rs/en-US/01_recipes.png" "$rs/unexpected/gallery/unknown.png"
cp "$shots/en-US/03_shopping.png" "$shots/en-US/01_recipes.png"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 1
assert_contains "$out" "hand-upload folder"
rm -r "$rs/unexpected"
it "B7 failed Apple overwrite explains potential loss and recovery"
touch "$fixture/fail-apple"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 1
assert_contains "$out" "gallery may now be empty"
assert_contains "$out" "App Store Connect"
rm "$fixture/fail-apple"
python3 "$ROOT/tests/unit/fastlane_controls.py" resolve "$lk" "$app" && pass || fail "resolve failed overwrite"

it "A4 a timed-out download kills the entire child group"
touch "$fixture/hang-download"
LK_FASTLANE_TIMEOUT=1 run_lk pull "${a[@]}"
assert_eq "$rc" 1
assert_contains "$out" "timed out"
rm "$fixture/hang-download"

it "A4 a timed-out upload requires a fresh review even with --yes"
touch "$fixture/hang-upload"
LK_FASTLANE_TIMEOUT=2 run_lk publish "${a[@]}" --yes
assert_eq "$rc" 1
assert_contains "$out" "outcome unknown"
assert_contains "$(cat "$fixture/receipt-at-launch")" '"status": "pending"'
assert_contains "$(cat "$fixture/receipt-at-launch")" '"manifestHash"'
rm "$fixture/hang-upload"
echo '{"apple":{"en-US":{"screenshots":{"iPhone Dynamic Island (medium display)":6}}}}' > "$app/.listing-kit/asset-plan.json"
: > "$fixture/sent"
: > "$STUB_LOG"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 1
assert_contains "$out" "outcome unknown"
assert_contains "$out" "APP_IPHONE_67"
assert_contains "$(cat "$STUB_LOG")" "download_screenshots"
assert_eq "$(cat "$fixture/sent")" ""
assert_ne "$(test -e "$fixture/orphan" && echo yes)" yes
rm "$app/.listing-kit/asset-plan.json"

it "ambiguous uploads still require interactive resolution on subsequent retries"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 1
assert_contains "$out" "--resolve apple"
it "a pending locale permits an independently approved gallery in another locale"
cp -R "$shots/en-US" "$shots/fr-FR"
cp -R "$meta/en-US" "$meta/fr-FR"
cp -R "$meta/en-US" "$ra/fr-FR"
run_lk publish "${a[@]}" --screenshots apple:fr-FR --yes
assert_eq "$(grep -c '^apple fr-FR/.*png$' "$fixture/sent")" 8
assert_not_contains "$(cat "$fixture/sent")" "apple en-US"
rm -r "$shots/fr-FR" "$meta/fr-FR" "$ra/fr-FR"
: > "$fixture/sent"
run_lk publish "${a[@]}" --resolve apple --yes
assert_ne "$rc" 0
assert_eq "$(cat "$fixture/sent")" ""
touch "$fixture/deny"
run_lk publish "${a[@]}" --yes
assert_ne "$rc" 0
assert_contains "$out" "--resolve apple"
assert_eq "$(cat "$fixture/sent")" ""
python3 "$ROOT/tests/unit/fastlane_controls.py" resolve "$lk" "$app" && pass || fail "interactive resolution with unavailable readback"
rm "$fixture/deny"

it "interrupted upload stays pending and successful readback advances its baseline"
touch "$fixture/interrupt-upload"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 130
assert_not_contains "$out" "Traceback"
assert_contains "$(cat "$fixture/receipt-at-launch")" '"status": "pending"'
rm "$fixture/interrupt-upload"
assert_eq "$(grep -c '^apple en-US/.*png$' "$fixture/sent")" 8
: > "$fixture/sent"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 0
assert_contains "$out" "matches the approved manifest"
assert_eq "$(cat "$fixture/sent")" ""
sleep 2
assert_ne "$(test -e "$fixture/interrupted-orphan" && echo yes)" yes

it "validate checks the selected asset plan before comparing"
echo '{"apple":{"en-US":{"screenshots":{"iPhone Dynamic Island (medium display)":6}}}}' > "$app/.listing-kit/asset-plan.json"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 1
assert_contains "$out" "LISTING HAS FAILURES"
rm "$app/.listing-kit/asset-plan.json"
it "publish preview validates derived headers and ignores the obsolete Apple plan"
cp "$fixture/saved" "$app/.listing-kit/listing.json"
python3 - "$app/.listing-kit/listing.json" <<'PYPLAN'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
d = json.loads(p.read_text())
d["graphics"] = {"apple": {"header-16x9": {"headline": {"en-US": "Hello"}}}}
d["platforms"]["hasWatchApp"] = True
d["targets"].append(dict(id="watch", store="apple", slot="watch", size=[422, 514],
                         state="deferred", reason="Watch runtime unavailable"))
p.write_text(json.dumps(d))
PYPLAN
fake_png "$shots/en-US/01_one_iphone-medium.png" 1206 2622
echo 'ignored' > "$app/.listing-kit/asset-plan.json"
run_lk publish --store apple
assert_eq "$rc" 1
assert_contains "$out" "planned Apple header en-US/header-16x9.png: MISSING"
assert_contains "$out" "cannot defer required screenshot class: Apple Watch"
rm "$app/.listing-kit/asset-plan.json"

it "text-only Apple preview validates the active Vision console set"
cp "$fixture/saved" "$app/.listing-kit/listing.json"
python3 - "$app/.listing-kit/listing.json" <<'PYPLAN'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
d = json.loads(p.read_text())
d["platforms"]["hasVisionApp"] = True
d["targets"].append(dict(id="vision", store="apple", slot="vision-pro", size=[3840,2160], state="active"))
p.write_text(json.dumps(d))
PYPLAN
fake_png "$app/store-assets/apple/en-US/screenshots/vision-pro/console-capture.png" 3840 2160
run_lk publish --store apple
assert_eq 0 "$rc"
assert_not_contains "$out" "no Apple Vision Pro screenshots"

it "publish preview sees native Watch evidence even with an explicit tablet flag"
cp -R "$ROOT/tests/fixtures/platforms/iphone/App.xcodeproj" "$app/"
python3 - "$app/.listing-kit/listing.json" "$app/App.xcodeproj/project.pbxproj" <<'PYPLAN'
import json, sys
from pathlib import Path
project = Path(sys.argv[2])
project.write_text(project.read_text().replace("SDKROOT = iphoneos;", "SDKROOT = iphoneos; WATCHOS_DEPLOYMENT_TARGET = 10.0;"))
p = Path(sys.argv[1])
d = json.loads(p.read_text())
d["targets"][-1] = dict(id="watch", store="apple", slot="watch", size=[422,514], state="deferred", reason="Watch later")
d["platforms"] = {"supportsIpad":False}
p.write_text(json.dumps(d))
PYPLAN
run_lk publish --store apple
assert_eq 1 "$rc"
assert_contains "$out" "cannot defer required screenshot class: Apple Watch"
remove_fixture "$app/App.xcodeproj" "$app/store-assets/apple/en-US/screenshots/vision-pro"

it "active console target protects every Apple set in its locale"
cp "$fixture/saved" "$app/.listing-kit/listing.json"
python3 - "$app/.listing-kit/listing.json" <<'PYPLAN'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d["targets"].append(dict(d["targets"][0], id="manual", upload="console"))
json.dump(d, open(p, "w"))
PYPLAN
fake_png "$app/store-assets/apple/en-US/screenshots/iphone-di-medium/manual.png" 1206 2622
fake_png "$shots/en-US/01_one_iphone-medium.png" 1206 2622
fake_png "$rs/en-US/01_remote_medium.png" 1179 2556
: > "$fixture/sent"
run_lk publish --store apple --screenshots apple:en-US --yes
[[ "$out" == *"hand-upload folder"* ]] || echo "$out"
assert_eq "$rc" 1
assert_contains "$out" "hand-upload folder"
assert_eq "$(cat "$fixture/sent")" ""
it "custom plan paths publish active screenshots and exclude explicitly held locales"
python3 - "$app/.listing-kit/listing.json" <<'PYPLAN'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d["targets"].pop()
d["targets"].append(dict(d["targets"][0], id="later", locales=["fr-FR"], state="deferred", status="held", reason="later"))
d["targets"][0]["locales"] = ["en-US"]
d["targets"].append(dict(d["targets"][0], id="held", status="held", suffix="held"))
d["locales"].append("fr-FR")
d["trees"] = {"apple":{"fastlaneDir":"ios/store","metadata":"ios/copy","screenshots":"ios/images"}}
json.dump(d, open(p, "w"))
PYPLAN
mkdir -p "$app/ios/copy" "$app/ios/images/en-US"
cp -R "$meta/en-US" "$app/ios/copy/en-US"
cp -R "$meta/en-US" "$app/ios/copy/fr-FR"
cp "$meta"/*.txt "$app/ios/copy/"
cp "$shots/en-US/01_one_iphone-medium.png" "$app/ios/images/en-US/"
rm -r "$rs/en-US"
mkdir "$rs/en-US"
cp "$app/ios/images/en-US/01_one_iphone-medium.png" "$rs/en-US/01_remote_medium.png"
mv "$app/.listing-kit/remote.lock.json" "$fixture/previous.lock"
mv "$app/.listing-kit/publish.receipt.json" "$fixture/previous.receipt"
run_lk publish --yes
assert_eq "$rc" 0
assert_contains "$out" "never published from this repo"
assert_eq "$(cat "$fixture/sent")" ""
fake_png "$rs/en-US/01_remote_medium.png" 1179 2556
run_lk publish --yes
assert_eq "$rc" 0
assert_eq "$(cat "$fixture/sent")" ""
run_lk publish --screenshots apple:en-US:APP_IPHONE_61 --yes
assert_eq "$rc" 0
assert_contains "$out" "new "
assert_contains "$(cat "$fixture/sent")" "apple en-US/01_one_iphone-medium.png"
: > "$fixture/sent"
echo 'Changed active title' > "$app/ios/copy/$name"
echo 'Held' > "$app/ios/copy/fr-FR/name.txt"
echo 'held' > "$app/ios/images/en-US/untracked.png"
run_lk publish --yes
[ "$rc" = 0 ] || echo "$out"
assert_eq "$rc" 0
assert_eq "$(cat "$fixture/sent")" "apple $name"

it "publish requires iPad screenshots when the app declares iPad support"
mv "$app/.listing-kit/listing.json" "$fixture/phone-plan.json"
python3 - "$fixture/phone-plan.json" > "$app/.listing-kit/listing.json" <<'PYPLAN'
import json, sys
with open(sys.argv[1]) as source:
    plan = json.load(source)
plan["platforms"]["supportsIpad"] = True
json.dump(plan, sys.stdout)
PYPLAN
: > "$fixture/sent"
run_lk publish --yes
assert_eq "$rc" 1
assert_contains "$out" 'no iPad 13" screenshots'
assert_eq "$(cat "$fixture/sent")" ""
mv "$fixture/phone-plan.json" "$app/.listing-kit/listing.json"

it "publish validates referenced flows before contacting the store"
echo '-----BEGIN PRIVATE KEY-----' > "$app/.listing-kit/flows/open.yaml"
n_before="$(wc -l < "$STUB_LOG")"
run_lk publish --yes
assert_eq "$rc" 1
assert_not_contains "$(tail -n +$((n_before + 1)) "$STUB_LOG")" "download_metadata"
echo flow > "$app/.listing-kit/flows/open.yaml"
it "setup verifies actual access and keeps diagnostics free of credential bytes"
touch "$fixture/deny"
run_lk fastlane setup --store apple
assert_eq "$rc" 1
assert_contains "$out" "forbidden"
assert_not_contains "$out" "SECRET-stub-apple-material"
rm "$fixture/deny"
rm "$app/.listing-kit/listing.json"
it "credential-bearing source is rejected before the listing validator sees the upload view"
cp "$meta/en-US/description.txt" "$fixture/description"
printf '%s\n' '-----BEGIN PRIVATE KEY-----' > "$meta/en-US/description.txt"
run_lk publish "${a[@]}" --yes
assert_eq "$rc" 1
assert_contains "$out" "Credential-like content"
assert_not_contains "$out" "listing-kit validating"
mv "$fixture/description" "$meta/en-US/description.txt"
it "repo-wide scan finds even ignored unrelated credential files"
touch "$fixture/repo/elsewhere.p8"
run_lk pull "${p[@]}"
assert_eq "$rc" 1
rm "$fixture/repo/elsewhere.p8"
cp "$fixture/play.json" "$fixture/repo/extensionless"
run_lk pull "${a[@]}"
assert_eq "$rc" 1
rm "$fixture/repo/extensionless"
cp "$fixture/play.json" "$fixture/repo/renamed.json"
run_lk pull "${a[@]}"
assert_eq "$rc" 1
assert_not_contains "$(cat "$STUB_LOG" "$fixture/console")" SECRET-stub
assert_not_contains "$(cat "$fixture/console")" "test@example.org"
it "missing fastlane returns installation and manual instructions"
printf '#!/bin/sh\nexit 127\n' > "$STUB_BIN/fastlane"
rm "$fixture/repo/renamed.json"
run_lk fastlane setup "${a[@]}"
assert_eq "$rc" 3
assert_contains "$out" "install"
assert_contains "$out" "scripts/handoff/handoff.py"
it "offline CI contract exercises the option inventory without store keys"
contract="$(python3 "$ROOT/tests/contract/fastlane_cases.py" 2>/dev/null)" || contract=""
assert_contains "$contract" "overwrite_screenshots"
assert_contains "$contract" "skip_upload_changelogs"
assert_file "$ROOT/tests/contract/fastlane.rb"
assert_file "$ROOT/.github/workflows/fastlane.yml"
it "secret scan standalone mode catches extensionless repository keys"
cp "$fixture/play.json" "$fixture/repo/extensionless"
rc=0
bash "$SCRIPTS/lib/secret-scan.sh" --store-credentials "$fixture/repo" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" 1
summary
