"""Exercise prompt cancellation and lock contention in the shell fixture."""
import fcntl
import os
from pathlib import Path
import runpy
import subprocess
import sys
from unittest.mock import patch

mode, tool, root = sys.argv[1:]
args = ["publish", "--store", "apple", "--app-identifier", "example.apple"]
if mode == "resolve-play":
    args = ["publish", "--package-name", "example.play"]
os.chdir(root)
if mode == "lock":
    fd = os.open(".listing-kit", os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        result = subprocess.run([tool, *args], capture_output=True, timeout=5)
    finally:
        os.close(fd)
    assert result.returncode == 1 and b"holds the lock" in result.stderr, result
else:
    # Inject terminal input at the prompt without requiring a controlling TTY in CI.
    sys.argv = [str(Path(tool).parent / "fastlane/lk_fastlane.py"), *args]
    if mode in ("resolve", "resolve-play"):
        sys.argv.extend(["--resolve", "play" if mode == "resolve-play" else "apple"])
        response = patch("builtins.input", return_value="yes")
    else:
        response = patch("builtins.input", side_effect=EOFError if mode == "eof" else KeyboardInterrupt)
    with patch("sys.stdin.isatty", return_value=True), response:
        runpy.run_path(sys.argv[0], run_name="__main__")
