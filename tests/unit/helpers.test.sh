#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

mktemp() {
  case "$result" in
    failure) echo "$ROOT"; return 1 ;;
    empty) return 0 ;;
    file) echo "$HELPER_DIR/helpers.sh" ;;
  esac
}

for result in failure empty file; do
  it "aborts before using a fixture directory when mktemp returns $result"
  OUT="$(
    new_tempdir T
    echo "continued into fixture setup"
  )"; RC=$?
  assert_ne 0 "$RC"
  assert_not_contains "$OUT" "continued into fixture setup"
done

summary
