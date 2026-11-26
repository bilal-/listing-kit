#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

# Fixture Git commands must never inherit a developer's hook manager.
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
unset LISTING_KIT_HOME

SUT="$SCRIPTS/package/install-review-hook.sh"

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
rm -rf "$T"

it "installs a pre-commit hook"
make_app "Initial description"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_exec "$T/.git/hooks/pre-commit"
rm -rf "$T"

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
rm -rf "$T"

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
rm -rf "$T"

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
rm -rf "$T" "$(dirname "$WT")"

it "honors core.hooksPath"
make_app "Hooks path description"
git -C "$T" config core.hooksPath .husky
bash "$SUT" "$T" >/dev/null
assert_exec "$T/.husky/pre-commit"
rm -rf "$T"

it "rerunning does not duplicate the hook call or the app entry"
make_app "Idempotent"
bash "$SUT" "$T" >/dev/null
bash "$SUT" "$T" >/dev/null
assert_eq 1 "$(grep -c 'listing-kit review refresh' "$T/.git/hooks/pre-commit")" "one call line"
assert_eq 1 "$(grep -c '^apps+=' "$T/.git/hooks/listing-kit-review")" "one app entry"
rm -rf "$T"

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
recorded="$installs/recorded kit"
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
rm -rf "$recorded"

it "finds the highest version across installed kits after the recorded copy moves"
kit_commit agents
assert_eq 0.9.0 "$(git -C "$T" show HEAD:listing-review.html)"
for entry in '.codex/skills:0.10.0' '.gemini/extensions/listing-kit/skills:0.11.0' \
    '.cursor/skills:0.12.0' '.kiro/skills:0.13.0' \
    '.claude/plugins/cache/vendor/kit/first/skills:0.14.1' \
    '.claude/plugins/cache/vendor/kit/second/skills:0.14.2'; do
  make_kit "$test_home/${entry%:*}/listing-kit" "${entry#*:}"
  kit_commit "$entry"
  assert_eq "${entry#*:}" "$(git -C "$T" show HEAD:listing-review.html)"
done

it "warns visibly and permits the commit when no installed kit is available"
rm -rf "$test_home"
OUT="$(kit_commit missing 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_contains "$OUT" "not refreshed"
rm -rf "$T" "$installs"


it "an existing failing shell hook still blocks the commit"
make_app "Existing hook"
printf '#!/bin/sh\necho "lint failed" >&2\nfalse\n' > "$T/.git/hooks/pre-commit"; chmod +x "$T/.git/hooks/pre-commit"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane
OUT="$(git -C "$T" commit -m "listing" 2>&1)"; RC=$?
assert_ne 0 "$RC" "commit is still rejected"
assert_contains "$OUT" "lint failed"
rm -rf "$T"

it "an existing hook that ends in 'exit 0' still gets the refresh"
make_app "Exit zero hook"
printf '#!/bin/bash\nexit 0\n' > "$T/.git/hooks/pre-commit"; chmod +x "$T/.git/hooks/pre-commit"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane && git -C "$T" commit -qm "listing" >/dev/null 2>&1
assert_contains "$(git -C "$T" show HEAD:listing-review.html 2>&1)" "Exit zero hook"
rm -rf "$T"

it "a non-shell hook is left unchanged and the call to add is printed"
make_app "Python hook"
printf '#!/usr/bin/env python3\nimport sys\nsys.exit(3)\n' > "$T/.git/hooks/pre-commit"
chmod +x "$T/.git/hooks/pre-commit"
BEFORE="$(cat "$T/.git/hooks/pre-commit")"
OUT="$(bash "$SUT" "$T" 2>&1)"; RC=$?
assert_eq 0 "$RC"
assert_eq "$BEFORE" "$(cat "$T/.git/hooks/pre-commit")" "hook untouched"
assert_contains "$OUT" "listing-kit-review"
assert_exec "$T/.git/hooks/listing-kit-review"
rm -rf "$T"

