"""Embedded in each installed runner so path selection works even if the kit moves."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sqlite3
import sys
import tempfile


from install_lookup import Blocked, find_kit

BUILDER = Path("scripts/package/build-review.sh")


def git(*args, **kwargs):
    return subprocess.check_output(["git", *args], **kwargs)


LISTING_DIRS = (b"fastlane/", b"store-assets/", b".listing-kit/")
SKIP = {".git", ".gradle", "build", "DerivedData", "node_modules", "Pods", ".expo",
        ".dart_tool", "dist", "vendor", "Carthage", ".build", ".swiftpm", "out", ".cxx"}
SKIP_SUFFIXES = (".framework", ".xcframework", ".xcarchive")


SKIP_LOWER = {name.lower() for name in SKIP}


def skipped_directory(name, ignorecase=False):
    if ignorecase:
        return name.lower() in SKIP_LOWER or name.lower().endswith(SKIP_SUFFIXES)
    return name in SKIP or name.endswith(SKIP_SUFFIXES)


def listing_input(path, prefix, ignorecase=False):
    if ignorecase:
        path, prefix = path.lower(), prefix.lower()
    if not path.startswith(prefix):
        return False
    rel = path[len(prefix):]
    if rel.startswith(LISTING_DIRS) or rel == b"app.json":
        return True
    if rel.startswith(b"app.config.") and b"/" not in rel:
        return True
    parts = rel.split(b"/")
    native_files = (b"Info.plist", b"AndroidManifest.xml", b"build.gradle", b"build.gradle.kts")
    if parts[-1] not in (tuple(n.lower() for n in native_files) if ignorecase else native_files) and not rel.endswith(b".pbxproj"):
        return False
    return not any(skipped_directory(os.fsdecode(part), ignorecase) for part in parts[:-1])


def pathspecs(prefixes, ignorecase=False):
    magic = b":(icase," if ignorecase else b":("
    specs = []
    for prefix in prefixes:
        specs.extend(magic + b"literal)" + prefix + name for name in
                     (b"fastlane", b"store-assets", b".listing-kit", b"app.json"))
        escaped = re.sub(rb"([\\*?\[])", rb"\\\1", prefix)
        specs.extend(magic + b"glob)" + escaped + pattern for pattern in
                     (b"app.config.*", b"**/*.pbxproj", b"**/Info.plist", b"**/AndroidManifest.xml", b"**/build.gradle", b"**/build.gradle.kts"))
    return specs


def staged_entries(prefixes, ignorecase=False):
    for record in git("ls-files", "--stage", "-z", "--", *pathspecs(prefixes, ignorecase)).split(b"\0"):
        if record:
            header, raw = record.split(b"\t", 1)
            mode, oid, stage = header.split()
            if any(listing_input(raw, prefix, ignorecase) for prefix in prefixes):
                yield raw, mode, oid, stage


def reviewed_devices():
    result = subprocess.run(["git", "config", "--local", "-z", "--get-all",
                             "listingKit.reviewedDeviceBlob"], stdout=subprocess.PIPE)
    if result.returncode != 1:
        result.check_returncode()
    return set(result.stdout.split(b"\0"))


class ScanCache:
    """Only clean results, partitioned by scanner implementation and path policy."""
    def __init__(self, scanner):
        digest = hashlib.sha256(Path(scanner.__file__).read_bytes()).hexdigest()
        common = Path(os.fsdecode(git("rev-parse", "--git-common-dir")[:-1]))
        self.db = None
        try:
            self.db = sqlite3.connect(str(common / "listing-kit-scan.sqlite3"), timeout=0.2)
            self.db.execute("CREATE TABLE IF NOT EXISTS clean "
                            "(scanner, oid, kind, media, PRIMARY KEY(scanner, oid, kind))")
        except sqlite3.Error:
            self.close()
        self.digest = digest

    def close(self):
        if self.db:
            try:
                self.db.commit()
            except sqlite3.Error:
                pass
            self.db.close()
        self.db = None

    def media(self, oid, path, scanner, ignorecase=False):
        name = path.name.lower() if ignorecase else path.name
        policy_path = path.with_name(name)
        kind = b"demo" if name == "demo_password.txt" else os.fsencode(path.suffix.lower())
        key = (self.digest, oid, kind)
        if self.db:
            try:
                row = self.db.execute("SELECT media FROM clean WHERE scanner=? AND oid=? AND kind=?", key).fetchone()
                if row:
                    return bool(row[0])
            except sqlite3.Error:
                self.close()
        with blob(oid) as proc:
            head = proc.stdout.read(32)
            media = scanner.binary_media(path, head)
            if not media:
                data = head + proc.stdout.read()
                if proc.wait():
                    raise OSError("could not read blob")
                if scanner.secret_content(policy_path, data):
                    scanner.report(path)
                    raise Blocked(f"remove the credential from {path}")
        if self.db:
            try:
                self.db.execute("INSERT OR IGNORE INTO clean VALUES (?,?,?,?)", (*key, int(media)))
            except sqlite3.Error:
                self.close()
        return media


def blob(oid):
    # Request streaming even for screenshots below Git's usual large-file threshold.
    # Closing the pipe after the signature releases this object without draining it.
    return subprocess.Popen(["git", "-c", "core.bigFileThreshold=1", "cat-file", "blob", oid],
                            stdout=subprocess.PIPE)


def path_key(path, ignorecase):
    return Path(os.fsdecode(os.fsencode(path).lower())) if ignorecase else path


def check_links(links, ignorecase):
    indexed = {path_key(path, ignorecase): target for path, (_, target) in links.items()}
    for path, (app, target) in links.items():
        current = path.parent
        pending = list(reversed(target.parts))
        hops = 0
        while pending:
            part = pending.pop()
            if part == ".." and path_key(current, ignorecase) == path_key(app, ignorecase):
                raise Blocked(f"cannot scan link outside listing tree: {path}")
            current = current.parent if part == ".." else current / part
            key = path_key(current, ignorecase)
            if key in indexed:
                hops += 1
                if hops > 40:
                    raise Blocked(f"cannot resolve listing link: {path}")
                pending.extend(reversed(indexed[key].parts))
                current = current.parent
        relative = os.fsencode(current.relative_to(app))
        tree = relative.lower() if ignorecase else relative
        if tree + b"/" not in LISTING_DIRS and not listing_input(relative, b"", ignorecase):
            raise Blocked(f"cannot scan link outside listing tree: {path}")
        yield path, path_key(current, ignorecase)


def scan_index(entries, prefixes, changed, scanner, ignorecase=False):
    paths, media, links, blobs = [], {}, {}, {}
    allowed = reviewed_devices()
    cache = ScanCache(scanner)
    try:
        for raw, mode, oid, stage in entries:
            path = Path(os.fsdecode(raw))
            prefix = max((p for p in prefixes if listing_input(raw, p, ignorecase)), key=len)
            relative = Path(os.fsdecode(raw[len(prefix):]))
            policy_path = path_key(relative, ignorecase)
            listing = os.fsencode(policy_path).startswith(LISTING_DIRS)
            if scanner.sensitive_name(relative):
                scanner.report(relative)
                raise Blocked("remove the credential from [redacted path]")
            if mode == b"160000":
                print(f"listing-kit: skipping submodule {relative}", file=sys.stderr)
                continue
            if stage != b"0" or mode not in (b"100644", b"100755", b"120000"):
                raise Blocked(f"cannot scan staged entry: {relative}")
            if scanner.private_local(policy_path) or scanner.credential_file(relative):
                scanner.report(relative)
                raise Blocked(f"remove the credential or private file from {relative}")
            if mode != b"120000":
                blobs[path_key(path, ignorecase)] = oid
            try:
                if mode == b"120000":
                    data = git("cat-file", "blob", oid)
                    target = Path(os.fsdecode(data))
                    if scanner.secret_text(data) or target.is_absolute():
                        raise Blocked(f"unsafe staged link target: {path}")
                    links[path] = (Path(os.fsdecode(raw[:len(prefix)])), target)
                elif not listing and (raw not in changed or oid + b" " + raw in allowed):
                    pass
                elif cache.media(oid, relative, scanner, ignorecase):
                    media[path] = oid
                    continue
            except (OSError, subprocess.SubprocessError, ValueError, RecursionError) as exc:
                raise Blocked(f"could not scan staged blob: {relative}") from exc
            paths.append(raw)
        for path, target in check_links(links, ignorecase):
            if target in blobs:
                # The alias can impose a stronger content policy (e.g. a demo password).
                cache.media(blobs[target], path.relative_to(links[path][0]), scanner, ignorecase)
    finally:
        cache.close()
    return paths, media


class ImageHeader:
    """Forward-only seeks for reading PNG/JPEG metadata from a Git stream."""
    def __init__(self, stream):
        self.stream = stream
        self.signature = b""

    def read(self, length):
        data = self.stream.read(length)
        self.signature += data[:32 - len(self.signature)]
        return data

    def seek(self, distance, whence):
        assert whence == os.SEEK_CUR and distance >= 0
        while distance:
            data = self.read(min(distance, 65536))
            if not data:
                break
            distance -= len(data)


def media_index(media, snap):
    # The page links to media by relative path. Validation only needs image facts.
    from imginfo import stream_info
    facts = {}
    sizes = git("cat-file", "--batch-check=%(objectsize)", input=b"".join(
        oid + b"\n" for oid in media.values())).splitlines() if media else []
    for (path, oid), size in zip(media.items(), sizes):
        target = snap / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        if path.suffix.lower() in (".png", ".jpg", ".jpeg"):
            with blob(oid) as proc:
                reader = ImageHeader(proc.stdout)
                info = stream_info(reader)
            target.write_bytes(reader.signature)
            facts[str(target)] = [info, int(size)]
    manifest = snap / ".listing-kit-image-info.json"
    manifest.write_text(json.dumps(facts), encoding="ascii")
    return str(manifest)


def refresh(apps, paths, media, kit, snap):
    if paths:
        git("checkout-index", "-z", "--stdin", "--ignore-skip-worktree-bits",
            "--prefix=" + str(snap) + "/", input=b"\0".join(paths) + b"\0")
    for raw in paths:
        path = snap / os.fsdecode(raw)
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as stream:
                if stream.read(43).startswith(b"version https://git-lfs.github.com/spec/v1"):
                    print(f"listing-kit: Warning: missing Git LFS content for {os.fsdecode(raw)}",
                          file=sys.stderr)
    build_env = os.environ.copy()
    for key in git("rev-parse", "--local-env-vars").decode("ascii").splitlines():
        build_env.pop(key, None)
    build_env["GIT_CEILING_DIRECTORIES"] = str(snap.parent)
    build_env["LK_REVIEW_IMAGE_INFO"] = media_index(media, snap)
    pages = []
    for app in apps:
        root = snap / app
        page = Path(app) / "listing-review.html"
        ignored = subprocess.run(["git", "check-ignore", "-q", "--", str(page)])
        if ignored.returncode == 0:
            print(f"listing-kit: Warning: {page} is git-ignored; skipping refresh.", file=sys.stderr)
            continue
        if ignored.returncode != 1:
            ignored.check_returncode()
        if (root / "fastlane").is_dir():
            build_env["LK_REVIEW_DISPLAY_ROOT"] = str(Path(app).resolve())
            result = subprocess.run(["bash", kit / BUILDER, root], env=build_env,
                                    stdout=subprocess.DEVNULL)
            if result.returncode or not (snap / page).is_file():
                raise Blocked("could not safely build the staged review page")
        pages.append(page)
    for page in pages:
        spec = ":(literal)" + str(page)
        if (snap / page).is_file():
            # Stage the generated bytes first. A failed clean filter or index
            # update leaves the caller's previous working-tree page intact.
            with (snap / page).open("rb") as source:
                oid = git("hash-object", "-w", "--path=" + str(page), "--stdin", stdin=source).strip()
            with tempfile.NamedTemporaryFile(dir=page.parent, delete=False) as output:
                tmp = Path(output.name)
            try:
                shutil.copy(snap / page, tmp)
                git("update-index", "--add", "--cacheinfo", "100644", oid, os.fsencode(page))
                os.replace(tmp, page)
            finally:
                tmp.unlink(missing_ok=True)
        else:
            git("rm", "-q", "--cached", "--ignore-unmatch", "--", spec)
            page.unlink(missing_ok=True)


def main(recorded, apps, channel=None, base=None):
    os.chdir(os.fsdecode(git("rev-parse", "--show-toplevel")[:-1]))
    prefixes = {app: os.fsencode(app + "/" if app else "") for app in apps}
    setting = subprocess.run(["git", "config", "--bool", "--get", "core.ignorecase"], stdout=subprocess.PIPE)
    if setting.returncode not in (0, 1):
        setting.check_returncode()
    ignorecase = setting.stdout.strip() == b"true"
    changed = set(git("diff", "--cached", "--name-only", "--no-renames", "-z",
                      *([base] if base else []), "--", *pathspecs(prefixes.values(), ignorecase)).split(b"\0"))
    affected = [app for app, prefix in prefixes.items() if any(listing_input(p, prefix, ignorecase) for p in changed)]
    if not affected:
        return
    kit = find_kit(Path(recorded), Path(channel) if channel else None)
    sys.path.insert(0, str(kit / "scripts/lib"))
    import secret_scan
    selected = [prefixes[app] for app in affected]
    paths, media = scan_index(staged_entries(selected, ignorecase), selected, changed, secret_scan, ignorecase)
    # A pathspec-only commit uses a disposable index. Git restores a second,
    # already locked index afterward, which would stage the old page again.
    index = Path(os.environ.get("GIT_INDEX_FILE", ""))
    if re.fullmatch(r"next-index-[0-9]+\.lock", index.name):
        print("listing-kit: Warning: partial commit scanned; refresh listing-review.html with build-review.sh and stage it separately.", file=sys.stderr)
        return
    try:
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR") or None) as directory:
            refresh(affected, paths, media, kit, Path(directory).resolve())
    except Exception as exc:
        print(f"listing-kit: Warning: scan completed; review refresh failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main(sys.argv[1], sys.argv[4:], sys.argv[2], sys.argv[3])
    except Blocked as exc:
        print(f"listing-kit: {exc}; listing-review.html not refreshed.", file=sys.stderr)
        sys.exit(1)
    except (OSError, subprocess.SubprocessError, ImportError, ValueError) as exc:
        print(f"listing-kit: could not complete staged credential check: {exc}", file=sys.stderr)
        sys.exit(1)
