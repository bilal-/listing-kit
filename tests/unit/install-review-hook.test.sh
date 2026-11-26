#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

unset LISTING_KIT_HOME CODEX_HOME

SUT="$SCRIPTS/package/install-review-hook.sh"
# A caller running tests from a Git hook can export its live index and gitdir.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1

make_app() {
  new_tempdir T
  git -C "$T" init >/dev/null
  git -C "$T" config user.email "listing-kit@example.test"
  git -C "$T" config user.name "listing-kit test"
  mkdir -p "$T/fastlane/metadata/en-US"
  printf 'Hook Test\n' > "$T/fastlane/metadata/en-US/name.txt"
  printf '%s\n' "$1" > "$T/fastlane/metadata/en-US/description.txt"
}

it "exits 2 outside a git worktree"
new_tempdir T
OUT="$(GIT_CEILING_DIRECTORIES="$(dirname "$T")" bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 2 "$RC"
assert_contains "$OUT" "Not inside a git worktree"
remove_fixture "$T"

it "installs a pre-commit hook"
make_app "Initial description"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_exec "$T/.git/hooks/pre-commit"
remove_fixture "$T"

it "refreshes and stages listing-review.html when fastlane metadata is committed"
make_app "Initial description"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane
git -C "$T" commit -m "initial listing" >/dev/null
assert_contains "$(git -C "$T" show HEAD:listing-review.html)" "Initial description"

printf 'Updated description from hook\n' > "$T/fastlane/metadata/en-US/description.txt"
git -C "$T" add fastlane/metadata/en-US/description.txt
git -C "$T" commit -m "update listing copy" >/dev/null
assert_contains "$(git -C "$T" show HEAD:listing-review.html)" "Updated description from hook"
remove_fixture "$T"

it "supports app roots below the git worktree root"
new_tempdir T
git -C "$T" init >/dev/null
git -C "$T" config user.email "listing-kit@example.test"
git -C "$T" config user.name "listing-kit test"
mkdir -p "$T/apps/mobile/fastlane/metadata/en-US"
printf 'Nested Hook Test\n' > "$T/apps/mobile/fastlane/metadata/en-US/name.txt"
printf 'Nested description\n' > "$T/apps/mobile/fastlane/metadata/en-US/description.txt"
bash "$SUT" "$T/apps/mobile" >/dev/null
git -C "$T" add apps/mobile/fastlane
git -C "$T" commit -m "nested listing" >/dev/null
assert_contains "$(git -C "$T" show HEAD:apps/mobile/listing-review.html)" "Nested description"
remove_fixture "$T"

it "installs into the shared hooks dir from a linked worktree"
make_app "Worktree description"
git -C "$T" add fastlane && git -C "$T" commit -qm "initial listing"
new_tempdir WT; WT="$WT/wt"
git -C "$T" worktree add -q "$WT"
bash "$SUT" "$WT" >/dev/null
assert_exec "$T/.git/hooks/pre-commit"
printf 'Worktree update\n' > "$WT/fastlane/metadata/en-US/description.txt"
git -C "$WT" commit -qam "update from worktree" >/dev/null
assert_contains "$(git -C "$WT" show HEAD:listing-review.html)" "Worktree update"
remove_fixture "$T" "$(dirname "$WT")"

it "honors core.hooksPath"
make_app "Hooks path description"
git -C "$T" config core.hooksPath .husky
bash "$SUT" "$T" >/dev/null
assert_ne 0 "$?"
[ ! -e "$T/.husky/pre-commit" ] && pass || fail "created an in-tree hook"
remove_fixture "$T"

it "rerunning does not duplicate the hook call or the app entry"
make_app "Idempotent"
bash "$SUT" "$T" >/dev/null
bash "$SUT" "$T" >/dev/null
assert_eq 1 "$(grep -c 'listing-kit review refresh' "$T/.git/hooks/pre-commit")" "one call line"
assert_eq 1 "$(grep -c '^apps+=' "$T/.git/listing-kit-review")" "one app entry"
remove_fixture "$T"

# Each fake kit writes its version into the page so we can observe which kit
# the installed hook actually ran, without consulting the developer's home.
make_kit() {
  mkdir -p "$1/scripts/package"
  ln -s "$SCRIPTS/lib" "$1/scripts/lib"
  echo "$2" > "$1/VERSION"
  cat > "$1/scripts/package/build-review.sh" <<'BUILD'
#!/bin/bash
cat "$(dirname "$0")/../../VERSION" > "$1/listing-review.html"
BUILD
  chmod +x "$1/scripts/package/build-review.sh"
}

