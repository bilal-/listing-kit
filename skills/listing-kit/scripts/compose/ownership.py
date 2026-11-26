"""Serialize compose runs and checkpoint each published output under the app root."""
from contextlib import contextmanager, ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat

import json_input
import specs

LOCK = ".listing-kit/compose.lock.json"
RECORD = ".listing-kit/outputs.json"
HELD = ".listing-kit/held"
CONFLICT = "exists and was not written by listing-kit (or was edited); move it away or rerun with --adopt"


def _relative(name):
    return isinstance(name, str) and all(specs.component(p) for p in name.split("/"))


def _entry(entry):
    if not isinstance(entry, dict):
        return False
    for key in ("sha256", "content", "style"):
        if not isinstance(entry.get(key), str) or not re.fullmatch("[0-9a-f]{64}", entry[key]):
            return False
    renderer = entry.get("renderer")
    return ((renderer is None or isinstance(renderer, dict) and
             all(isinstance(renderer.get(k), str) for k in ("os", "browser"))) and
            ("size" not in entry or specs._size(entry["size"])) and
            (entry.get("checks") is None or isinstance(entry["checks"], dict)))


@contextmanager
def directory(root, relative, create=False):
    """Pin each parent while walking from the app root. Never follow symlinks."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as stack:
        fd = os.open(root, flags)
        stack.callback(os.close, fd)
        for part in Path(relative).parts:
            if not specs.component(part):
                raise ValueError("invalid directory: %s" % relative)
            if create:
                try:
                    os.mkdir(part, dir_fd=fd)
                except FileExistsError:
                    pass
            fd = os.open(part, flags, dir_fd=fd)
            stack.callback(os.close, fd)
        yield fd


def output_directory(root, path, create=False):
    # Plan trees can use in-app aliases. Resolve the alias, then pin the
    # resolved directories without following any more links during mutation.
    parent = (Path(root) / path.parent).resolve()
    try:
        relative = parent.relative_to(root)
    except ValueError:
        raise ValueError("output directory escapes app root: %s" % path.parent)
    return directory(root, relative, create)


class OwnershipConflict(ValueError):
    pass


def _identity(fd, name):
    try:
        file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except FileNotFoundError:
        return None
    with os.fdopen(file_fd, "rb") as stream:
        st = os.fstat(stream.fileno())
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("expected regular file: %s" % name)
        sha = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            sha.update(chunk)
    return st.st_dev, st.st_ino, sha.hexdigest()


def _temp(fd, data):
    name = ".lk-" + secrets.token_hex(12)
    handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=fd)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            st = os.fstat(out.fileno())
    except BaseException:
        os.unlink(name, dir_fd=fd)
        raise
    return name, st


class State:
    def __init__(self, root, kit):
        self.root, self.kit = root, kit
        self.lock = self.read(LOCK, {"format": 1, "outputs": {}})
        self.inventory = self.read(RECORD, {"format": 1, "files": []})
        outputs = self.lock.get("outputs")
        if not isinstance(outputs, dict) or not all(_relative(k) and _entry(v) for k, v in outputs.items()):
            raise ValueError("malformed " + LOCK)
        files = self.inventory.get("files")
        if not isinstance(files, list) or not all(_relative(k) for k in files):
            raise ValueError("malformed " + RECORD)
        self.files = set(files)
        self.outputs = outputs

    def read(self, path, default):
        try:
            fd = os.open(os.path.basename(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.kit)
        except FileNotFoundError:
            return default
        try:
            with os.fdopen(fd, encoding="utf-8") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("expected regular file")
                obj = json_input.read(stream)
            if not isinstance(obj, dict) or type(obj.get("format")) is not int or obj["format"] != 1:
                raise ValueError("expected format 1")
            return obj
        except ValueError as exc:
            raise ValueError("malformed %s: %s" % (path, exc)) from exc

    def write(self, path, obj):
        data = (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode()
        tmp, _ = _temp(self.kit, data)
        try:
            os.replace(tmp, os.path.basename(path), src_dir_fd=self.kit, dst_dir_fd=self.kit)
        finally:
            try:
                os.unlink(tmp, dir_fd=self.kit)
            except FileNotFoundError:
                pass

    def save(self):
        # Keep the pending publication in the on-disk lock until BOTH records
        # are committed. Replaying it after an interruption is idempotent.
        self.inventory["files"] = sorted(self.files)
        self.write(RECORD, self.inventory)
        self.lock.pop("pending", None)
        self.write(LOCK, self.lock)

    def recover(self):
        if "pending" not in self.lock:
            return
        p = self.lock["pending"]
        if (not isinstance(p, dict) or not _relative(p.get("path")) or not _entry(p.get("entry"))
                or not isinstance(p.get("tmp"), str) or not re.fullmatch(r"\.lk-[0-9a-f]{24}", p["tmp"])
                or not all(type(p.get(k)) is int for k in ("dev", "ino"))):
            raise ValueError("malformed pending publication in " + LOCK)
        path = Path(p["path"])
        expected = (p["dev"], p["ino"], p["entry"]["sha256"])
        with output_directory(self.root, path) as fd:
            if _identity(fd, path.name) == expected:
                self.outputs[p["path"]] = p["entry"]
                self.files.add(p["path"])
            if _identity(fd, p["tmp"]) == expected:
                os.unlink(p["tmp"], dir_fd=fd)
        self.save()

    def digest(self, rel):
        p = Path(rel)
        try:
            with output_directory(self.root, p) as fd:
                identity = _identity(fd, p.name)
        except FileNotFoundError:
            return None
        return identity[2] if identity else None

    def publish(self, rel, data, entry, adopted=None):
        path = Path(rel)
        with output_directory(self.root, path, create=True) as fd:
            tmp, st = _temp(fd, data)
            try:
                self.lock["pending"] = dict(path=rel, tmp=tmp, dev=st.st_dev, ino=st.st_ino, entry=entry)
                self.write(LOCK, self.lock)
                current = _identity(fd, path.name)
                if current:
                    if current[2] not in (self.outputs.get(rel, {}).get("sha256"), adopted):
                        raise OwnershipConflict("%s: %s" % (rel, CONFLICT))
                    os.replace(tmp, path.name, src_dir_fd=fd, dst_dir_fd=fd)
                else:
                    try:
                        os.link(tmp, path.name, src_dir_fd=fd, dst_dir_fd=fd)
                    except FileExistsError:
                        raise OwnershipConflict("%s: %s" % (rel, CONFLICT))
                self.outputs[rel] = entry
                self.files.add(rel)
                self.save()
            finally:
                try:
                    os.unlink(tmp, dir_fd=fd)
                except FileNotFoundError:
                    pass

    def hold(self, rel):
        path = Path(rel)
        with output_directory(self.root, path) as src:
            identity = _identity(src, path.name)
            if not identity or identity[2] != self.outputs.get(rel, {}).get("sha256"):
                return None
            parent = Path(HELD) / path.parent
            with directory(self.root, parent, create=True) as dst:
                suffix = 0
                while True:
                    name = path.name if not suffix else "%s.%d%s" % (path.stem, suffix, path.suffix)
                    try:
                        os.link(path.name, name, src_dir_fd=src, dst_dir_fd=dst, follow_symlinks=False)
                        break
                    except FileExistsError:
                        suffix += 1
                if _identity(dst, name) != identity or _identity(src, path.name) != identity:
                    raise ValueError("stale output changed while archiving: " + rel)
                os.unlink(path.name, dir_fd=src)
        self.outputs.pop(rel)
        self.files.discard(rel)
        self.save()
        return str(parent / name)


@contextmanager
def exclusive_state(root):
    with directory(root, ".listing-kit") as kit:
        fd = os.open("compose.flock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=kit)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("another compose run holds .listing-kit/compose.flock")
            state = State(root, kit)
            state.recover()
            yield state
        finally:
            os.close(fd)