it "husky 9: wires .husky/pre-commit, not the regenerated .husky/_/pre-commit"
make_app "Husky"
mkdir -p "$T/.husky/_"; printf '#!/usr/bin/env sh\n' > "$T/.husky/_/h"
printf '#!/usr/bin/env sh\n. "$(dirname "$0")/h"\n' > "$T/.husky/_/pre-commit"; chmod +x "$T/.husky/_/pre-commit"
git -C "$T" config core.hooksPath .husky/_
bash "$SUT" "$T" >/dev/null
assert_contains "$(cat "$T/.husky/pre-commit")" "listing-kit review refresh"
assert_not_contains "$(cat "$T/.husky/_/pre-commit")" "listing-kit"
assert_exec "$T/.husky/_/listing-kit-review"
rm -rf "$T"

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
rm -rf "$T"

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
rm -rf "$T"

it "deletion-only commits refresh the page"
make_app "Deletions"
printf 'Promo to delete\n' > "$T/fastlane/metadata/en-US/promotional_text.txt"
bash "$SUT" "$T" >/dev/null
git -C "$T" add fastlane && git -C "$T" commit -qm "listing" >/dev/null 2>&1
git -C "$T" rm -q fastlane/metadata/en-US/promotional_text.txt
git -C "$T" commit -qm "drop promo" >/dev/null 2>&1
assert_not_contains "$(git -C "$T" show HEAD:listing-review.html)" "Promo to delete"
rm -rf "$T"

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
rm -rf "$T"

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
rm -rf "$T"

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
git -C "$T" commit -qm "header" >/dev/null 2>&1
PAGE="$(git -C "$T" show HEAD:listing-review.html)"
assert_contains "$PAGE" 'Header Asset (manual console upload)'
assert_contains "$PAGE" '5244x2950 RGB/no-alpha'
mkdir -p "$T/.listing-kit"
printf '%s\n' '{"apple":{"en-US":{"screenshots":{"iPhone Duo":5}}}}' > "$T/.listing-kit/asset-plan.json"
git -C "$T" add .listing-kit/asset-plan.json
git -C "$T" commit -qm "plan" >/dev/null 2>&1
assert_contains "$(git -C "$T" show HEAD:listing-review.html)" 'iPhone Duo: 0 of 5 screenshots'
rm -rf "$T"

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
rm -rf "$T"

it "reinstallation replaces the permissive v0.5.0 call and runner"
make_app "Legacy call"
cat > "$T/.git/hooks/pre-commit" <<'EOF'
#!/bin/sh
r="$(git rev-parse --git-path hooks)/listing-kit-review"; [ ! -x "$r" ] || "$r" || true # listing-kit review refresh
exit 0
EOF
printf '#!/bin/bash\napps=()\napps+=(\x27\x27)\nexit 0\n' > "$T/.git/hooks/listing-kit-review"
chmod +x "$T/.git/hooks/pre-commit" "$T/.git/hooks/listing-kit-review"
bash "$SUT" "$T" >/dev/null
printf 'AKIAIOSFODNN7EXAMPLE\n' > "$T/fastlane/metadata/en-US/name.txt"
git -C "$T" add fastlane
OUT="$(git -C "$T" commit -qm "secret" 2>&1)"; RC=$?
assert_ne 0 "$RC"
assert_contains "$OUT" 'fastlane/metadata/en-US/name.txt'
if [ ! -e "$T/listing-review.html" ]; then pass "no review created"; else fail "wrote review"; fi
rm -rf "$T"

it "refuses a globally configured hooks path outside the repository before creating it"
make_app "External hooks"
new_tempdir shared
git config --file "$shared/global-config" core.hooksPath "$shared/missing/hooks"
OUT="$(GIT_CONFIG_GLOBAL="$shared/global-config" bash "$SUT" "$T" 2>&1)"; RC=$?
assert_ne 0 "$RC"
assert_contains "$OUT" 'outside'
if [ -e "$shared/missing" ]; then fail "created shared hooks directory"; else pass; fi
rm -rf "$T" "$shared"

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
rm -rf "$T" "$shared"

it "preserves a pre-existing shell hook's non-executable mode on install and reinstall"
make_app "Disabled hook"
echo '#!/bin/sh' > "$T/.git/hooks/pre-commit"
chmod 640 "$T/.git/hooks/pre-commit"
bash "$SUT" "$T" >/dev/null
bash "$SUT" "$T" >/dev/null
if [ -x "$T/.git/hooks/pre-commit" ]; then fail "enabled existing hook"; else pass; fi
rm -rf "$T"

summary