it "uses LISTING_KIT_HOME before the recorded installation"
make_app "Runtime discovery"
new_tempdir installs
channel="$installs/home/.codex/plugins/cache/bilal-/listing-kit"
recorded="$channel/old/skills/listing-kit"
override="$installs/override kit"
test_home="$installs/home"
make_kit "$recorded" 0.5.0
make_kit "$override" 1.0.0
cp "$SUT" "$recorded/scripts/package/"
bash "$recorded/scripts/package/install-review-hook.sh" "$T" >/dev/null
git -C "$T" add fastlane
env HOME="$test_home" LISTING_KIT_HOME="$override" git -C "$T" commit -qm override
assert_eq 1.0.0 "$(git -C "$T" show HEAD:listing-review.html)"

kit_commit() {
  echo "$1" > "$T/fastlane/metadata/en-US/description.txt"
  git -C "$T" add fastlane
  env -u LISTING_KIT_HOME HOME="$test_home" git -C "$T" commit -qm "$1"
}
it "uses the recorded kit while it exists"
make_kit "$test_home/.agents/skills/listing-kit" 0.9.0
kit_commit recorded
assert_eq 0.5.0 "$(git -C "$T" show HEAD:listing-review.html)"
remove_fixture "$recorded"

it "reports a newer sibling even while the recorded version remains"
make_kit "$channel/new/skills/listing-kit" 0.15.0
OUT="$(bash "$SUT" --status "$T" 2>&1)"; RC=$?
assert_ne 0 "$RC"
assert_contains "$OUT" outdated
it "after removal discovers only siblings in the installed channel"
remove_fixture "$recorded"
make_kit "$test_home/.claude/plugins/cache/other/listing-kit/new/skills/listing-kit" 99.0.0
kit_commit upgraded || fail "could not run sibling"
assert_eq 0.15.0 "$(git -C "$T" show HEAD:listing-review.html)"

it "blocks a relative override and an override missing VERSION"
make_kit "$T/relative" 99.0.0
echo override-test > "$T/fastlane/metadata/en-US/description.txt"
git -C "$T" add fastlane
for override in relative "$T/relative"; do
  if [ "$override" != relative ]; then rm "$T/relative/VERSION"; fi
  OUT="$(HOME="$test_home" LISTING_KIT_HOME="$override" git -C "$T" commit -qm override 2>&1)"; RC=$?
  assert_ne 0 "$RC"
  assert_contains "$OUT" '--no-verify'
done

it "blocks only listing commits when the kit disappears"
remove_fixture "$test_home"
OUT="$(kit_commit missing 2>&1)"; RC=$?
assert_ne 0 "$RC"
assert_contains "$OUT" "not refreshed"
assert_contains "$OUT" "--no-verify"
git -C "$T" reset -q HEAD
touch "$T/readme"
git -C "$T" add readme
OUT="$(HOME="$test_home" git -C "$T" commit -qm unrelated 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_eq "" "$OUT"
remove_fixture "$T" "$installs"


it "an existing failing shell hook still blocks the commit"
make_app "Existing hook"
printf '#!/bin/sh\necho "lint failed" >&2\nfalse\n' > "$T/.git/hooks/pre-commit"; chmod +x "$T/.git/hooks/pre-commit"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane
OUT="$(git -C "$T" commit -m "listing" 2>&1)"; RC=$?
assert_ne 0 "$RC" "commit is still rejected"
assert_contains "$OUT" "lint failed"
remove_fixture "$T"

it "an existing hook that ends in 'exit 0' still gets the refresh"
make_app "Exit zero hook"
printf '#!/bin/bash\nexit 0\n' > "$T/.git/hooks/pre-commit"; chmod +x "$T/.git/hooks/pre-commit"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane && git -C "$T" commit -qm "listing" >/dev/null 2>&1
assert_contains "$(git -C "$T" show HEAD:listing-review.html 2>&1)" "Exit zero hook"
remove_fixture "$T"

it "a non-shell hook is left unchanged and the call to add is printed"
make_app "Python hook"
printf '#!/usr/bin/env python3\nimport sys\nsys.exit(3)\n' > "$T/.git/hooks/pre-commit"
chmod +x "$T/.git/hooks/pre-commit"
BEFORE="$(cat "$T/.git/hooks/pre-commit")"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_ne 0 "$RC"
assert_contains "$OUT" inactive
assert_contains "$(bash "$SUT" --status "$T" 2>&1)" inactive
assert_eq "$BEFORE" "$(cat "$T/.git/hooks/pre-commit")" "hook untouched"
assert_contains "$OUT" "listing-kit-review"
assert_exec "$T/.git/listing-kit-review"
remove_fixture "$T"

