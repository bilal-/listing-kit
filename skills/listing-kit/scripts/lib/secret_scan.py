"""Check listing inputs without printing credential values."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import re
import sys

BOUNDARY = rb"(?<![A-Za-z0-9_])"
TOKEN = re.compile(
    BOUNDARY + rb"(?:gh[pousr]_[A-Za-z0-9_]{36,}|glpat-[A-Za-z0-9_-]{20,}|"
    rb"(?:xox[abposre]|xapp|xwfp)-[A-Za-z0-9-]{10,}|"
    rb"(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}|whsec_[A-Za-z0-9]{24,}|"
    rb"ey[A-Za-z0-9_-]{8,}\.ey[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|"
    rb"""(?i:(?:authorization[ \t]*:[ \t]*|["'])bearer)[ \t]+[A-Za-z0-9._~+/-]{20,})|"""
    rb'(?i:aws_secret_access_key)|github_pat_[A-Za-z0-9_]{22,}|AIza[0-9A-Za-z_-]{35}|'
    rb'(?i:"(?:private_key_id|private_key)"[ \t]*:|-----BEGIN [A-Z ]*PRIVATE KEY-----)',
)
SK_TOKEN = re.compile(rb"(?<![A-Za-z0-9_-])sk-([A-Za-z0-9_-]{20,})")
URL_SLUG = re.compile(rb"(?:[a-z0-9]+-)+[a-z0-9]+")

# AWS IDs are uppercase. Lowercase "asia..." in an ordinary URL is clean.
AWS = re.compile(BOUNDARY + rb"(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Za-z0-9])")
ASSIGNMENT = re.compile(
    BOUNDARY + rb"""(?P<key>[A-Za-z][A-Za-z0-9_-]*)["']?[ \t]*(?P<op>[:=])[ \t]*"""
)
VALUE = re.compile(
    rb"""(?P<quote>["']?)(?P<value>[A-Za-z0-9/_+.=-]{12,})""",
)
SENSITIVE_KEYS = {b"apikey", b"clientsecret", b"secret", b"password", b"mypassword",
                  b"passwd", b"token", b"bearer"}
IDENTIFIER = rb"[A-Za-z_$][A-Za-z0-9_$]*"
REFERENCE = re.compile(rb"(?:" + IDENTIFIER + rb"(?:\." + IDENTIFIER + rb")+|[A-Z][A-Z0-9]*_[A-Z0-9_]+)(?=[\s,;)}\]?:|]|$)")
FALLBACK = re.compile(rb"\s*(?:\|\||\?\?|\?|:)\s*")
# Require a digit in the value or an assignment terminator, so ordinary copy
# such as "Password: synchronization made easy" does not match.
TERMINATOR = re.compile(rb"""["',;}]|[ \t\r]*$""", re.M)
ACCOUNT = re.compile(rb'"type"\s*:\s*"service_account"')
KEY_SUFFIXES = (".p8", ".p12", ".pem", ".key", ".jks", ".keystore")
# Text store fields and JSON are always scanned, including malformed fields.
def binary_media(path, head):
    suffix = path.suffix.lower()
    if suffix not in ("", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".ico", ".bmp", ".gif",
                      ".woff", ".woff2", ".otf", ".ttf", ".ttc", ".webp", ".avif", ".heic",
                      ".heif", ".pdf", ".psd", ".mp4", ".mov"):
        return False
    if suffix == ".pdf" and re.match(rb"%PDF-\d\.\d", head):
        return True
    if suffix == ".psd" and head.startswith(b"8BPS\x00\x01" + b"\0" * 6):
        return True
    if suffix in (".mp4", ".mov") and (head[4:8] == b"ftyp" or
            (suffix == ".mov" and head[4:8] in (b"moov", b"mdat", b"wide"))):
        return True
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
    for token in SK_TOKEN.finditer(data):
        body = token[1]
        if (data[token.start()-1:token.start()] == b"/" and URL_SLUG.fullmatch(body)
                and not body.startswith((b"proj-", b"ant-", b"svcacct-"))):
            continue
        return True
    for match in ASSIGNMENT.finditer(data):
        key = re.sub(rb"([a-z0-9])([A-Z])", rb"\1_\2", match["key"])
        words = re.split(rb"[_-]+", key.lower())
        if words[-1] not in SENSITIVE_KEYS and b"".join(words[-2:]) not in SENSITIVE_KEYS:
            continue
        pos = match.end()
        reference = REFERENCE.match(data, pos)
        while reference:
            fallback = FALLBACK.match(data, reference.end())
            if not fallback:
                break
            pos = fallback.end()
            reference = REFERENCE.match(data, pos)
        if reference:
            continue
        literal = VALUE.match(data, pos)
        if not literal:
            continue
        value = literal["value"]
        if not literal["quote"]:
            if (match["op"] == b":" and words[-1] == b"password"
                    and re.fullmatch(rb"[a-z][a-z.-]*", value)):
                continue
            # A colon followed by a hyphenated modifier and further prose.
            if (match["op"] == b":" and b"-" in value
                    and re.match(rb",?[ \t]+[A-Za-z]", data[literal.end():])):
                continue
        if re.search(rb"[0-9]", value) or TERMINATOR.match(data, literal.end()):
            return True
    return False


def secret_content(path, data):
    if path.name == "demo_password.txt":
        try:
            return bool(data.decode("utf-8").strip())
        except UnicodeError:
            return True
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


def git_files(path, *args):
    """Return paths relative to cwd, or an empty set outside a worktree."""
    if shutil.which("git") is None:
        return set()
    env = dict(os.environ, LC_ALL="C")
    result = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=path,
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode and b"not a git repository" in result.stderr:
        return set()
    result.check_returncode()
    data = subprocess.check_output(["git", "ls-files", "-z", *args], cwd=path, env=env)
    return {Path(os.fsdecode(item)) for item in data.split(b"\0") if item}

def tracked(path):
    return bool(git_files(path.parent, "--", ":(literal)" + path.name))

def sensitive_name(path):
    return any(secret_text(os.fsencode(part)) for part in path.parts)


def credential_file(path):
    return path.name.lower().endswith(KEY_SUFFIXES)


def report(path):
    label = "[redacted path]" if sensitive_name(path) else str(path)
    message = f"POTENTIAL SECRET in committed listing: {label}"
    if path.name == "demo_password.txt":
        message += " (keep the demo password out of the repo; supply it via the environment at upload)"
    print(message, file=sys.stderr)

def file_secret(path):
    with path.open("rb") as stream:
        head = stream.read(32)
        return not binary_media(path, head) and secret_content(path, head + stream.read())


def scan(path, base, ignored, roots):
    relative = path.relative_to(base)
    if relative in ignored:
        return
    try:
        if private_local(relative) and not path.is_dir():
            if tracked(path):
                report(relative)
                yield 1
            return
        if sensitive_name(relative) or credential_file(relative):
            report(relative)
            yield 1
        elif path.is_symlink():
            target = Path(os.readlink(path))
            if secret_text(os.fsencode(target)):
                report(relative)
                yield 1
            elif target.is_absolute() or not any(root == path.resolve() or root in path.resolve().parents
                                                  for root in roots):
                raise OSError("symbolic link leaves scan root")
            elif path.is_file() and file_secret(path):
                report(relative)
                yield 1
        elif path.is_dir():
            for child in path.iterdir():
                yield from scan(child, base, ignored, roots)
        elif path.is_file():
            if file_secret(path):
                report(relative)
                yield 1
        elif path.exists():
            raise OSError("unsupported file type")
    except (OSError, subprocess.SubprocessError):
        print("ERROR: secret scan could not complete", file=sys.stderr)
        yield 2


def main(paths):
    results = set()
    roots = [Path(p).resolve() for p in paths if not Path(p).is_symlink()]
    for name in paths:
        path = Path(name).absolute()
        if not path.exists() and not path.is_symlink():
            continue
        try:
            ignored = git_files(path.parent, "--others", "--ignored", "--exclude-standard",
                                "--directory", "--", ":(literal)" + path.name)
            results.update(scan(path, path.parent, ignored, roots))
        except (OSError, RuntimeError, subprocess.SubprocessError):
            print("ERROR: secret scan could not complete", file=sys.stderr)
            results.add(2)
    if 1 in results:
        return 1
    if 2 in results:
        return 2
    print("Secret scan clean: no detected credentials.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
