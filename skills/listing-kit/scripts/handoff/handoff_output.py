"""Install the handoff at its fixed path and preserve user additions on rebuild."""

import fcntl
import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from itertools import groupby
from pathlib import Path

UPLOAD = Path(".listing-kit/upload")
MARKER = ".listing-kit-upload"
PREVIOUS = ".upload-previous"
STAGE = ".upload-stage-"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_owned(directory):
    def refuse(names):
        raise ValueError("%s contains unexpected or modified entries: %s\nmove or delete these, then rerun"
                         % (directory, ", ".join(names)))

    if directory.is_symlink() or not directory.is_dir():
        refuse(["symlink or file at " + str(directory)])
    marker = directory / MARKER
    files = {}
    if marker.is_file() and not marker.is_symlink():
        try:
            files = json.loads(marker.read_text(encoding="utf-8"))
        except ValueError:
            files = None
    if not isinstance(files, dict):
        refuse(sorted(p.name for p in directory.iterdir()))
    dirs = {str(parent) for name in files for parent in Path(name).parents}
    unexpected = []
    for path in directory.rglob("*"):
        name = str(path.relative_to(directory))
        if not path.is_symlink():
            if path.is_dir() and name in dirs:
                continue
            if path.is_file() and (path == marker or path.name.startswith("._") or
                                   path.name in (".DS_Store", "Thumbs.db", "desktop.ini")):
                continue
            if name in files and path.is_file() and digest(path) == files[name]:
                continue
        unexpected.append(name)
    if unexpected:
        refuse(sorted(unexpected))


@contextmanager
def locked_upload(root):
    # Lock the existing app root, including on the very first build.
    fd = os.open(root, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        upload = root / UPLOAD
        if upload.parent.is_symlink():
            raise ValueError("symlink in output path: %s" % upload.parent)
        for stage in upload.parent.glob(STAGE + "*"):
            if not stage.is_symlink() and (stage / MARKER).is_file():
                shutil.rmtree(stage)
        previous = upload.with_name(PREVIOUS)
        if os.path.lexists(previous):
            if os.path.lexists(upload):
                check_owned(previous)
                shutil.rmtree(previous)
            elif previous.is_dir() and not previous.is_symlink():
                previous.rename(upload)
            else:
                raise ValueError("unexpected backup: %s; move or delete these, then rerun" % previous)
        yield upload
    finally:
        os.close(fd)


def cell(value):
    return "".join("%%%02X" % ord(c) if c in "%|`" or ord(c) < 32 else c for c in str(value))


def write_stage(stage, plan):
    rows = ["# Upload your store listing", "",
            "Open each text file, copy its contents, and paste into the named console field. "
            "Drag screenshots from each numbered folder into its slot in file-name order.",
            "The upload folder is hidden in Finder. Drag from the opened window or press Cmd+Shift+. "
            "in the file picker to show hidden folders.",
            "A language marked `default` means use for every language.", ""]
    hashes = {}
    for (store, locale), items in groupby(plan.items, key=lambda item: item[1].parts[:2]):
        console = "App Store Connect" if store == "apple" else "Play Console"
        language = "English (U.S.) (en-US)" if locale == "en-US" else cell(locale)
        rows.extend(["## %s — %s" % (console, language), "", "| File | Console page and field |", "|---|---|"])
        for src, dest, place, content in items:
            target = stage / dest
            target.parent.mkdir(parents=True, exist_ok=True)
            if src is None:
                target.write_bytes(content)
            else:
                shutil.copyfile(src, target)
            hashes[str(dest)] = digest(target)
            rows.append("| `%s` | `%s` |" % (cell(dest), cell(place)))
        rows.append("")
    rows.extend(["## Not included", "", *plan.deferred,
                 "- Complete the review contact and demo account, age rating, privacy answers, "
                 "and pricing in the console. Upload the build separately."])
    for name, content in (("INDEX.md", "\n".join(rows) + "\n"), (".gitignore", "*\n")):
        (stage / name).write_text(content, encoding="utf-8")
        hashes[name] = digest(stage / name)
    (stage / MARKER).write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")


def install(upload, plan):
    upload.parent.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=STAGE, dir=upload.parent))
    previous = upload.with_name(PREVIOUS)
    try:
        (stage / MARKER).touch()
        write_stage(stage, plan)
        if os.path.lexists(upload):
            check_owned(upload)
            upload.rename(previous)
        stage.rename(upload)
    finally:
        if previous.exists() and not upload.exists():
            previous.rename(upload)
        if stage.exists():
            shutil.rmtree(stage)
    if previous.exists():
        shutil.rmtree(previous)