it "Husky 9 gets instructions for its user hook"
make_app "Husky"
mkdir -p "$T/.husky/_"; printf '#!/usr/bin/env sh\n' > "$T/.husky/_/h"
printf '#!/usr/bin/env sh\n. "$(dirname "$0")/h"\n' > "$T/.husky/_/pre-commit"; chmod +x "$T/.husky/_/pre-commit"
git -C "$T" config core.hooksPath .husky/_
bash "$SUT" "$T" >/dev/null
assert_contains "$(bash "$SUT" --status "$T" 2>&1)" "inactive: needs one line in $T/.husky/pre-commit"
[ ! -e "$T/.husky/pre-commit" ] && pass || fail "modified Husky hook"
assert_not_contains "$(cat "$T/.husky/_/pre-commit")" "listing-kit"
assert_exec "$T/.git/listing-kit-review"
[ ! -e "$T/.husky/_/listing-kit-review" ] && pass || fail "in-tree runner"
remove_fixture "$T"

it "preserves a foreign binary pre-commit"
make_app "Binary hook"
printf 'binary\0fixture\n' > "$T/original"
cp "$T/original" "$T/.git/hooks/pre-commit"
chmod +x "$T/.git/hooks/pre-commit"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_ne 0 "$RC"
assert_contains "$OUT" inactive
if cmp -s "$T/original" "$T/.git/hooks/pre-commit"; then pass; else fail "rewrote binary hook"; fi
remove_fixture "$T"

it "migrates a listing-kit 0.2 inline hook block"
make_app "Legacy"
cat > "$T/.git/hooks/pre-commit" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

# BEGIN listing-kit review hook
listing_kit_build_review=/old/path/build-review.sh
listing_kit_app_rel=''
echo old-block
# END listing-kit review hook
EOF
bash "$SUT" "$T" >/dev/null
assert_not_contains "$(cat "$T/.git/hooks/pre-commit")" "BEGIN listing-kit"
assert_contains "$(cat "$T/.git/hooks/pre-commit")" "listing-kit review refresh"
if [ -x "$T/.git/hooks/pre-commit" ]; then fail "enabled disabled legacy hook"; else pass; fi
remove_fixture "$T"

# --- what the page is built from ---
it "the page reflects staged content, not unstaged edits"
make_app "Staged text"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane
printf 'Unstaged text\n' > "$T/fastlane/metadata/en-US/description.txt"
git -C "$T" commit -qm "listing" >/dev/null 2>&1
PAGE="$(git -C "$T" show HEAD:listing-review.html)"
assert_contains "$PAGE" "Staged text"
assert_not_contains "$PAGE" "Unstaged text"
remove_fixture "$T"

it "deletion-only commits refresh the page"
make_app "Deletions"
printf 'Promo to delete\n' > "$T/fastlane/metadata/en-US/promotional_text.txt"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane && git -C "$T" commit -qm "listing" || fail "initial commit failed"
PAGE="$(git -C "$T" show HEAD:listing-review.html)" || fail "initial page missing"
assert_contains "$PAGE" "Promo to delete"
git -C "$T" rm -q fastlane/metadata/en-US/promotional_text.txt
git -C "$T" commit -qm "drop promo" || fail "deletion commit failed"
PAGE="$(git -C "$T" show HEAD:listing-review.html)" || fail "refreshed page missing"
assert_not_contains "$PAGE" "Promo to delete"
remove_fixture "$T"

it "registers several app roots in one repo"
new_tempdir T; git -C "$T" init -q
git -C "$T" config user.email "listing-kit@example.test"; git -C "$T" config user.name "listing-kit test"
for a in apps/one apps/two; do
  mkdir -p "$T/$a/fastlane/metadata/en-US"
  printf 'App %s\n' "$a" > "$T/$a/fastlane/metadata/en-US/name.txt"
  printf 'Description of %s\n' "$a" > "$T/$a/fastlane/metadata/en-US/description.txt"
  bash "$SUT" "$T/$a" >/dev/null
done
git -C "$T" add apps && git -C "$T" commit -qm "two listings" >/dev/null 2>&1
assert_contains "$(git -C "$T" show HEAD:apps/one/listing-review.html)" "Description of apps/one"
assert_contains "$(git -C "$T" show HEAD:apps/two/listing-review.html)" "Description of apps/two"
remove_fixture "$T"

