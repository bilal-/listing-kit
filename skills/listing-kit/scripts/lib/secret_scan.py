"""Check listing inputs without printing credential values."""
import json
import os
from pathlib import Path
import subprocess
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
    BOUNDARY + rb"""(?:[A-Za-z0-9]+[_-])*(?:api[_-]?key|client[_-]?secret|secret|password|passwd|token|bearer)"""
    rb"""["']?[ \t]*[:=][ \t]*(?P<quote>["']?)(?P<value>[A-Za-z0-9/_+.=-]{12,})""",
    re.I,
)
# Require a digit in the value or an assignment terminator, so ordinary copy
# such as "Password: synchronization made easy" does not match.
TERMINATOR = re.compile(rb"""["',;}]|[ \t\r]*$""", re.M)
ACCOUNT = re.compile(rb'"type"\s*:\s*"service_account"')
KEY_SUFFIXES = (".p8", ".p12", ".pem", ".key", ".jks", ".keystore")
# Text store fields and JSON are always scanned, including malformed fields.
def binary_media(path, head):
    if path.suffix.lower() in (".txt", ".json"):
        return False
    if head.startswith((b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", b"\xff\xd8\xff",
                        b"II*\x00", b"MM\x00*", b"\x00\x00\x01\x00")):
        return True
    if head.startswith(b"BM") and head[6:10] == b"\0" * 4 and len(head) >= 14:
        return True
    if head.startswith((b"GIF87a", b"GIF89a")):
        return len(head) >= 13 and not all(32 <= byte < 127 for byte in head[6:13])
    if head[:4] in (b"wOFF", b"wOF2"):
        return head[4:8] in (b"OTTO", b"ttcf", b"\x00\x01\x00\x00") and head[14:16] == b"\0\0"
    if head[:4] in (b"OTTO", b"\x00\x01\x00\x00"):
        return len(head) >= 12 and 0 < int.from_bytes(head[4:6], "big") < 4096
    if head[:4] == b"ttcf":
        return head[4:8] in (b"\0\1\0\0", b"\0\2\0\0")
    return ((head.startswith(b"RIFF") and head[8:12] == b"WEBP")
            or (head[4:8] == b"ftyp" and head[8:12] in (b"avif", b"heic", b"mif1")))


def secret_text(data):
    if TOKEN.search(data) or AWS.search(data) or ACCOUNT.search(data):
        return True
    for match in ASSIGNMENT.finditer(data):
        value = match["value"]
        if not match["quote"] and re.fullmatch(rb"process\.env\.[A-Za-z_][A-Za-z0-9_]*", value):
            continue
        if re.search(rb"[0-9]", value) or TERMINATOR.match(data, match.end()):
            return True
    return False


def secret_content(path, data):
    if secret_text(data):
        return True
    if b"\0" in data:
        for encoding in ("utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"):
            try:
                decoded = data.decode(encoding)
            except UnicodeError:
                continue
            if secret_text(decoded.encode("utf-8")):
                return True
    if path.suffix.lower() == ".json":
        try:
            decoded = json.loads(data)
        except (ValueError, UnicodeError):
            return False
        # Test decoded assignments as well as individual strings. Serializing
        # alone would escape a leading newline again and could hide a token.
        if secret_text(json.dumps(decoded, ensure_ascii=False).encode("utf-8", "surrogatepass")):
            return True
        pending = [decoded]
        while pending:
            item = pending.pop()
            if isinstance(item, dict):
                pending.extend(item.keys())
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
            elif isinstance(item, str) and secret_text(item.encode("utf-8", "surrogatepass")):
                return True
    return False


def private_local(path):
    return ".listing-kit" in path.parts and (path.name == "local.json" or path.name.endswith(".local"))


def tracked(path):
    # A local-only file in an app outside Git can be ignored too. Other Git
    # errors must reach the caller as an incomplete scan.
    env = dict(os.environ, LC_ALL="C")
    repo = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=path.parent, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if repo.returncode and b"not a git repository" in repo.stderr:
        return False
    repo.check_returncode()
    return bool(subprocess.check_output(["git", "ls-files", "-z", "--", ":(literal)" + path.name],
                                        cwd=path.parent, env=env))


def sensitive_name(path):
    return any(secret_text(os.fsencode(part)) for part in path.parts)


def credential_file(path, size):
    return path.name.lower().endswith(KEY_SUFFIXES) or (path.name == "demo_password.txt" and size > 0)


def report(path):
    label = "[redacted path]" if sensitive_name(path) else str(path)
    print(f"POTENTIAL SECRET in committed listing: {label}", file=sys.stderr)


def scan(path):
    try:
        if private_local(path) and not path.is_dir():
            if tracked(path):
                report(path)
                yield 1
            return
        if sensitive_name(path) or path.name.lower().endswith(KEY_SUFFIXES):
            report(path)
            yield 1
        elif path.is_symlink():
            raise OSError("symbolic link")
        elif path.is_dir():
            for child in path.iterdir():
                yield from scan(child)
        elif path.is_file():
            with path.open("rb") as stream:
                head = stream.read(32)
                if credential_file(path, len(head)) or (
                        not binary_media(path, head) and secret_content(path, head + stream.read())):
                    report(path)
                    yield 1
        elif path.exists():
            raise OSError("unsupported file type")
    except (OSError, subprocess.SubprocessError):
        print("ERROR: secret scan could not complete", file=sys.stderr)
        yield 2


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
