"""Check listing inputs without printing credential values."""
from pathlib import Path
import re
import sys

BOUNDARY = rb"(?<![A-Za-z0-9_])"
TOKEN = re.compile(
    BOUNDARY + rb"(?:gh[pousr]_[A-Za-z0-9_]{36,}|glpat-[A-Za-z0-9_-]{20,}|"
    rb"(?:xox[abposre]|xapp|xwfp)-[A-Za-z0-9-]{10,}|"
    rb"sk-(?:proj-|ant-|svcacct-)?[A-Za-z0-9_-]{20,}|"
    rb"(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}|whsec_[A-Za-z0-9]{24,}|"
    rb"ey[A-Za-z0-9_-]{8,}\.ey[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|"
    rb"bearer[ \t]+[A-Za-z0-9._~+/-]{20,})|"
    rb'aws_secret_access_key|github_pat_[A-Za-z0-9_]{22,}|AIza[0-9A-Za-z_-]{35}|'
    rb'"(?:private_key_id|private_key)"[ \t]*:|-----BEGIN [A-Z ]*PRIVATE KEY-----',
    re.I,
)
# AWS IDs are uppercase. Lowercase "asia..." in an ordinary URL is clean.
AWS = re.compile(BOUNDARY + rb"(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Za-z0-9])")
ASSIGNMENT = re.compile(
    rb"""(?:api[_-]?key|client[_-]?secret|secret|password|passwd|token|bearer)["']?[ \t]*[:=][ \t]*["']?([A-Za-z0-9/_+.=-]{12,})""",
    re.I,
)
# Require a digit in the value or an assignment terminator, so ordinary copy
# such as "Password: synchronization made easy" does not match.
TERMINATOR = re.compile(rb"""["',;}]|[ \t\r]*$""", re.M)
ACCOUNT = re.compile(rb'"type"\s*:\s*"service_account"')
KEY_SUFFIXES = (".p8", ".p12", ".pem", ".key", ".jks", ".keystore")
MEDIA = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp",
         ".tif", ".tiff", ".heic", ".avif", ".otf", ".ttf", ".ttc", ".woff", ".woff2", ".eot"}


def excluded(path):
    if ".listing-kit" not in path.parts:
        return False
    return (any(a == ".listing-kit" and b == "raw" for a, b in zip(path.parts, path.parts[1:]))
            or path.name == "local.json" or path.name.endswith(".local"))


def scan(path):
    if excluded(path):
        return
    try:
        key_file = path.name.lower().endswith(KEY_SUFFIXES)
        if path.is_symlink():
            if not key_file:
                raise OSError(f"cannot scan symbolic link: {path}")
        elif path.is_dir():
            for child in path.iterdir():
                yield from scan(child)
            return
        elif not path.is_file():
            return
        if key_file or contains_secret(path):
            print(f"POTENTIAL SECRET in committed listing: {path}", file=sys.stderr)
            yield 1
    except OSError as exc:
        print(f"ERROR: secret scan could not complete: {exc}", file=sys.stderr)
        yield 2


def contains_secret(path):
    suffix = path.suffix.lower()
    if path.name == "demo_password.txt" and path.stat().st_size:
        return True
    if suffix in MEDIA:
        return False
    with path.open("rb") as stream:
        header = stream.read(8192)
        if b"\0" in header:
            return False
        data = header + stream.read()
    if b"\0" in data:
        return False
    if TOKEN.search(data) or AWS.search(data) or (suffix == ".json" and ACCOUNT.search(data)):
        return True
    return any(re.search(rb"[0-9]", match[1]) or TERMINATOR.match(data, match.end())
               for match in ASSIGNMENT.finditer(data))


def main(paths):
    results = {result for name in paths for result in scan(Path(name))}
    if 1 in results:
        return 1
    if 2 in results:
        return 2
    print("Secret scan clean: no detected credentials.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