it "app dirs with glob characters are matched literally"
new_tempdir T; git -C "$T" init -q
git -C "$T" config user.email "listing-kit@example.test"; git -C "$T" config user.name "listing-kit test"
for a in "apps/mobile[1]" "apps/mobile1"; do
  mkdir -p "$T/$a/fastlane/metadata/en-US"
  printf 'Name\n' > "$T/$a/fastlane/metadata/en-US/name.txt"
  printf 'Description of %s\n' "$a" > "$T/$a/fastlane/metadata/en-US/description.txt"
done
bash "$SUT" "$T/apps/mobile[1]" >/dev/null
git -C "$T" add apps && git -C "$T" commit -qm "listings" >/dev/null 2>&1
assert_contains "$(git -C "$T" show 'HEAD:apps/mobile[1]/listing-review.html')" "Description of apps/mobile[1]"
assert_not_contains "$(git -C "$T" ls-files)" "apps/mobile1/listing-review.html" "the look-alike dir is untouched"
remove_fixture "$T"

it "header-only and plan-only commits refresh from staged assets"
new_tempdir T; git -C "$T" init -q
git -C "$T" config user.email "listing-kit@example.test"; git -C "$T" config user.name "listing-kit test"
cp -R "$ROOT/examples/expo-recipe-box/fastlane" "$T/"
fake_png "$T/fastlane/screenshots/en-US/medium.png" 1206 2622
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane && git -C "$T" commit -qm "listing" >/dev/null 2>&1
fake_png "$T/store-assets/apple/en-US/header.png" 5244 2950
git -C "$T" add store-assets
# The unstaged working copy must not leak into the committed review.
fake_png "$T/store-assets/apple/en-US/header.png" 1024 500 8 6
OUT="$(git -C "$T" commit -qm header 2>&1)"; assert_eq 0 "$?"
assert_eq "" "$OUT" "header commit refreshes without warnings"
PAGE="$(git -C "$T" show HEAD:listing-review.html)"
assert_contains "$PAGE" 'Header Asset (manual console upload)'
assert_contains "$PAGE" '5244x2950 RGB/no-alpha'
mkdir -p "$T/.listing-kit"
printf '%s\n' '{"apple":{"en-US":{"screenshots":{"iPhone Duo":5}}}}' > "$T/.listing-kit/asset-plan.json"
git -C "$T" add .listing-kit/asset-plan.json
git -C "$T" commit -qm "plan" >/dev/null 2>&1
assert_contains "$(git -C "$T" show HEAD:listing-review.html)" 'iPhone Duo: 0 of 5 screenshots'
remove_fixture "$T"

it "flow-only and app-config-only commits refresh validation from the index"
new_tempdir T; git -C "$T" init -q
git -C "$T" config user.email "listing-kit@example.test"; git -C "$T" config user.name "listing-kit test"
cp -R "$ROOT/examples/expo-recipe-box/fastlane" "$T/"
rm "$T"/fastlane/screenshots/en-US/ipad13_*.png
fake_png "$T/fastlane/screenshots/en-US/medium.png" 1206 2622
printf '%s\n' '{"expo":{"ios":{"supportsTablet":false}}}' > "$T/app.json"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane app.json && git -C "$T" commit -qm "phone listing" >/dev/null 2>&1
assert_contains "$(git -C "$T" show HEAD:listing-review.html)" 'LISTING VALID'
it "blocks credentials in staged listing inputs and leaves the previous page intact"
page_hash="$(git -C "$T" rev-parse HEAD:listing-review.html)"
for file in .listing-kit/flows/login.yaml store-assets/promo/notes.txt .listing-kit/settings/notes fastlane/metadata/en-US/description.txt app.config.js; do
  mkdir -p "$(dirname "$T/$file")"
  printf '%s%s\n' 'password: abc123' 'def456ghi789' > "$T/$file"
  git -C "$T" add -- "$file"
  echo 'safe unstaged edit' > "$T/$file"
  OUT="$(git -C "$T" commit -qm "listing edit" 2>&1)"; RC=$?
  assert_ne 0 "$RC" "blocks $file"
  assert_contains "$OUT" "$file"
  assert_not_contains "$OUT" 'abc123def456ghi789'
  assert_eq "$page_hash" "$(git -C "$T" rev-parse :listing-review.html)" "index page unchanged"
  assert_eq "$page_hash" "$(git -C "$T" hash-object listing-review.html)" "working page unchanged"
  git -C "$T" reset -q HEAD -- "$file"
