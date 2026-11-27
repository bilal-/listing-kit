#!/usr/bin/env bash
# Scan each listing file or directory. Exit 0 if clean, 1 for credentials,
# or 2 if the scan could not complete. Diagnostics never include field values.
set -eu
exec python3 -I -B "$(dirname "${BASH_SOURCE[0]}")/secret_scan.py" "$@"
