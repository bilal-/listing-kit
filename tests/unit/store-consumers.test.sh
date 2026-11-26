#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir T
fake_png "$T/vision-pro.png" 3840 2160
it "imginfo uses the filename to resolve Vision and TV at the shared size"
assert_eq "Apple Vision Pro" "$(python3 -I -B "$SCRIPTS/lib/imginfo.py" "$T/vision-pro.png" | cut -f6)"
it "supply counts the original text and rejects invalid changelog filenames"
mkdir -p "$T/changelogs"
printf '%030d\n' 0 > "$T/title.txt"
printf entry > "$T/changelogs/latest.txt"
OUT="$(python3 -I -B "$SCRIPTS/lib/fields.py" play "$T")"
assert_contains "$OUT" "31/30 chars OVER LIMIT"
assert_contains "$OUT" "remove the trailing newline"
assert_contains "$OUT" $'FAIL\tchangelogs/latest: invalid'
it "deliver strips whitespace and requires keywords and app metadata"
printf '   ab   ' > "$T/name.txt"
OUT="$(python3 -I -B "$SCRIPTS/lib/fields.py" apple "$T")"
assert_contains "$OUT" "name: 2/30"
assert_contains "$OUT" $'FAIL\tkeywords: REQUIRED'
OUT="$(python3 -I -B "$SCRIPTS/lib/fields.py" apple-app "$T")"
assert_contains "$OUT" $'FAIL\tcopyright: REQUIRED'
assert_contains "$OUT" $'FAIL\tprimary_category: REQUIRED'
summary
