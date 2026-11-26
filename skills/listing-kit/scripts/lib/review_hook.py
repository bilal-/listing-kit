"""Embedded in each installed runner so path selection works even if the kit moves."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


BUILDER = Path("scripts/package/build-review.sh")


class Blocked(Exception):
    pass


def git(*args, **kwargs):
    return subprocess.check_output(["git", *args], **kwargs)


def version(kit):
    if not kit.is_absolute() or not (kit / BUILDER).is_file() or not os.access(kit / BUILDER, os.X_OK):
        return ()
    try:
        value = (kit / "VERSION").read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return ()
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?", value)
    if not match:
        return ()
    major, minor, patch, pre = match.groups()
    parts = [(0, int(p)) if p.isdigit() else (1, p) for p in (pre or "").split(".")]
    return int(major), int(minor), int(patch), pre is None, parts


def find_kit(recorded):
    override = os.environ.get("LISTING_KIT_HOME")
    if override:
        path = Path(override)
        if version(path):
            return path
        raise Blocked("LISTING_KIT_HOME must be an absolute skill directory with VERSION and build-review.sh")
    if version(recorded):
        return recorded
    home = Path.home()
    codex = Path(os.environ.get("CODEX_HOME") or home / ".codex")
    candidates = [home / folder / "listing-kit" for folder in
                  (".agents/skills", ".gemini/extensions/listing-kit/skills", ".cursor/skills", ".kiro/skills")]
    candidates.append(codex / "skills/listing-kit")
    for cache in (home / ".claude/plugins/cache", codex / "plugins/cache"):
        if cache.is_absolute():
            candidates.extend(sorted(cache.glob("*/listing-kit/*/skills/listing-kit")))
    matches = [(version(path), path) for path in candidates]
    if matches:
        best, path = max(matches)
        if best:
            return path
    raise Blocked("listing-kit installation not found; set LISTING_KIT_HOME or reinstall")


def listing_input(path, prefix):
    if not path.startswith(prefix):
        return False
    rel = path[len(prefix):]
    return (rel.startswith((b"fastlane/", b"store-assets/", b".listing-kit/"))
            or rel == b"app.json" or (rel.startswith(b"app.config.") and b"/" not in rel)
            or rel.endswith(b".pbxproj") or rel.rsplit(b"/", 1)[-1] == b"Info.plist")


def staged_entries(prefixes):
    entries = []
    for record in git("ls-files", "--stage", "-z").split(b"\0"):
        if not record:
            continue
        meta, path = record.split(b"\t", 1)
        if any(listing_input(path, prefix) for prefix in prefixes):
            mode, oid, stage = meta.split()
            entries.append((path, mode, oid, stage))
    return entries


def scan_index(entries, scanner):
    # One request at a time keeps --batch pipes bounded even for large indexes.
    with subprocess.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE) as batch:
        try:
            for raw, mode, oid, stage in entries:
                path = Path(os.fsdecode(raw))
                if scanner.sensitive_name(path) or scanner.private_local(path) or scanner.credential_file(path, 0):
                    scanner.report(path)
                    raise Blocked("remove the credential or private file from staged listing inputs")
                if stage != b"0" or mode not in (b"100644", b"100755"):
                    raise Blocked("cannot scan a symlink, submodule or unmerged listing input")
                batch.stdin.write(oid + b"\n")
                batch.stdin.flush()
                header = batch.stdout.readline().split()
                if len(header) != 3 or header[:2] != [oid, b"blob"]:
                    raise Blocked("could not read a staged listing blob")
                size = int(header[2])
                head = batch.stdout.read(min(size, 32))
                remaining = size - len(head)
                if scanner.binary_media(path, head):
                    while remaining:
                        chunk = batch.stdout.read(min(remaining, 1024 * 1024))
                        if not chunk:
                            raise Blocked("incomplete staged media blob")
                        remaining -= len(chunk)
                elif scanner.credential_file(path, size) or scanner.secret_content(path, head + batch.stdout.read(remaining)):
                    scanner.report(path)
                    raise Blocked("remove the credential from staged listing inputs")
                if batch.stdout.read(1) != b"\n":
                    raise Blocked("incomplete staged listing blob")
        finally:
            batch.stdin.close()
            batch.stdout.close()
        if batch.wait():
            raise Blocked("git cat-file failed")


def refresh(apps, entries, kit, snap):
    paths = b"".join(entry[0] + b"\0" for entry in entries)
    git("checkout-index", "-z", "--stdin", "--ignore-skip-worktree-bits",
        "--prefix=" + str(snap) + "/", input=paths)
    build_env = os.environ.copy()
    for key in git("rev-parse", "--local-env-vars").decode("ascii").splitlines():
        build_env.pop(key, None)
    build_env["GIT_CEILING_DIRECTORIES"] = str(snap.parent)
    pages = []
    for app in apps:
        root = snap / app
        page = Path(app) / "listing-review.html"
        if (root / "fastlane").is_dir():
            result = subprocess.run(["bash", kit / BUILDER, root], env=build_env,
                                    stdout=subprocess.DEVNULL)
            if result.returncode or not (snap / page).is_file():
                raise Blocked("could not safely build the staged review page")
        pages.append(page)
    for page in pages:
        spec = ":(literal)" + str(page)
        if (snap / page).is_file():
            shutil.copyfile(snap / page, page)
            git("add", "--", spec)
        else:
            git("rm", "-q", "--cached", "--ignore-unmatch", "--", spec)
            page.unlink(missing_ok=True)


def main(recorded, apps):
    # Strip only Git's terminating LF; filenames may themselves end in LF.
    os.chdir(os.fsdecode(git("rev-parse", "--show-toplevel")[:-1]))
    changed = git("diff", "--cached", "--name-only", "--no-renames", "-z").split(b"\0")
    prefixes = {app: os.fsencode(app + "/" if app else "") for app in apps}
    affected = [app for app, prefix in prefixes.items() if any(listing_input(p, prefix) for p in changed)]
    try:
        kit = find_kit(Path(recorded))
    except Blocked as exc:
        if affected:
            raise
        print(f"listing-kit: Warning: {exc}; listing-review.html not refreshed.", file=sys.stderr)
        return
    if affected:
        sys.path.insert(0, str(kit / "scripts/lib"))
        import secret_scan
        entries = staged_entries([prefixes[app] for app in affected])
        scan_index(entries, secret_scan)
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR") or None) as directory:
            refresh(affected, entries, kit, Path(directory).resolve())


if __name__ == "__main__":
    try:
        main(sys.argv[1], sys.argv[2:])
    except Blocked as exc:
        print(f"listing-kit: {exc}; listing-review.html not refreshed.", file=sys.stderr)
        sys.exit(1)
    except (OSError, subprocess.SubprocessError, ImportError, ValueError):
        print("listing-kit: could not complete staged credential check or checkout.", file=sys.stderr)
        sys.exit(1)