done

it "app-config-only commits use the staged device support settings"
printf '%s\n' '{"expo":{"ios":{"supportsTablet":true}}}' > "$T/app.json"
git -C "$T" add app.json
# The staged configuration must win over this unstaged edit.
printf '%s\n' '{"expo":{"ios":{"supportsTablet":false}}}' > "$T/app.json"
git -C "$T" commit -qm "enable tablet" >/dev/null 2>&1
PAGE="$(git -C "$T" show HEAD:listing-review.html)"
assert_contains "$PAGE" 'app supports iPad but NO iPad screenshots'
assert_contains "$PAGE" 'LISTING HAS FAILURES'
git -C "$T" mv app.json retired-app.json
git -C "$T" commit -qm "remove app config from listing inputs" >/dev/null 2>&1
assert_contains "$(git -C "$T" show HEAD:listing-review.html)" 'LISTING VALID'
remove_fixture "$T"

it "reinstallation replaces the permissive v0.5.0 call and runner"
make_app "Legacy call"
cat > "$T/.git/hooks/pre-commit" <<'EOF'
#!/bin/sh
r="$(git rev-parse --git-path hooks)/listing-kit-review"; [ ! -x "$r" ] || "$r" || true # listing-kit review refresh
exit 0
EOF
# The runner body is the generated v0.5.0 code. Its builder path survives a
# package update, while the two installed hook files stay byte-for-byte old.
new_tempdir old_kit
make_kit "$old_kit" 0.5.0
{
  printf '#!/usr/bin/env bash\nbuild_review=%q\napps=()\napps+=(%q)\n' "$old_kit/scripts/package/build-review.sh" ''
  cat "$HELPER_DIR/fixtures/hooks/v0.5.0-runner-body"
} > "$T/.git/hooks/listing-kit-review"
chmod +x "$T/.git/hooks/pre-commit" "$T/.git/hooks/listing-kit-review"
cp "$SCRIPTS/package/build-review.sh" "$old_kit/scripts/package/"
ln -s "$SCRIPTS/validate" "$old_kit/scripts/validate"
cp "$SUT" "$old_kit/scripts/package/"
OUT="$(bash "$old_kit/scripts/package/install-review-hook.sh" --status "$T" 2>&1)"; RC=$?
assert_ne 0 "$RC"
assert_contains "$OUT" outdated
printf 'AKIAIOSFODNN7EXAMPLE\n' > "$T/fastlane/metadata/en-US/name.txt"
git -C "$T" add fastlane
git -C "$T" commit -qm "old runner permits fixture" || fail "old hook did not allow commit"
bash "$old_kit/scripts/package/install-review-hook.sh" "$T" >/dev/null || fail "migration failed"
OUT="$(bash "$old_kit/scripts/package/install-review-hook.sh" --status "$T")"; RC=$?
assert_eq 0 "$RC"
assert_eq active "$OUT"
echo 'trigger a listing commit' >> "$T/fastlane/metadata/en-US/description.txt"
git -C "$T" add fastlane
OUT="$(git -C "$T" commit -qm "secret" 2>&1)"; RC=$?
assert_ne 0 "$RC"
assert_contains "$OUT" 'fastlane/metadata/en-US/name.txt'
if [ ! -e "$T/listing-review.html" ]; then pass "no review created"; else fail "wrote a review"; fi
remove_fixture "$T"

it "refuses a globally configured hooks path outside the repository before creating it"
make_app "External hooks"
new_tempdir shared
git config --file "$shared/global-config" core.hooksPath "$shared/missing/hooks"
OUT="$(GIT_CONFIG_GLOBAL="$shared/global-config" bash "$SUT" "$T" 2>&1)"; RC=$?
assert_ne 0 "$RC"
assert_contains "$OUT" 'outside'
if [ -e "$shared/missing" ]; then fail "created shared hooks directory"; else pass; fi
remove_fixture "$T" "$shared"

it "refuses an in-repo hooks path or hook file symlinked outside"
make_app "Linked hooks"
new_tempdir shared
ln -s "$shared" "$T/linked-hooks"
git -C "$T" config core.hooksPath linked-hooks
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_ne 0 "$RC"
if [ -e "$shared/pre-commit" ]; then fail "wrote external hook"; else pass; fi
git -C "$T" config core.hooksPath .hooks
mkdir "$T/.hooks"
echo '#!/bin/sh' > "$shared/original"
for target in pre-commit listing-kit-review; do
  ln -s "$shared/original" "$T/.hooks/$target"
  OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
  assert_ne 0 "$RC"
  assert_eq '#!/bin/sh' "$(cat "$shared/original")" "preserves external $target"
  rm -f "$T/.hooks/pre-commit" "$T/.hooks/listing-kit-review"
