"""Ownership checks and recoverable installation of a handoff on one filesystem."""
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote

UPLOAD = Path(".listing-kit/upload")
SWAP = ".upload.listing-kit-swap"
MARKER = ".listing-kit-upload"
INDEX = "INDEX.md"
ROW = re.compile(r"\| \d+ \| `([^`|]+)` \| `[^`|]*` \| `([0-9a-f]{64})` \|")


def is_link(path):
    """Include Windows junctions and other reparse points on Python 3.8."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def open_source(path):
    """Open a listing file without traversing a symlink, including at copy time."""
    if os.open not in os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"):
        for part in (*reversed(path.parents), path):
            if is_link(part):
                raise ValueError("symlink in listing: %s" % part)
        return path.open("rb")
    path = path.absolute()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, flags, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except OSError as error:
        error.filename = str(path)
        raise
    finally:
        os.close(directory)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ValueError("not a regular listing file: %s" % path)
    return os.fdopen(fd, "rb")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@contextmanager
def locked_upload(root):
    """Serialize swaps and crash recovery; the OS releases the lock on process exit."""
    upload = root / UPLOAD
    parent = upload.parent
    if is_link(parent):
        raise ValueError("symlink in output path: %s" % parent)
    parent.mkdir(exist_ok=True)
    if os.name == "nt":
        # Windows deletes this exclusive handle's file even on abnormal termination.
        fd = os.open(parent / ".listing-kit-handoff.lock", os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_TEMPORARY)
    else:
        import fcntl
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if os.name != "nt":
            fcntl.flock(fd, fcntl.LOCK_EX)
        if is_link(upload):
            raise ValueError("symlink in output path: %s" % upload)
        _recover(upload)
        yield upload
    finally:
        os.close(fd)


def _cell(value):
    # Code spans protect Markdown punctuation. Escape the table/code delimiters,
    # control characters and the escape introducer itself, reversibly.
    return "".join("%%%02X" % ord(c) if c in "%|`" or ord(c) < 32 or ord(c) == 127 else c
                   for c in str(value))


def _target(stage, relative):
    relative = Path(relative)
    target = stage / relative
    if (relative.is_absolute() or not relative.parts or ".." in relative.parts
            or stage != stage.resolve() or target.resolve() != target):
        raise ValueError("destination outside staging directory: %s" % relative)
    return target


def _entries(directory):
    """Walk actual entries without following links. Preserve files and empty directories."""
    for entry in directory.iterdir():
        yield entry
        if not is_link(entry) and entry.is_dir():
            yield from _entries(entry)


def _check_tree(directory, files):
    """Verify all surviving entries before removal, including changes to generated files."""
    if is_link(directory) or not directory.is_dir():
        raise ValueError("expected a directory: %s" % directory)
    dirs = {parent.as_posix() for name in files for parent in Path(name).parents}
    unexpected = []
    entries = list(_entries(directory))
    for path in entries:
        name = path.relative_to(directory).as_posix()
        if not is_link(path):
            if name in dirs and path.is_dir():
                continue
            if name in files and path.is_file() and (files[name] is None or digest(path) == files[name]):
                continue
        unexpected.append(name)
    if unexpected:
        raise ValueError("extra or modified entries in %s: %s" % (directory, ", ".join(sorted(unexpected))))
    return entries


def owned_files(directory):
    if not os.path.lexists(directory):
        return None
    if is_link(directory) or not directory.is_dir():
        raise ValueError("output is not a regular directory: %s" % directory)
    marker, index = directory / MARKER, directory / INDEX
    if (is_link(marker) or not marker.is_file() or is_link(index) or not index.is_file()
            or marker.read_bytes() != (digest(index) + "\n").encode()):
        names = ", ".join(sorted(p.relative_to(directory).as_posix() for p in _entries(directory)))
        if not names:
            return {}
        raise ValueError("missing or modified %s or %s in %s (contents: %s)" % (MARKER, INDEX, directory, names))
    files = {MARKER: digest(marker), INDEX: digest(index)}
    for line in index.read_text(encoding="utf-8").split("\n"):
        row = ROW.fullmatch(line)
        if row:
            name, checksum = row.groups()
            files[unquote(name)] = checksum
    _check_tree(directory, files)
    return files


def _remove_tree(directory, files):
    # Delete only inspected entries. rmdir will refuse a concurrently added file.
    entries = _check_tree(directory, files)
    for path in reversed(entries):
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()
    directory.rmdir()


def _recover(upload):
    """Restore the previous output first, even if this invocation's inputs are invalid."""
    txn = upload.with_name(SWAP)
    journal = txn.with_suffix(txn.suffix + ".json")
    if not os.path.lexists(txn) and not os.path.lexists(journal):
        return
    if is_link(txn) or is_link(journal) or not journal.is_file():
        raise ValueError("unrecognized handoff transaction: %s" % txn)
    record = json.loads(journal.read_text(encoding="utf-8"))
    if (not isinstance(record, dict) or record.get("format") != "listing-kit-handoff-swap-v1"
            or record.get("out") != str(upload) or not isinstance(record.get("stage"), list)
            or not (record.get("previous") is None or isinstance(record["previous"], dict))):
        raise ValueError("unexpected handoff transaction: %s" % txn)
    old, stage = txn / "previous", txn / "stage"
    if os.path.lexists(old):
        if is_link(old) or not old.is_dir() or record.get("previous") is None:
            raise ValueError("unexpected backup: %s" % old)
        if not os.path.lexists(upload):
            os.replace(old, upload)
        elif not os.path.lexists(stage):
            _remove_tree(old, record["previous"])
        else:
            raise ValueError("cannot restore %s over %s" % (old, upload))
    if os.path.lexists(stage):
        if (stage / MARKER).exists():
            stage_files = owned_files(stage)
        else:
            stage_files = dict.fromkeys(record["stage"])
        _remove_tree(stage, stage_files)
    if txn.exists():
        txn.rmdir()
    journal.unlink()


