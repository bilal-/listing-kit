#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

mktemp() {
  case "$result" in
    failure) echo "$ROOT"; return 1 ;;
    empty) return 0 ;;
    outside) echo "$ROOT" ;;
    file) echo "$HELPER_DIR/helpers.sh" ;;
  esac
}

for result in failure empty file outside; do
  it "aborts before using a fixture directory when mktemp returns $result"
  OUT="$(
    new_tempdir T
    echo "continued into fixture setup"
  )"; RC=$?
  assert_ne 0 "$RC"
  assert_not_contains "$OUT" "continued into fixture setup"
done

unset -f mktemp

it "fixture Git and Python ignore the invoking hook environment"
OUT="$(GIT_DIR=unexpected GIT_WORK_TREE=unexpected GIT_INDEX_FILE=unexpected PYTHONDONTWRITEBYTECODE= bash -c '
  . "$1"
  echo "${GIT_DIR-unset} ${GIT_WORK_TREE-unset} ${GIT_INDEX_FILE-unset} $PYTHONDONTWRITEBYTECODE"
' bash "$HELPER_DIR/helpers.sh")"
assert_eq 'unset unset unset 1' "$OUT"

it "rejects a foreign suite root"
OUT="$(bash -c '. "$0" --suite-root "$1"; echo accepted' "$HELPER_DIR/helpers.sh" "$ROOT" 2>&1)"
assert_ne 0 "$?"; assert_not_contains "$OUT" accepted
it "isolates fixture git from a disposable caller index and object store"
new_tempdir repo
git -C "$repo" init -q
echo sentinel > "$repo/sentinel"
GIT_INDEX_FILE="$repo/caller-index" git -C "$repo" add sentinel
cp "$repo/caller-index" "$repo/before"
mkdir "$repo/caller-objects"
GIT_INDEX_FILE="$repo/caller-index" GIT_OBJECT_DIRECTORY="$repo/caller-objects" GIT_CONFIG_PARAMETERS="'x.y'='z'" bash -c '
 . "$1"
 [ "$GIT_CONFIG_GLOBAL" = /dev/null ] && [ "$GIT_CONFIG_SYSTEM" = /dev/null ] && [[ "$HOME" = "$SUITE_ROOT/"* ]] || exit 1
 new_tempdir fx
 git -C "$fx" init -q && touch "$fx/file" && git -C "$fx" add file
' bash "$HELPER_DIR/helpers.sh"
assert_eq 0 "$?"
cmp -s "$repo/before" "$repo/caller-index"; assert_eq 0 "$?"
assert_eq "" "$(ls -A "$repo/caller-objects")"


it "unsets every repository-local variable advertised by this Git"
(
  cd "$repo" || exit 1
  names="$(git rev-parse --local-env-vars)" || exit 1
  for name in $names; do export "$name="; done
  export GIT_DIR="$repo/.git" GIT_COMMON_DIR="$repo/.git" GIT_WORK_TREE="$repo"
  export GIT_CONFIG_COUNT=0 GIT_CONFIG=/dev/null
  . "$HELPER_DIR/helpers.sh" --suite-root "$SUITE_ROOT"
  for name in $names; do
    [ -z "${!name+x}" ] || exit 1
  done
)
assert_eq 0 "$?"

summary
