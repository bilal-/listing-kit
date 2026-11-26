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

it "fixture Git and Python ignore the invoking hook environment"
OUT="$(GIT_DIR=unexpected GIT_WORK_TREE=unexpected GIT_INDEX_FILE=unexpected PYTHONDONTWRITEBYTECODE= bash -c '
  . "$1"
  echo "${GIT_DIR-unset} ${GIT_WORK_TREE-unset} ${GIT_INDEX_FILE-unset} $PYTHONDONTWRITEBYTECODE"
' bash "$HELPER_DIR/helpers.sh")"
assert_eq 'unset unset unset 1' "$OUT"

summary
