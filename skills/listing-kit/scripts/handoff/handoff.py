#!/usr/bin/env python3
"""Build a folder for uploading a listing by hand, sorted the way the consoles ask.

fastlane needs Apple screenshots in one flat folder per locale. That is awkward to
upload from by hand, so this writes a throwaway copy organised by store, locale and
console slot, with the text fields, graphics and an index:

  <app-root>/.listing-kit/upload/
    INDEX.md
    apple/<locale>/01 iPhone Dynamic Island (medium display)/01_home_iphone-medium.png
    apple/<locale>/text/name.txt ...
    apple/<locale>/graphics/header-16x9.png
    play/<locale>/01 Phone/01_home.png
    play/<locale>/graphics/icon.png  featureGraphic.png
    play/<locale>/text/title.txt ...

The fastlane tree stays the source. The folder is built in a temporary directory and
swapped in only when complete. Standard library only.

Usage: handoff.py <app-root> [--out <dir>] [--open]
Exit:  0 built, 1 nothing to hand over or a file could not be placed, 2 usage.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import imginfo  # noqa: E402
import listing  # noqa: E402
import specs  # noqa: E402

OUT_REL = os.path.join(".listing-kit", "upload")


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe(label):
    """A console label as a folder name on macOS, Linux and Windows."""
    out = "".join("in" if c == '"' else ("-" if c in '\\/:*?<>|' else c) for c in label)
    return out.strip(" .")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


class Plan:
    """The ordered inventory: (source or None, destination relative path, console place, text or None)."""

    def __init__(self):
        self.items = []
        self.problems = []

    def add(self, src, dest, place, text=None):
        self.items.append((src, dest, place, text))


def _apple(root, data, plan):
    fl = os.path.join(root, "fastlane")
    default = listing.apple_default(fl)
    app_fields = specs.fields(data, "apple", "app")
    loc_fields = specs.fields(data, "apple", "locale")
    slot_order = [s["id"] for s in specs.slots(data, "apple")]
    for meta in listing.apple_locales(fl):
        locale = os.path.basename(meta)
        base = os.path.join("apple", locale)
        # Text: the value in effect, falling back to metadata/default/ as deliver does.
        for f in loc_fields:
            for cand in (meta, default):
                text = _read(os.path.join(cand, f["stem"] + ".txt")) if cand else None
                if text is not None:
                    plan.add(None, os.path.join(base, "text", f["stem"] + ".txt"),
                             "App Store Connect > %s > %s" % (locale, f["label"]), text)
                    break
        for f in app_fields:
            text = _read(os.path.join(fl, "metadata", f["stem"] + ".txt"))
            if text is not None:
                plan.add(None, os.path.join(base, "text", f["stem"] + ".txt"),
                         "App Store Connect > App Information > %s" % f["label"], text)
        # Screenshots, grouped by the slot their pixel size belongs to.
        groups = {}
        for path in listing.images(os.path.join(fl, "screenshots", locale)):
            w, h, _, _ = imginfo.image_info(path)
            slot = specs.apple_slot_for_size(data, w, h)
            if not slot:
                plan.problems.append("%s: %sx%s matches no App Store slot; left out" % (path, w, h))
                continue
            groups.setdefault(slot["id"], (slot, []))[1].append(path)
        # Console-only slots keep their files under store-assets/apple/<locale>/screenshots/<slot>/.
        manual = os.path.join(root, "store-assets", "apple", locale, "screenshots")
        if os.path.isdir(manual):
            for slot_id in sorted(os.listdir(manual)):
                slot = specs.slot(data, "apple", slot_id)
                files = listing.images(os.path.join(manual, slot_id))
                if slot and files:
                    groups.setdefault(slot_id, (slot, []))[1].extend(files)
        n = 0
        for slot_id in slot_order:
            if slot_id not in groups:
                continue
            slot, files = groups[slot_id]
            n += 1
            folder = "%02d %s" % (n, _safe(slot["label"]))
            for path in files:  # listing.images sorts by name, which is store order
                plan.add(path, os.path.join(base, folder, os.path.basename(path)),
                         "App Store Connect > %s > Screenshots > %s" % (locale, slot["label"]))
        # Header assets are always uploaded by hand.
        for path in listing.images(os.path.join(root, "store-assets", "apple", locale)):
            plan.add(path, os.path.join(base, "graphics", os.path.basename(path)),
                     "App Store Connect > %s > Header Asset" % locale)


def _play(root, data, plan):
    fl = os.path.join(root, "fastlane")
    store = data["stores"]["play"]
    for loc in listing.play_locales(fl):
        locale = os.path.basename(loc)
        base = os.path.join("play", locale)
        for f in store["fields"]:
            text = _read(os.path.join(loc, f["stem"] + ".txt"))
            if text is not None:
                plan.add(None, os.path.join(base, "text", f["stem"] + ".txt"),
                         "Play Console > Main store listing > %s > %s" % (locale, f["label"]), text)
        cl = os.path.join(loc, "changelogs")
        if os.path.isdir(cl):
            for name in sorted(os.listdir(cl)):
                text = _read(os.path.join(cl, name)) if name.endswith(".txt") else None
                if text is not None:
                    plan.add(None, os.path.join(base, "text", "release-notes-" + name),
                             "Play Console > Release > Release notes > %s (%s)" % (locale, name[:-4]), text)
        img = os.path.join(loc, "images")
        for g in store["graphics"]:
            for ext in ("png", "jpg", "jpeg"):
                path = os.path.join(img, "%s.%s" % (g["file"], ext))
                if os.path.isfile(path):
                    plan.add(path, os.path.join(base, "graphics", os.path.basename(path)),
                             "Play Console > Main store listing > %s > %s" % (locale, g["label"]))
                    break
        n = 0
        for slot in specs.slots(data, "play"):
            files = listing.images(os.path.join(img, slot["folder"])) if slot.get("folder") else []
            manual = os.path.join(root, "store-assets", "play", locale, "screenshots", slot["id"])
            files += listing.images(manual)
            if not files:
                continue
            n += 1
            folder = "%02d %s" % (n, _safe(slot["label"]))
            for path in files:
                plan.add(path, os.path.join(base, folder, os.path.basename(path)),
                         "Play Console > Main store listing > %s > %s screenshots" % (locale, slot["label"]))


def inventory(root):
    data = specs.load(root)
    plan = Plan()
    _apple(root, data, plan)
    _play(root, data, plan)
    seen = set()
    for _, dest, _, _ in plan.items:
        key = dest.lower()  # case-insensitive filesystems
        if key in seen:
            plan.problems.append("two files would land on %s" % dest)
        seen.add(key)
    return plan, data


def build(root, out=None):
    """Write the folder. Returns (out path, item count, problems)."""
    out = os.path.abspath(out or os.path.join(root, OUT_REL))
    plan, data = inventory(root)
    if not plan.items:
        return out, 0, plan.problems + ["no listing found under %s/fastlane" % root]
    if plan.problems:
        return out, len(plan.items), plan.problems
    parent = os.path.dirname(out)
    os.makedirs(parent, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".upload-", dir=parent)
    try:
        rows = []
        for src, dest, place, text in plan.items:
            target = os.path.join(tmp, dest)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if src:
                shutil.copyfile(src, target)
            else:
                with open(target, "w", encoding="utf-8", newline="") as f:
                    f.write(text)
            rows.append((dest.replace(os.sep, "/"), place, _sha(target)[:12]))
        with open(os.path.join(tmp, "INDEX.md"), "w", encoding="utf-8") as f:
            f.write("# Files to upload by hand\n\n")
            f.write("Built from the listing in this repository (store rules checked %s).\n" % data["verified"])
            f.write("This folder is a copy: edit the source files, then rebuild it.\n")
            f.write("Upload the screenshots in each numbered folder in file-name order.\n\n")
            f.write("| File | Where it goes | sha256 |\n|---|---|---|\n")
            for dest, place, digest in rows:
                f.write("| `%s` | %s | `%s` |\n" % (dest, place.replace("|", "/"), digest))
        old = None
        if os.path.lexists(out):
            old = tempfile.mkdtemp(prefix=".upload-old-", dir=parent)
            os.rmdir(old)
            os.rename(out, old)
        os.rename(tmp, out)
        if old:
            shutil.rmtree(old, ignore_errors=True)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return out, len(plan.items), []


def open_folder(path):
    """Reveal a folder with the system's opener. Returns False when there is none."""
    if sys.platform == "darwin":
        cmd = ["open", path]
    elif os.name == "nt":
        cmd = ["explorer", path]
    else:
        cmd = ["xdg-open", path]
    if not shutil.which(cmd[0]):
        return False
    try:
        rc = subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return rc == 0 or os.name == "nt"  # explorer returns 1 on success


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    out = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 >= len(argv):
            sys.stderr.write(__doc__)
            return 2
        out = argv[i + 1]
        args = [a for a in args if a != out]
    if len(args) != 1 or not os.path.isdir(args[0]):
        sys.stderr.write(__doc__)
        return 2
    try:
        path, count, problems = build(args[0], out)
    except specs.SpecsError as e:
        sys.stderr.write("handoff: %s\n" % e)
        return 1
    if problems:
        for p in problems:
            sys.stderr.write("handoff: %s\n" % p)
        sys.stderr.write("handoff: nothing was written.\n")
        return 1
    print("Upload folder: %s (%d files; see INDEX.md)" % (path, count))
    if "--open" in argv and not open_folder(path):
        print("Could not open a file manager here; open the folder above yourself.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
