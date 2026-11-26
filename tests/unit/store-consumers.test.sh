#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
new_tempdir T
fake_png "$T/vision-pro.png" 3840 2160
it "imginfo uses the filename to resolve Vision and TV at the shared size"
assert_eq "Apple Vision Pro" "$(python3 -I -B "$SCRIPTS/lib/imginfo.py" "$T/vision-pro.png" | cut -f6)"
summary
