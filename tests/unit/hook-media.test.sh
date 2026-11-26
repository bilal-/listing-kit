#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"
it "200 distinct staged 1 MiB screenshots use bounded reads and cached scans"
new_tempdir T
git -C "$T" init -q
python3 -I -B - "$T" "$SKILL_DIR" <<'PY'
import os
from pathlib import Path
import struct
import subprocess
import sys
from unittest.mock import patch

root, kit = map(Path, sys.argv[1:])
os.chdir(root)
sys.path.insert(0, str(kit / "scripts/lib"))
import review_hook
import secret_scan

folder = Path("fastlane/screenshots/en-US")
folder.mkdir(parents=True)
for index in range(200):
    path = folder / ("%03d.png" % index)
    with path.open("wb") as stream:
        stream.write(b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR" + struct.pack(">IIBBBBB", 1206, 2622, 8, 2, 0, 0, 0))
        stream.write(b"\0" * 4 + struct.pack(">I", index) + b"IDAT")
        stream.truncate(1024 * 1024)
subprocess.run(["git", "add", "fastlane"], check=True)
real_popen = subprocess.Popen
reads = []
class Meter:
    def __init__(self, pipe):
        self.pipe = pipe
    def read(self, *args):
        data = self.pipe.read(*args)
        reads.append(len(data))
        return data
    def __getattr__(self, name):
        return getattr(self.pipe, name)
def popen(argv, *args, **kwargs):
    child = real_popen(argv, *args, **kwargs)
    if "cat-file" in argv and child.stdout:
        child.stdout = Meter(child.stdout)
    return child
with patch.object(subprocess, "Popen", popen), patch.object(review_hook, "git", wraps=review_hook.git) as git:
    review_hook.main(str(kit), [""])
    assert sum(reads) < 4 * 1024 * 1024, sum(reads)
    assert (root / "listing-review.html").is_file()
    for args, kwargs in git.call_args_list:
        if args[0] == "checkout-index":
            assert b".png" not in kwargs["input"], "rewrote media via checkout-index"
        if args[0] == "ls-files":
            assert {b":(literal)fastlane", b":(icase,literal)fastlane"}.intersection(args), "enumerated the entire index"
    with patch.object(secret_scan, "binary_media", side_effect=AssertionError("rescanned cached blob")):
        review_hook.main(str(kit), [""])
    changed_scanner = root / "changed-scanner.py"
    changed_scanner.write_bytes(Path(secret_scan.__file__).read_bytes() + b"\n# scanner update\n")
    with patch.object(secret_scan, "__file__", str(changed_scanner)), patch.object(
            secret_scan, "binary_media", wraps=secret_scan.binary_media) as classify:
        review_hook.scan_index(review_hook.staged_entries([b""]), [b""], set(), secret_scan)
        assert classify.call_count == 200, "cache survived a scanner change"
PY
assert_eq 0 "$?"
summary
