# shellcheck shell=bash
# Tiny zero-dependency assertion + stubbing library for listing-kit tests.
# Source this from a *.test.sh file, write assertions, end with `summary`.
set -uo pipefail

HELPER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HELPER_DIR/.." && pwd)"
SCRIPTS="$ROOT/skills/listing-kit/scripts"
SKILL_DIR="$ROOT/skills/listing-kit"
BASH_BIN="$(command -v bash)"   # absolute, so tests can run with a stubbed-only PATH

PASS=0
FAIL=0
CURRENT="(unnamed)"

if [ -t 1 ]; then G=$'\033[32m'; R=$'\033[31m'; B=$'\033[1m'; Z=$'\033[0m'; else G=; R=; B=; Z=; fi

it()   { CURRENT="$1"; }
pass() { PASS=$((PASS + 1)); printf '  %s✓%s %s\n' "$G" "$Z" "${1:-$CURRENT}"; }
fail() { FAIL=$((FAIL + 1)); printf '  %s✗ %s%s\n      %s\n' "$R" "$CURRENT" "$Z" "${1:-assertion failed}"; }

assert_eq()           { if [ "$1" = "$2" ];      then pass "${3:-$CURRENT}"; else fail "expected [$1] got [$2]"; fi; }
assert_ne()           { if [ "$1" != "$2" ];     then pass "${3:-$CURRENT}"; else fail "expected != [$1]"; fi; }
assert_contains()     { case "$1" in *"$2"*) pass "${3:-$CURRENT}";; *) fail "expected substring [$2] in output";; esac; }
assert_not_contains() { case "$1" in *"$2"*) fail "unexpected substring [$2]";; *) pass "${3:-$CURRENT}";; esac; }
assert_file()         { if [ -f "$1" ]; then pass "${2:-exists: $1}"; else fail "missing file: $1"; fi; }
assert_exec()         { if [ -x "$1" ]; then pass "${2:-executable: $1}"; else fail "not executable: $1"; fi; }

# JSON field readers (python3 is universally present on CI/dev machines).
json_get()      { python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2],''))" "$1" "$2"; }
json_valid()    { python3 -c "import json,sys;json.load(open(sys.argv[1]))" "$1" >/dev/null 2>&1; }
json_path()     { python3 -c "import json,sys;d=json.load(open(sys.argv[1]));exec('print('+sys.argv[2]+')')" "$1" "d$2"; }

# --- command stubbing: shim a binary onto PATH and record its invocations ---
STUB_DIRS=()
new_stubdir() { STUB_BIN="$(mktemp -d)"; STUB_LOG="$STUB_BIN/.calls"; : > "$STUB_LOG"; STUB_DIRS+=("$STUB_BIN"); }
trap 'for d in ${STUB_DIRS[@]+"${STUB_DIRS[@]}"}; do rm -rf "$d"; done' EXIT
stub() {
  local name="$1" code="${2:-0}"
  cat > "$STUB_BIN/$name" <<EOF
#!/usr/bin/env bash
echo "$name \$*" >> "$STUB_LOG"
exit $code
EOF
  chmod +x "$STUB_BIN/$name"
}
stub_log() { cat "$STUB_LOG"; }

# Print a machine-readable line for the runner and exit non-zero on any failure.
summary() {
  echo "##SUMMARY pass=$PASS fail=$FAIL"
  [ "$FAIL" -eq 0 ]
}

# --- tiny image fixtures (headers + minimal data; enough for lib/imginfo.py) ---
# fake_png <path> <w> <h> [depth=8] [colortype=2] [trns]   (pass "trns" to add a tRNS chunk)
fake_png() { mkdir -p "$(dirname "$1")"; python3 - "$@" <<'PY'
import struct, sys, zlib
p, w, h = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
depth = int(sys.argv[4]) if len(sys.argv) > 4 else 8
ct = int(sys.argv[5]) if len(sys.argv) > 5 else 2
def chunk(k, d): return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))
extra = chunk(b"tRNS", b"\0\0\0\0\0\0") if "trns" in sys.argv[6:] else b""
open(p, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ct, 0, 0, 0))
                    + extra + chunk(b"IDAT", zlib.compress(b"\0")) + chunk(b"IEND", b""))
PY
}
# fake_jpeg <path> <w> <h>   (8-bit, 3-component baseline JPEG header)
fake_jpeg() { mkdir -p "$(dirname "$1")"; python3 - "$@" <<'PY'
import struct, sys
p, w, h = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
sof = struct.pack(">BHHB", 8, h, w, 3) + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01"
open(p, "wb").write(b"\xff\xd8\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof + b"\xff\xd9")
PY
}