done
remove_fixture "$T" "$shared"

it "preserves a pre-existing shell hook's non-executable mode on install and reinstall"
make_app "Disabled hook"
echo '#!/bin/sh' > "$T/.git/hooks/pre-commit"
chmod 640 "$T/.git/hooks/pre-commit"
for mode in install reinstall --status; do
  case "$mode" in
    --status) OUT="$(bash "$SUT" --status "$T" 2>&1)" ;;
    *) OUT="$(bash "$SUT" "$T" 2>&1)" ;;
  esac
  RC=$?
  assert_ne 0 "$RC"
  assert_contains "$OUT" inactive
done
if [ -x "$T/.git/hooks/pre-commit" ]; then fail "enabled existing hook"; else pass; fi
remove_fixture "$T"

it "rejects hooks in a nested repo and replaces hard-linked files atomically"
make_app "Ownership"
git -C "$T" init -q nested
git -C "$T" config core.hooksPath nested/.git/hooks
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_ne 0 "$RC"
git -C "$T" config --unset core.hooksPath
for name in pre-commit listing-kit-review; do
  echo '#!/bin/sh' > "$T/original-$name"
  chmod +x "$T/original-$name"
  ln "$T/original-$name" "$T/.git/hooks/$name"
done
bash "$SUT" "$T" >/dev/null
for name in pre-commit listing-kit-review; do
  if printf '#!/bin/sh\n' | cmp -s - "$T/original-$name"; then pass; else fail "modified hard-linked $name"; fi
done

it "isolates app-root Python names during installation, build and commit"
make_app "isolated python"
for module in re pathlib; do
  echo 'raise ImportError("app-local test module")' > "$T/$module.py"
done
(cd "$T" && bash "$SUT" .) >/dev/null || fail "installer imported app code"
(cd "$T" && bash "$SCRIPTS/package/build-review.sh" .) >/dev/null || fail "builder imported app code"
rm -f "$T/listing-review.html"
git -C "$T" add fastlane
git -C "$T" commit -qm isolated || fail "commit failed"
assert_contains "$(git -C "$T" show HEAD:listing-review.html)" "isolated python"

it "checks index blobs before checkout conversion"
make_app "blob scan"
git -C "$T" config filter.fixture.smudge 'cat >/dev/null && echo clean'
echo 'description.txt filter=fixture' > "$T/.gitattributes"
echo AKIAIOSFODNN7EXAMPLE > "$T/fastlane/metadata/en-US/description.txt"
bash "$SUT" "$T" >/dev/null
git -C "$T" add .gitattributes fastlane
OUT="$(git -C "$T" commit -qm filtered 2>&1)"; RC=$?
assert_ne 0 "$RC"
assert_contains "$OUT" 'description.txt'

it "blocks escaping links and warns on temp allocation and checkout errors"
make_app "scan failure"
bash "$SUT" "$T" >/dev/null
ln -s ../outside "$T/fastlane/link"
git -C "$T" add fastlane
OUT="$(git -C "$T" commit -qm link 2>&1)"; RC=$?
assert_ne 0 "$RC"
assert_contains "$OUT" '--no-verify'
git -C "$T" rm -qf fastlane/link
OUT="$(TMPDIR="$T/nonexistent" git -C "$T" commit -qm temp 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" 'Warning'
git -C "$T" config filter.unavailable.clean cat
git -C "$T" config filter.unavailable.smudge false
git -C "$T" config filter.unavailable.required true
echo 'description.txt filter=unavailable' > "$T/.gitattributes"
echo clean >> "$T/fastlane/metadata/en-US/description.txt"
git -C "$T" add .gitattributes fastlane
OUT="$(git -C "$T" commit -qm checkout 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" 'Warning'

