#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir area
export HOME="$area/home"
mkdir -p "$HOME" "$area/repo/apps/my app"
cd "$area/repo" || exit 1
git init -q
cli="$SKILL_DIR/bin/listing-kit"
version="$(cat "$SKILL_DIR/VERSION")"

it "GitHub workflow goes in repo root with the app's path filters and kit version"
out="$("$cli" ci init --provider github --app-root 'apps/my app' 2>&1)"
assert_eq 0 "$?"
github=.github/workflows/listing.yml
assert_file "$github"
assert_contains "$(cat "$github")" "v$version"
assert_contains "$(cat "$github")" 'apps/my app/.listing-kit/**'
it "ci init refuses an existing workflow until forced"
echo sentinel > "$github"
"$cli" ci init --provider github >/dev/null 2>&1; assert_ne 0 "$?"
assert_eq sentinel "$(cat "$github")"
"$cli" ci init --provider github --force --kit-ref v1.2.3 --app-root 'apps/my app' >/dev/null
assert_eq 0 "$?"
assert_contains "$(cat "$github")" 'v1.2.3'

it "GitLab writes a standalone pipeline then an include beside existing CI"
gitlab=.gitlab-ci.yml
"$cli" ci init --provider gitlab >/dev/null; assert_eq 0 "$?"; assert_file "$gitlab"
assert_contains "$(cat "$gitlab")" 'fastlane/**'
echo 'user pipeline' > "$gitlab"
include=listing-kit.gitlab-ci.yml
out="$("$cli" ci init --provider gitlab --app-root 'apps/my app' 2>&1)"
assert_eq 0 "$?"; assert_eq 'user pipeline' "$(cat "$gitlab")"
assert_contains "$out" 'include:'; assert_contains "$out" "$include"; assert_file "$include"
echo existing > "$include"
"$cli" ci init --provider gitlab >/dev/null 2>&1; assert_ne 0 "$?"
assert_eq existing "$(cat "$include")"
"$cli" ci init --provider gitlab --force --app-root 'apps/my app' >/dev/null
assert_eq 0 "$?"; assert_eq 'user pipeline' "$(cat "$gitlab")"

it "YAML shape, job gates, secrets and artifacts match both providers"
python3 - "$github" "$include" <<'PY'
import re
import sys
from pathlib import Path

gh, gl = (Path(p).read_text() for p in sys.argv[1:])
def top(doc, key):
    assert re.search("^" + re.escape(key) + ": *$", doc, re.M), key
for key in ("on", "jobs"):
    top(gh, key)
for key in ("listing-validate", "listing-publish-apple", "listing-publish-play"):
    top(gl, key)
for doc in (gh, gl):
    assert "\t" not in doc
    assert "live test" in doc.splitlines()[0]
    for tree in ("fastlane", "store-assets", ".listing-kit"):
        assert "apps/my app/" + tree + "/**" in doc
    for literal in ("git clone", "https://github.com/bilal-/listing-kit", "imagemagick",
                    "listing-kit validate", "listing-kit review", "listing-review.html",
                    "gem install fastlane -v 2.242.0", "listing-kit publish --store",
                    "--yes", "store-listing", ".listing-kit/publish.receipt.json", "umask 077",
                    "APP_STORE_CONNECT_API_KEY_PATH", "SUPPLY_JSON_KEY"):
        assert literal in doc, literal
    assert "set -x" not in doc and "LK_PUBLISH_UNVERIFIED" not in doc
    assert not re.search(r"\becho[^\n]*(?:_JSON|secrets\.)", doc)
for line in gh.splitlines():
    if "secrets." in line:
        assert re.fullmatch(r" +(?:APP_STORE_CONNECT_API_KEY_JSON|PLAY_SERVICE_ACCOUNT_JSON): \$\{\{ [^{}]+ \}\}", line), line
assert "workflow_dispatch:" in gh and "pull_request:" in gh and "type: choice" in gh
assert "environment: store-listing" in gh
assert "github.event_name == 'workflow_dispatch'" in gh
assert "github.event_name == 'pull_request'" in gh
assert "include-hidden-files: true" in gh
for action in ("checkout", "upload-artifact"):
    ref = re.search(r"uses: actions/" + action + r"@(\S+)", gh)[1]
    assert re.fullmatch(r"[a-f0-9]{40}", ref) or ("# TODO: Pin actions/" in gh and re.fullmatch(r"v\d+", ref))
assert "allow_failure: true" in gl  # each store is an independent manual job
assert gl.count("when: always") == 2  # include receipts even after a partial publish
assert re.search(r"Upload publish receipt\n +if: .*always\(\)", gh)
assert "merge_request_event" in gl and "when: manual" in gl
assert "CI_COMMIT_REF_PROTECTED" in gl
for doc in (gh, gl):
    assert "listing-kit capture" not in doc and "listing-kit compose" not in doc