def _write(stage, items, verified, root):
    rows = [
        "# Files to upload by hand", "",
        "Store rules checked %s." % _cell(verified),
        "Upload screenshots in the numbered order. Edit the source listing and rebuild to update this copy.",
        "In table cells, percent escapes represent literal characters.", "",
        "| # | File | Where it goes | SHA-256 |", "|---|---|---|---|",
    ]
    for number, (src, relative, place, content) in enumerate(items, 1):
        target = _target(stage, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as dest:
            if src is None:
                dest.write(content)
            else:
                if not any(root / tree in src.parents for tree in ("fastlane", "store-assets")):
                    raise ValueError("source outside listing: %s" % src)
                with open_source(src) as source:
                    shutil.copyfileobj(source, dest)
        rows.append("| %d | `%s` | `%s` | `%s` |" %
                    (number, _cell(relative.as_posix()), _cell(place), digest(target)))
    index = _target(stage, INDEX)
    with index.open("xb") as dest:
        dest.write(("\n".join(rows) + "\n").encode("utf-8"))
    with _target(stage, MARKER).open("xb") as dest:
        dest.write((digest(index) + "\n").encode())


def install(root, previous, items, verified):
    upload = root / UPLOAD
    txn = upload.with_name(SWAP)
    stage = txn / "stage"
    paths = [_target(stage, dest).relative_to(stage).as_posix() for _, dest, _, _ in items]
    # Write the recovery record before creating any payload or moving the old tree.
    record = {"format": "listing-kit-handoff-swap-v1", "out": str(upload),
              "stage": [INDEX, MARKER] + paths, "previous": previous}
    journal = txn.with_suffix(txn.suffix + ".json")
    # Publish a complete journal before making a work directory. Remove it last
    # during recovery, so interruption while creating/removing directories is retryable.
    with tempfile.NamedTemporaryFile(dir=upload.parent, mode="w", encoding="utf-8", delete=False) as pending:
        try:
            json.dump(record, pending)
            pending.close()
            os.replace(pending.name, journal)
        finally:
            if os.path.exists(pending.name):
                os.unlink(pending.name)
    mask = None
    try:
        txn.mkdir(mode=0o700)
        stage.mkdir()
        _write(stage, items, verified, root)
        owned_files(stage)
        if owned_files(upload) != previous:
            raise ValueError("output changed during build: %s" % upload)
        # Defer ordinary termination across the two renames and cleanup. The
        # journal also supports uncatchable termination or a Windows process exit.
        if hasattr(signal, "pthread_sigmask"):
            mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        if previous is not None:
            os.rename(upload, txn / "previous")
        os.rename(stage, upload)
    finally:
        try:
            _recover(upload)
        finally:
            if mask is not None:
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)
