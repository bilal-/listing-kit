#!/usr/bin/env bash
# listing-kit test runner — zero dependencies. Usage: bash tests/run.sh
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -t 1 ]; then B=$'\033[1m'; G=$'\033[32m'; R=$'\033[31m'; Z=$'\033[0m'; else B=; G=; R=; Z=; fi

total_pass=0
total_fail=0
files_errored=0
file_count=0

for f in $(find tests -name '*.test.sh' | sort); do
  file_count=$((file_count + 1))
  printf '\n%s▶ %s%s\n' "$B" "${f#tests/}" "$Z"
  out="$(bash "$f" 2>&1)"; rc=$?
  echo "$out" | grep -v '^##SUMMARY' || true

  s="$(echo "$out" | grep '^##SUMMARY' | tail -1)"
  if [ -n "$s" ]; then
    p="$(echo "$s" | sed -E 's/.*pass=([0-9]+).*/\1/')"
    fl="$(echo "$s" | sed -E 's/.*fail=([0-9]+).*/\1/')"
    total_pass=$((total_pass + p))
    total_fail=$((total_fail + fl))
  fi
  if [ "$rc" -ne 0 ] && [ -z "$s" ]; then
    printf '  %s✗ test file errored before reporting (exit %d)%s\n' "$R" "$rc" "$Z"
    files_errored=$((files_errored + 1))
  fi
done

printf '\n%s── Summary ──%s\n' "$B" "$Z"
printf '%d passed, %d failed across %d test files\n' "$total_pass" "$total_fail" "$file_count"

if [ "$total_fail" -ne 0 ] || [ "$files_errored" -ne 0 ]; then
  printf '%sFAIL%s\n' "$R" "$Z"
  exit 1
fi
printf '%sALL PASS%s\n' "$G" "$Z"