PY
assert_eq 0 "$?"

it "publish scripts give the adapter only the selected external file, then clean up on failure"
new_stubdir
cat > "$STUB_BIN/listing-kit" <<'SH'
#!/bin/bash
set -eu
[ "$1" = publish ] && [ "$2" = --store ] && [ "$4" = --yes ] && [ "$5" = "$APP_ROOT" ] || exit 11
[ -z "${APP_STORE_CONNECT_API_KEY_JSON+x}${PLAY_SERVICE_ACCOUNT_JSON+x}" ] || exit 12
case "$3" in
  apple) key="$APP_STORE_CONNECT_API_KEY_PATH"; test -z "${SUPPLY_JSON_KEY+x}" ;;
  play) key="$SUPPLY_JSON_KEY"; test -z "${APP_STORE_CONNECT_API_KEY_PATH+x}" ;;
esac
python3 - "$key" <<'PYCHECK'
from pathlib import Path
import os, stat, sys
key = Path(sys.argv[1]).resolve()
assert Path.cwd() not in key.parents
assert stat.S_IMODE(key.stat().st_mode) == 0o600
assert key.read_bytes() == b'{"dummy":"offline fixture"}'
Path(os.environ["KEY_RECORD"]).write_text(str(key))
PYCHECK
exit 23
SH
chmod +x "$STUB_BIN/listing-kit"
# Keep GitLab's /tmp allocation inside the suite, as on a disposable runner.
MKTEMP_BIN="$(command -v mktemp)"
export MKTEMP_BIN
cat > "$STUB_BIN/mktemp" <<'SH'
#!/bin/bash
case "$2" in
  /tmp/listing-keys.*) exec "$MKTEMP_BIN" -d "$RUNNER_TEMP/${2##*/}" ;;
  *) exec "$MKTEMP_BIN" "$@" ;;
esac
SH
chmod +x "$STUB_BIN/mktemp"
export APP_ROOT='apps/my app' RUNNER_TEMP="$area/runner" KEY_RECORD="$area/key-path"
mkdir "$RUNNER_TEMP"
for provider in github gitlab; do
  file="$github"; [ "$provider" = github ] || file="$include"
  # Run the credential and publish commands from the generated YAML.
  python3 - "$file" "$area/publish" <<'PYSCRIPT'
from pathlib import Path
import sys, textwrap
lines = Path(sys.argv[1]).read_text().splitlines()
start = next(i for i, line in enumerate(lines) if line.strip() == "umask 077")
end = next(i for i in range(start, len(lines)) if "listing-kit publish --store" in lines[i])
script = textwrap.dedent("\n".join(lines[start:end+1]))
Path(sys.argv[2]).write_text(script + "\n")
PYSCRIPT
  for store in apple play; do
    rm -f "$KEY_RECORD"
    out="$(
      export STORE="$store"
      unset APP_STORE_CONNECT_API_KEY_PATH SUPPLY_JSON_KEY
      value='{"dummy":"offline fixture"}'
      if [ "$provider" = gitlab ]; then
        printf '%s' "$value" > "$area/file variable"
        value="$area/file variable"
      fi
      export APP_STORE_CONNECT_API_KEY_JSON="$value" PLAY_SERVICE_ACCOUNT_JSON="$value"
      PATH="$STUB_BIN:$PATH" bash -e "$area/publish" 2>&1
    )"; rc=$?
    assert_eq 23 "$rc" "$provider $store propagates publish failure"
    assert_not_contains "$out" 'offline fixture'
    if [ -f "$KEY_RECORD" ] && [ ! -e "$(cat "$KEY_RECORD")" ]; then pass; else fail "credential handling"; fi
  done
done

it "literal app paths containing template markers survive rendering"
mkdir -p apps/__KIT_REF__
"$cli" ci init --provider github --app-root apps/__KIT_REF__ --force >/dev/null
assert_contains "$(cat "$github")" "apps/__KIT_REF__/store-assets/**"
it "ordinary apostrophes and at signs in app names are YAML literals"
mkdir -p "apps/Kate's app @ work"
"$cli" ci init --provider github --app-root "apps/Kate's app @ work" --force >/dev/null
assert_eq 0 "$?"
assert_contains "$(cat "$github")" "'apps/Kate''s app @ work/fastlane/**'"
it "invalid provider, unsafe ref or missing app root creates no workflow"
new_tempdir clean
cd "$clean" || exit 1
for args in '--provider other' '--provider github --app-root missing' '--provider github --kit-ref ${{injection}}'; do
  "$cli" ci init $args >/dev/null 2>&1; assert_ne 0 "$?"
done
[ ! -e .github ] && pass || fail "unexpected workflow"
summary