it "rejects indexed private files even when clean and permits their deletion"
make_app "local policy"
bash "$SUT" "$T" >/dev/null
for name in local.json secrets.local; do
  mkdir -p "$T/.listing-kit"
  echo harmless > "$T/.listing-kit/$name"
  git -C "$T" add -f ".listing-kit/$name" || fail "could not stage private fixture"
  OUT="$(git -C "$T" commit -qm private 2>&1)"; RC=$?
  assert_ne 0 "$RC"
  assert_contains "$OUT" ".listing-kit/$name"
  git -C "$T" commit -qm fixture --no-verify || fail "could not seed tracked file"
  echo changed >> "$T/.listing-kit/$name"
  git -C "$T" add -u
  OUT="$(git -C "$T" commit -qm tracked 2>&1)"; RC=$?
  assert_ne 0 "$RC"
  git -C "$T" rm -qf ".listing-kit/$name"
  git -C "$T" commit -qm deletion || fail "could not delete private file"
done

it "checks device files under newline-containing directories and repository roots"
make_app "newlines"
bash "$SUT" "$T" >/dev/null || fail "installation failed"
dir=$'native\nproject'
mkdir -p "$T/$dir"
echo AKIAIOSFODNN7EXAMPLE > "$T/$dir/Info.plist"
git -C "$T" add "$dir"
OUT="$(git -C "$T" commit -qm plist 2>&1)"; RC=$?
assert_ne 0 "$RC"
assert_contains "$OUT" Info.plist
git -C "$T" rm -qf "$dir/Info.plist"
mv "$T" "$T"$'\n'
T="$T"$'\n'
bash "$SUT" "$T" >/dev/null || fail "installation failed"
echo AKIAIOSFODNN7EXAMPLE > "$T/Info.plist"
git -C "$T" add Info.plist
OUT="$(git -C "$T" commit -qm plist 2>&1)"; RC=$?
assert_ne 0 "$RC"
assert_contains "$OUT" Info.plist

it "permits environment references and ordinary URLs at commit time"
make_app "https://example.test/search?monkeytoken=springlaunch2026"
echo 'clientSecret: process.env.CLIENT_SECRET' > "$T/app.config.js"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane app.config.js
git -C "$T" commit -qm clean || fail "clean commit was blocked"
assert_contains "$(git -C "$T" show HEAD:listing-review.html)" 'monkeytoken=springlaunch2026'

it "scans symlink targets, permits an internal locale alias and skips gitlinks"
make_app "linked locale"
git -C "$T" add fastlane && git -C "$T" commit -qm seed
ln -s en-US "$T/fastlane/metadata/en-GB"
git -C "$T" add fastlane
git -C "$T" update-index --add --cacheinfo 160000,"$(git -C "$T" rev-parse HEAD)",fastlane/vendor
bash "$SUT" "$T" >/dev/null
OUT="$(git -C "$T" commit -qm links 2>&1)"; assert_eq 0 "$?"
assert_contains "$OUT" fastlane/vendor
assert_contains "$(git -C "$T" show HEAD:listing-review.html)" 'en-GB'
ln -s AKIAIOSFODNN7EXAMPLE "$T/fastlane/bad-target"
git -C "$T" add fastlane/bad-target
OUT="$(git -C "$T" commit -qm target 2>&1)"; assert_ne 0 "$?"
assert_contains "$OUT" fastlane/bad-target
assert_not_contains "$OUT" AKIAIOSFODNN7EXAMPLE

it "gates changed device settings and honors an exactly reviewed device blob"
make_app "device settings"
printf '{"googleMapsApiKey": "AIza%035d"}' 0 > "$T/app.json"
git -C "$T" add app.json && git -C "$T" commit -qm existing
echo 'apiKey: Env.GOOGLE_API_KEY,' > "$T/app.config.ts"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane app.config.ts
OUT="$(git -C "$T" commit -qm listing 2>&1)"; assert_eq 0 "$?"
echo ' ' >> "$T/app.json"
git -C "$T" add app.json
git -C "$T" config --add listingKit.reviewedDeviceBlob "$(git -C "$T" rev-parse :app.json) app.json"
OUT="$(git -C "$T" commit -qm allow 2>&1)"; assert_eq 0 "$?"
echo ' ' >> "$T/app.json"
git -C "$T" add app.json
OUT="$(git -C "$T" commit -qm changed 2>&1)"; assert_ne 0 "$?"
assert_contains "$OUT" app.json

it "keeps whitespace-only demo passwords and explains how to supply real ones"
make_app demo
d="$T/fastlane/metadata/review_information"
mkdir -p "$d"
printf '  \t\n' > "$d/demo_password.txt"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane && git -C "$T" commit -qm empty || fail "blocked blank demo password"
echo abc > "$d/demo_password.txt"
git -C "$T" add fastlane
OUT="$(git -C "$T" commit -qm demo 2>&1)"; assert_ne 0 "$?"
assert_contains "$OUT" "environment at upload"

