#!/usr/bin/env bash
# listing-kit test runner — zero dependencies. Usage: bash tests/run.sh
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -t 1 ]; then B=$'\033[1m'; G=$'\033[32m'; R=$'\033[31m'; Z=$'\033[0m'; else B=; G=; R=; Z=; fi

. tests/helpers.sh
total_pass=0
total_fail=0
total_skip=0
files_errored=0
required_skips=0
file_count=0

for f in $(find tests -type f \( -name '*.test.sh' -o -path 'tests/e2e/example.sh' \) | sort); do
  file_count=$((file_count + 1))
  printf '\n%s▶ %s%s\n' "$B" "${f#tests/}" "$Z"
  out="$(cd "$SUITE_ROOT" && bash "$ROOT/$f" --suite-root "$SUITE_ROOT" 2>&1)"; rc=$?
  echo "$out" | grep -v '^##SUMMARY' || true

  s="$(echo "$out" | grep '^##SUMMARY' | tail -1)"
  sk="$(printf '%s\n' "$out" | grep -c '^  skipped: ' || true)"
  total_skip=$((total_skip + sk))
  if [ "${LK_REQUIRE_RENDER:-0}" = 1 ] && [ "$sk" -gt 0 ]; then
    render_skips="$(printf '%s\n' "$out" | grep -Ec '^  skipped: (no browser|no ImageMagick|ImageMagick required)' || true)"
    if [ "$f" = tests/unit/compose.test.sh ]; then render_skips="$sk"; fi
    if [ "$render_skips" -gt 0 ]; then
      printf '  LK_REQUIRE_RENDER=1 requires the %d skipped rendering test(s) to run\n' "$render_skips"
      required_skips=$((required_skips + render_skips))
    fi
  fi
  if [ -n "$s" ]; then
    p="$(echo "$s" | sed -E 's/.*pass=([0-9]+).*/\1/')"
    fl="$(echo "$s" | sed -E 's/.*fail=([0-9]+).*/\1/')"
    total_pass=$((total_pass + p))
    total_fail=$((total_fail + fl))
  fi
  if [ -z "$s" ]; then
    printf '  %s✗ test file did not report a summary (exit %d)%s\n' "$R" "$rc" "$Z"
    files_errored=$((files_errored + 1))
  elif [ "$rc" -ne 0 ] && [ "${fl:-0}" -eq 0 ]; then
    printf '  %s✗ test file exited %d after reporting no failures%s\n' "$R" "$rc" "$Z"
    files_errored=$((files_errored + 1))
  fi
done

printf '\n%s── Summary ──%s\n' "$B" "$Z"
printf '%d passed, %d failed, %d skipped across %d test files\n' "$total_pass" "$((total_fail + required_skips))" "$total_skip" "$file_count"

if [ "$total_pass" -eq 0 ] && [ "$total_fail" -eq 0 ] && [ "$files_errored" -eq 0 ]; then
  printf '%sALL SKIPPED%s\n' "$R" "$Z"
  exit 1
fi
if [ "$((total_fail + required_skips))" -ne 0 ] || [ "$files_errored" -ne 0 ]; then
  printf '%sFAIL%s\n' "$R" "$Z"
  exit 1
fi
printf '%sALL PASS%s\n' "$G" "$Z"
