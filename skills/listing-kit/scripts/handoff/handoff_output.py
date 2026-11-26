"""Install the handoff at its fixed path and refuse rebuilds over user changes."""

import datetime
import fcntl
import hashlib
import html
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


def remove_tree(directory):
    # Keep the ownership record readable until every listed entry is gone.
    marker = directory / MARKER
    for entry in directory.iterdir():
        if entry == marker:
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    marker.unlink(missing_ok=True)
    directory.rmdir()


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
            if stage.is_symlink() or not stage.is_dir():
                continue
            marker = stage / MARKER
            if not marker.is_symlink() and marker.is_file():
                remove_tree(stage)
            elif not any(stage.iterdir()):
                stage.rmdir()
        previous = upload.with_name(PREVIOUS)
        if os.path.lexists(previous):
            if os.path.lexists(upload):
                check_owned(previous)
                remove_tree(previous)
            elif previous.is_dir() and not previous.is_symlink():
                previous.rename(upload)
            else:
                raise ValueError("unexpected backup: %s; move or delete these, then rerun" % previous)
        yield upload
    finally:
        os.close(fd)


def markdown_cell(text):
    if any(c in "|`" or ord(c) < 32 for c in text):
        escaped = "".join("&#%d;" % ord(c) if c in "|`" or ord(c) < 32 else html.escape(c) for c in text)
        return "<code>%s</code>" % escaped
    return "`%s`" % text


def guide(plan):
    title = next((content.decode().strip() for _, path, _, content in plan.items
                  if path.parts[2:] in (("text", "name.txt"), ("text", "title.txt"))), "")
    yield "h1", "Upload your store listing" + (" — " + title if title else "")
    yield "p", "Built " + datetime.date.today().isoformat()
    yield "p", ("This folder is a copy. Edit the source files under fastlane/ or store-assets/ and rerun. "
                "Rebuilds are refused if you edit files in this folder.")
    yield "p", ("Paths are relative to the folder containing INDEX.md. In the console, pick or add the language "
                "first. Copy and paste text into the named field. For categories, select the value shown. "
                "Drag screenshots into their slot in file-name order. Upload each graphic to the field shown. "
                "On a Mac, press Cmd+Shift+. in the file picker "
                "to show hidden folders.")
    if any(path.parts[1] == "default" for _, path, _, _ in plan.items):
        yield "p", "A language marked default means use for every language."
    for (store, locale), items in groupby(plan.items, key=lambda item: item[1].parts[:2]):
        console = "App Store Connect" if store == "apple" else "Play Console"
        language = "English (U.S.) (en-US)" if locale == "en-US" else locale
        yield "h2", console + " — " + language
        rows = []
        for folder, files in groupby(items, key=lambda item: item[1].parent):
            if folder.name[:1].isdigit() and len(folder.parts) == 3:
                group = list(files)
                action = " — drag all %d files in file-name order" % len(group)
                rows.append((str(folder) + "/", group[0][2] + action))
            else:
                rows.extend((str(dest), place) for _, dest, place, _ in files)
        yield "table", rows
    if plan.missing:
        yield "h2", "Missing"
        yield "ul", plan.missing
    yield "h2", "Not included"
    yield "ul", plan.omitted + ["Complete the review contact and demo account, age rating, privacy answers, "
                                 "and pricing in the console. Upload the build separately."]


def indexes(plan):
    md, page = [], ['<!doctype html><html lang="en"><meta charset="utf-8">',
                    '<meta name="viewport" content="width=device-width, initial-scale=1"><title>Listing upload</title>',
                    '<style>body{font:1rem/1.5 system-ui,sans-serif;max-width:76rem;margin:auto;padding:1.5rem}'
                    'table{border-collapse:collapse;width:100%}td,th{border:1px solid #aaa;padding:.5rem;'
                    'text-align:left;overflow-wrap:anywhere}th{background:#eee}</style><body>']
    for tag, value in guide(plan):
        if tag == "table":
            columns = ("File or folder", "Console page and field")
            md.extend(["| %s | %s |" % columns, "|---|---|"])
            page.append("<table><thead><tr><th>%s</th><th>%s</th></tr></thead><tbody>" % columns)
            for row in value:
                md.append("| %s | %s |" % tuple(map(markdown_cell, row)))
                page.append("<tr><td><code>%s</code></td><td>%s</td></tr>" % tuple(map(html.escape, row)))
            page.append("</tbody></table>")
        elif tag == "ul":
            md.extend("- " + html.escape(line, quote=False) for line in value)
            page.append("<ul>" + "".join("<li>%s</li>" % html.escape(line) for line in value) + "</ul>")
        else:
            md.append({"h1": "# ", "h2": "## ", "p": ""}[tag] + html.escape(value, quote=False).replace("\n", " "))
            page.append("<%s>%s</%s>" % (tag, html.escape(value), tag))
        md.append("")
    page.append("</body></html>")
    return {"INDEX.md": "\n".join(md), "INDEX.html": "\n".join(page) + "\n"}


def write_stage(stage, plan):
    hashes = {}
    for src, dest, _, content in plan.items:
        target = stage / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        if src is None:
            target.write_bytes(content)
        else:
            shutil.copyfile(src, target)
        hashes[str(dest)] = digest(target)
    documents = indexes(plan)
    documents[".gitignore"] = "*\n"
    for name, text in documents.items():
        (stage / name).write_text(text, encoding="utf-8")
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
            remove_tree(stage)
    if previous.exists():
        remove_tree(previous)