it "checks the contents of an internal demo-password symlink"
git -C "$T" reset -q HEAD
echo private-demo > "$d/demo-account"
rm "$d/demo_password.txt"
ln -s demo-account "$d/demo_password.txt"
git -C "$T" add fastlane
OUT="$(git -C "$T" commit -qm link-demo 2>&1)"; assert_ne 0 "$?"
assert_contains "$OUT" "environment at upload"
OUT="$(bash "$SCRIPTS/validate/validate-listing.sh" "$T" 2>&1)"
assert_contains "$OUT" "environment at upload"

it "keeps the registered app directory above the staged path scan root"
make_app "ancestor test"
mkdir -p "$T/apps/xoxo-valentines-app"
mv "$T/fastlane" "$T/apps/xoxo-valentines-app/"
bash "$SUT" "$T/apps/xoxo-valentines-app" >/dev/null
git -C "$T" add apps
OUT="$(git -C "$T" commit -qm ancestor 2>&1)"; assert_eq 0 "$?"

it "silently passes unrelated changes without Python and names it for staged inputs"
make_app no-python
bash "$SUT" "$T" >/dev/null
new_stubdir
for cmd in bash git; do ln -s "$(command -v "$cmd")" "$STUB_BIN/$cmd"; done
touch "$T/readme"; git -C "$T" add readme
run_without_python() { (cd "$T" && PATH="$STUB_BIN" .git/hooks/pre-commit); }
OUT="$(run_without_python 2>&1)"; assert_eq 0 "$?"; assert_eq "" "$OUT"
git -C "$T" add fastlane
OUT="$(run_without_python 2>&1)"; assert_ne 0 "$?"; assert_contains "$OUT" python3

it "warns after clean scan on an ignored page or builder failure"
make_app warning
bash "$SUT" "$T" >/dev/null
echo listing-review.html > "$T/.gitignore"
git -C "$T" add fastlane .gitignore
OUT="$(git -C "$T" commit -qm ignored 2>&1)"; assert_eq 0 "$?"
assert_contains "$OUT" Warning
[ ! -e "$T/listing-review.html" ] && pass || fail "overwrote ignored page"
new_tempdir broken; make_kit "$broken" 1.0.0
echo 'exit 2' > "$broken/scripts/package/build-review.sh"
rm "$T/.gitignore"
echo updated > "$T/fastlane/metadata/en-US/name.txt"
git -C "$T" add -u
OUT="$(LISTING_KIT_HOME="$broken" git -C "$T" commit -qm failed 2>&1)"; assert_eq 0 "$?"
assert_contains "$OUT" Warning

it "warns when checkout leaves a Git LFS pointer unhydrated"
mkdir -p "$T/fastlane/screenshots"
printf 'version https://git-lfs.github.com/spec/v1\noid sha256:%064d\nsize 12345\n' 0 > "$T/fastlane/screenshots/missing.png"
git -C "$T" add fastlane
OUT="$(git -C "$T" commit -qm lfs-pointer 2>&1)"; assert_eq 0 "$?"
assert_contains "$OUT" "Warning"
assert_contains "$OUT" "missing.png"

it "still scans when the builder disappears"
rm "$broken/scripts/package/build-review.sh"
echo newer > "$T/fastlane/metadata/en-US/name.txt"
git -C "$T" add fastlane
OUT="$(LISTING_KIT_HOME="$broken" git -C "$T" commit -qm missing-builder 2>&1)"; assert_eq 0 "$?"
assert_contains "$OUT" Warning

it "leaves a symlinked hook and its target intact and prints a working wiring line"
make_app managed
mkdir "$T/scripts"; printf '#!/bin/sh\n' > "$T/scripts/pre-commit"; chmod +x "$T/scripts/pre-commit"
ln -s ../../scripts/pre-commit "$T/.git/hooks/pre-commit"
OUT="$(bash "$SUT" "$T" 2>&1)"; assert_ne 0 "$?"
assert_contains "$OUT" "inactive: needs one line in"
[ -L "$T/.git/hooks/pre-commit" ] && pass || fail "detached symlink"
assert_eq '#!/bin/sh' "$(cat "$T/scripts/pre-commit")"
printf '%s\n' "$OUT" | grep ' # listing-kit review refresh$' >> "$T/scripts/pre-commit"
assert_eq active "$(bash "$SUT" --status "$T")"


summary
