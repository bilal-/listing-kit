#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

new_tempdir suite
mkdir "$suite/tests"
cp "$ROOT/tests/run.sh" "$ROOT/tests/helpers.sh" "$suite/tests/"
cat > "$suite/tests/render.test.sh" <<'FIXTURE'
. "$(dirname "$0")/helpers.sh"
it "render an image"
skip "$SKIP_REASON"
if [ "$RUN_ASSERTION" = 1 ]; then pass "raw capture"; fi
summary
FIXTURE

it "a suite with only skips reports ALL SKIPPED and fails"
out="$(RUN_ASSERTION=0 SKIP_REASON="no browser" LK_REQUIRE_RENDER=0 bash "$suite/tests/run.sh")"
assert_ne 0 "$?"
assert_contains "$out" "0 passed, 0 failed, 1 skipped"
assert_contains "$out" "ALL SKIPPED"

it "browserless runs count skips and strict runs fail for each missing render dependency"
for reason in "no browser" "no ImageMagick" "ImageMagick required"; do
  out="$(RUN_ASSERTION=1 SKIP_REASON="$reason" LK_REQUIRE_RENDER=0 bash "$suite/tests/run.sh")"
  assert_eq 0 "$?"
  assert_contains "$out" "1 passed, 0 failed, 1 skipped"
  out="$(RUN_ASSERTION=1 SKIP_REASON="$reason" LK_REQUIRE_RENDER=1 bash "$suite/tests/run.sh")"
  assert_ne 0 "$?"
  assert_contains "$out" "FAIL"
done

it "test commands start outside the source checkout"
git -C "$suite" init -q
cat > "$suite/tests/render.test.sh" <<'FIXTURE'
. "$(dirname "$0")/helpers.sh"
it "Git cannot discover the source checkout from the test working directory"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then fail; else pass; fi
summary
FIXTURE
out="$(bash "$suite/tests/run.sh")"
assert_eq 0 "$?" "$out"

it "an empty suite cannot report success"
rm "$suite/tests/render.test.sh"
out="$(bash "$suite/tests/run.sh")"
assert_ne 0 "$?"
assert_contains "$out" "ALL SKIPPED"
summary
