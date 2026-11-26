#!/usr/bin/env python3
"""Manage a single app's listing through fastlane deliver and supply."""
import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "lib"))
import apple_assets
import imginfo
import listing
import plan
import secret_scan
import specs

PUBLISH_ENABLED = {"apple": False, "play": False}
CREDENTIAL = {
    "apple": ("appleApiKeyPath", "APP_STORE_CONNECT_API_KEY_PATH", "App Store Connect API key JSON"),
    "play": ("playJsonKeyPath", "SUPPLY_JSON_KEY", "Google Play service-account JSON"),
}
IMAGE = {".png", ".jpg", ".jpeg"}
INSTALL = ("Install fastlane with 'gem install fastlane' (Ruby 3.2+ for 2.242.0), "
           "or run 'bundle install' for the project's Gemfile. Manual path: scripts/handoff/handoff.py")


class MissingFastlane(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path, fallback):
    try:
        with path.open(encoding="utf-8") as stream:
            obj = json.load(stream)
    except FileNotFoundError:
        return fallback
    if not isinstance(obj, dict):
        raise ValueError("Expected a JSON object in %s" % path)
    return obj


def safe(root, path):
    """Refuse indirect writes, including an absent file beneath a symlink."""
    rel = path.relative_to(root)
    current = root
    for component in rel.parts:
        current /= component
        if component in (".git", "..") or current.is_symlink():
            raise ValueError("Unsafe listing path: %s" % current)
    return path


def atomic(path, data, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            if mode is not None:
                os.fchmod(stream.fileno(), mode)
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()


def write_json(path, obj):
    atomic(path, (json.dumps(obj, sort_keys=True, indent=2) + "\n").encode(), 0o600)


def record(path, store, entry):
    obj = read_json(path, {"format": 1, "stores": {}})
    obj["stores"][store] = entry
    write_json(path, obj)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def comparable(store, raw):
    return raw.strip(b" \t\n\r\v\f\0") if store == "apple" else raw


def fingerprint(files):
    return sha(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())


def fail_walk(error):
    raise error


def scan_credentials(repo):
    """Check even ignored files in sibling apps. Git internals are outside the worktree."""
    for parent, dirs, files in os.walk(repo, onerror=fail_walk):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            path = Path(parent, name)
            if path.suffix.lower() == ".p8":
                raise ValueError("Found a .p8 credential; move it outside the repository")
            if path.suffix.lower() != ".json" or not path.is_file():
                continue
            try:
                obj = json.loads(path.read_bytes())
            except (ValueError, UnicodeError):
                continue
            if isinstance(obj, dict) and (obj.get("type") == "service_account"
                                          or {"key_id", "key"} <= obj.keys()):
                raise ValueError("Found a store credential; move it outside the repository")


def read_key(root, repo, store, args, config):
    field, env, description = CREDENTIAL[store]
    given = getattr(args, "apple_api_key_path" if store == "apple" else "play_json_key_path", None)
    value = given or os.environ.get(env) or config.get("fastlane", {}).get(field)
    if not value:
        raise ValueError("Set %s to the external %s path, or use fastlane setup" % (env, description))
    path = root / Path(value).expanduser()
    if repo in path.absolute().parents or repo in path.resolve().parents:
        raise ValueError("Credential is inside the repository; move it outside the repository")
    if not path.is_file():
        raise ValueError("Credential file does not exist for %s" % store)
    return path.resolve()


@dataclass
class Store:
    name: str
    app: str
    root: Path
    trees: dict
    rules: dict
    data: dict
    manifest: dict
    track: str
    code: str
    key: Path = None

    @property
    def selector(self):
        return "editable version (deliver default)" if self.name == "apple" else self.track

    @property
    def identity(self):
        return {"app": self.app, "selector": self.selector}

    def state(self, name):
        return safe(self.root, self.root / ".listing-kit" / name)

    def key_args(self):
        if self.name == "apple":
            return ["--app_identifier", self.app, "--api_key_path", str(self.key)]
        return ["--package_name", self.app, "--json_key", str(self.key), "--track", self.track]

    def tool(self):
        for parent in (self.trees["fastlaneDir"], self.root):
            gemfile = parent / "Gemfile"
            if gemfile.is_file() and re.search(r"(?m)^[^#\n]*\bfastlane\b", gemfile.read_text()):
                return ["bundle", "exec", "fastlane"], gemfile
        return ["fastlane"], None

    def run(self, args, cwd, version=False):
        prefix, gemfile = self.tool()
        # A clean cwd precludes implicit Deliverfile, Supplyfile and binary discovery.
        # Remove inherited tool overrides, including JSON objects and submission settings.
        env = {k: v for k, v in os.environ.items() if not k.startswith(
            ("DELIVER_", "SUPPLY_", "FASTLANE_", "APP_STORE_CONNECT_", "BUNDLE_GEMFILE"))}
        env.update(FASTLANE_SKIP_UPDATE_CHECK="1", FASTLANE_OPT_OUT_USAGE="1")
        if gemfile:
            env["BUNDLE_GEMFILE"] = str(gemfile)
        try:
            result = subprocess.run(prefix + args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except FileNotFoundError:
            raise MissingFastlane(INSTALL)
        if version:
            # UNVERIFIED in S3: the global fastlane --version switch/output.
            match = re.search(rb"\bfastlane\s+(\d+(?:\.\d+)+)", result.stdout, re.I)
            if result.returncode or not match:
                raise MissingFastlane(INSTALL)
            print("fastlane", match.group(1).decode())
        elif result.returncode:
            # Fastlane can include credentials in diagnostics. Only emit known error categories.
            hints = (b"unauthorized", b"forbidden", b"not found", b"invalid credentials",
                     b"permission denied", b"authentication failed")
            reason = next((h.decode() for h in hints if h in result.stdout.lower()), "action failed")
            raise ValueError("%s %s for %s (exit %d)" % (args[0], reason, self.app, result.returncode))


def selected(args, root, rules):
    data = manifest = {}
    if (root / plan.LISTING).exists():
        data = plan.load(root)
        manifest = plan.manifest(data, rules, root)
        trees = manifest["trees"]
        ids = manifest["app"]
        active = {t["store"] for t in plan.targets(data)}
    else:
        trees = plan._trees({})
        ids = {"apple": args.app_identifier, "play": args.package_name}
        meta = root / trees["apple"]["metadata"]
        active = set()
        if (root / trees["apple"]["screenshots"]).is_dir() or (
            meta.is_dir() and (not (meta / "android").is_dir() or any(
                p.name != "android" and not p.name.startswith(".") for p in meta.iterdir()))):
            active.add("apple")
        if (root / trees["play"]["metadata"]).is_dir():
            active.add("play")
    names = [args.store] if args.store else [s for s in CREDENTIAL if s in active]
    if not names:
        raise ValueError("No active store or listing tree; specify --store and its app id")
    stores = []
    for name in names:
        if not ids.get(name):
            raise ValueError("Missing %s app id (%s)" % (name, "--app-identifier" if name == "apple" else "--package-name"))
        paths = {k: safe(root, root / v) for k, v in trees[name].items()}
        stores.append(Store(name, ids[name], root, paths, rules, data, manifest, args.track,
                            getattr(args, "version_code", None)))
    return stores


def download(store, scratch):
    scratch.mkdir()
    metadata = scratch / "metadata"
    args = store.key_args()
    if store.name == "apple":
        store.run(["deliver", "download_metadata", *args, "--metadata_path", str(metadata), "--force"], scratch)
        store.run(["deliver", "download_screenshots", *args, "--screenshots_path",
                   str(scratch / "screenshots")], scratch)
    else:
        store.run(["supply", "init", *args, "--metadata_path", str(metadata)], scratch)
    if not metadata.is_dir():
        raise ValueError("fastlane returned without downloading metadata for %s" % store.app)
    return inventory(store, metadata, scratch / "screenshots" if store.name == "apple" else metadata)


def is_locale(name):
    return bool(plan.LOCALE.fullmatch(name)) and name != "android"


@dataclass
class Inventory:
    text: dict
    shots: dict
    graphics: dict

    def files(self):
        return {**self.text, **self.shots, **self.graphics}

    def hashes(self):
        return {k: file_hash(v) for k, v in self.files().items()}


def inventory(store, meta, shots):
    """Whitelist store listing fields. Never traverse console, review credentials or other stores."""
    result = Inventory({}, {}, {})
    fields = specs.fields(store.rules, store.name)
    for row in fields:
        if row["scope"] == "app":
            path = meta / (row["stem"] + ".txt")
            if path.is_file():
                result.text["metadata/" + path.name] = safe(meta, path)
    for loc in sorted(meta.iterdir()) if meta.is_dir() else []:
        if not loc.is_dir() or not (is_locale(loc.name) or (store.name == "apple" and loc.name == "default")):
            continue
        safe(meta, loc)
        for row in fields:
            if row["scope"] == "locale":
                path = loc / (row["stem"] + ".txt")
                if path.is_file():
                    result.text["metadata/" + path.relative_to(meta).as_posix()] = safe(meta, path)
        if store.name == "play":
            for path in sorted((loc / "changelogs").glob("*.txt")):
                if re.fullmatch(r"(?:[0-9]+|default)\.txt", path.name) and path.is_file():
                    result.text["metadata/" + path.relative_to(meta).as_posix()] = safe(meta, path)
    folders = {s.get("folder") for s in specs.slots(store.rules, "play")}
    for path in sorted(shots.rglob("*")) if shots.is_dir() else []:
        if path.suffix.lower() not in IMAGE or not path.is_file() or path.name.startswith("."):
            continue
        rel = path.relative_to(shots)
        parts = rel.parts
        if store.name == "apple":
            if ((len(parts) == 2 and (is_locale(parts[0]) or parts[0] == "default"))
                or (len(parts) == 3 and parts[0] in ("appleTV", "iMessage") and is_locale(parts[1]))):
                result.shots["screenshots/" + rel.as_posix()] = safe(shots, path)
        elif len(parts) >= 3 and is_locale(parts[0]) and parts[1] == "images":
            key = "metadata/" + rel.as_posix()
            if len(parts) == 4 and parts[2] in folders:
                result.shots[key] = safe(shots, path)
            elif len(parts) == 3 and path.stem in ("featureGraphic", "icon", "tvBanner"):
                result.graphics[key] = safe(shots, path)
    return result


def workspace_file(store, key):
    tree, rel = key.split("/", 1)
    return safe(store.root, store.trees[tree] / rel)


def pull(store, remote):
    lock = store.state("remote.lock.json")
    old = read_json(lock, {}).get("stores", {}).get(store.name, {})
    if old.get("identity", store.identity) != store.identity:
        raise ValueError("Previous pull was for another app or track; review remote.lock.json")
    # Remember the common ancestor across incomplete downloads and unresolved conflicts.
    ancestors = old.get("ancestors", old.get("files", {})).copy()
    conflicts = False
    staged = set()
    if plan._repo_root(store.root):
        raw = subprocess.check_output(["git", "diff", "--cached", "--name-only", "--relative", "-z"],
                                      cwd=store.root)
        staged = {store.root / os.fsdecode(p) for p in raw.split(b"\0") if p}
    for key, source in remote.text.items():
        dest = workspace_file(store, key)
        raw = source.read_bytes()
        fresh = sha(comparable(store.name, raw))
        current = sha(comparable(store.name, dest.read_bytes())) if dest.is_file() else None
        base = ancestors.get(key)
        if current != fresh and fresh != base:
            if current != base or dest in staged:
                print("conflict", key, "— local file retained")
                atomic(store.state("remote/" + store.name + "/" + key), raw)
                conflicts = True
                continue
            atomic(dest, raw, 0o644)
            print("updated", dest)
        ancestors[key] = fresh
    for key, path in remote.shots.items():
        dest = store.state("remote/" + store.name + "/" + key)
        atomic(dest, path.read_bytes())
    record(lock, store.name, dict(identity=store.identity, pulledAt=now(), files=remote.hashes(),
                                  ancestors=ancestors))
    return conflicts


def target_locales(store, target):
    return [loc[store.name] for loc in plan._target_locales(
        [plan._locale(item) for item in store.data["locales"]], target)]


def prepared(store, view):
    source = inventory(store, store.trees["metadata"], store.trees["screenshots"])
    metadata = view / ("fastlane/metadata" if store.name == "apple" else "fastlane/metadata/android")
    screenshots = view / "fastlane/screenshots" if store.name == "apple" else metadata
    if store.data:
        active = plan.targets(store.data, store.name)
        locales = {loc for target in active for loc in target_locales(store, target)}
        if not locales:
            raise ValueError("No active %s target locales to publish" % store.name)
        approved = {store.root / row["outputPath"] for row in store.manifest["outputs"]
                    if row["store"] == store.name and row["upload"] == "fastlane" and row["kind"] == "screenshot"}
        for path in approved:
            if path not in source.shots.values():
                raise ValueError("Missing planned screenshot: %s" % path)
        source.shots = {k: p for k, p in source.shots.items() if p in approved}
        source.text = {k: p for k, p in source.text.items() if len(k.split("/")) == 2
                       or k.split("/")[1] in locales | {"default"}}
        source.graphics = {k: p for k, p in source.graphics.items() if k.split("/")[1] in locales}
    if store.name == "apple":
        legacy = apple_assets.load_plan(store.root)
        source.shots = {k: p for k, p in source.shots.items() if not apple_assets.is_deferred(
            p, legacy.get(p.parent.name, {}).get("deferredScreenshots", {}))}
    for key, path in source.files().items():
        tree, rel = key.split("/", 1)
        dest = (metadata if tree == "metadata" else screenshots) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    override = store.root / specs.OVERRIDE
    if override.exists():
        dest = view / specs.OVERRIDE
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(override, dest)
    env = dict(os.environ, LK_REVIEW_DISPLAY_ROOT=str(store.root))
    facts = specs.conditions_from_plan(store.data, rules=store.rules)
    for key, var in (("supportsIpad", "LK_SUPPORTS_IPAD"), ("supportsIphone", "LK_SUPPORTS_IPHONE")):
        if key in facts:
            env[var] = str(int(facts[key]))
    # Preserve native/Expo tablet detection when validating the isolated store view.
    if store.name == "apple" and "LK_SUPPORTS_IPAD" not in env:
        for parent, dirs, names in os.walk(store.root):
            dirs[:] = [d for d in dirs if d not in (".git", ".listing-kit", "node_modules", "Pods",
                                                    "build", "DerivedData", ".expo", "dist", ".dart_tool")]
            for name in names:
                p = Path(parent, name)
                if (p.parent == store.root and name in ("app.json", "app.config.json", "app.config.js",
                                                        "app.config.ts", "app.config.mjs", "app.config.cjs")
                        or name.endswith(".pbxproj") or name == "Info.plist"):
                    dest = view / p.relative_to(store.root)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(safe(store.root, p), dest)
    subprocess.run(["bash", str(SCRIPTS / "validate/validate-listing.sh"), str(view)], env=env, check=True)
    return inventory(store, metadata, screenshots)


def photo_groups(store, images, downloaded=False):
    groups = defaultdict(list)
    for key, path in images.items():
        parts = key.split("/")
        if store.name == "apple":
            loc = parts[-2]
            slot = specs.apple_slot_for_file(store.rules, *imginfo.image_info(path)[:2], key)
            display = slot["id"] if slot else "unknown"
            if parts[1] == "iMessage":
                display = "iMessage/" + display
        else:
            loc, display = parts[1], parts[-2]
        groups[loc, display].append(key)
    for members in groups.values():
        if downloaded:
            # UNVERIFIED on a live record: numbered download basenames reflect store order.
            members.sort(key=lambda k: [int(s) if i % 2 else s for i, s in
                                        enumerate(re.split(r"(\d+)", k))])
        else:
            members.sort()
    return groups


def summary(store, local, remote):
    send = {}
    text = local.text.copy()
    if store.name == "apple":
        # Materialize default fields for actual locales. Never upload a broad default folder.
        locales = {k.split("/")[1] for k in text if len(k.split("/")) == 3} - {"default"}
        if store.data:
            locales.update(loc for t in plan.targets(store.data, store.name) for loc in target_locales(store, t))
        else:
            locales.update(k.split("/")[-2] for k in local.shots)
        for key in list(text):
            if key.startswith("metadata/default/"):
                path = text.pop(key)
                if not locales:
                    print("cannot compare Apple default without a concrete locale:", key)
                for loc in locales:
                    text.setdefault("metadata/%s/%s" % (loc, path.name), path)
    notes = {}
    for key, path in sorted(text.items()):
        if "/changelogs/" in key:
            if not store.code or path.stem not in ("default", store.code):
                print("held", key, "(requires matching --version-code)")
                continue
            versioned = str(Path(key).with_name(store.code + ".txt"))
            notes[versioned] = text.get(versioned, path)
            continue
        raw = comparable(store.name, path.read_bytes())
        if store.name == "apple" and not raw:
            print("cannot send empty Apple field", key)
            continue
        other = remote.text.get(key)
        if other is None or raw != comparable(store.name, other.read_bytes()):
            print(store.name, key, "changed" if other else "added (cannot compare: absent from download)")
            send[key] = path

    if any(k not in remote.text or p.read_bytes() != remote.text[k].read_bytes() for k, p in notes.items()):
        # Supply replaces release_notes. Include every observed translation for this version.
        # Missing notes in a supplied locale become empty strings in fastlane.
        for key, path in remote.text.items():
            if key.endswith("/changelogs/%s.txt" % store.code):
                notes.setdefault(key, path)
        for key, path in notes.items():
            status = "added" if key not in remote.text else (
                "changed" if path.read_bytes() != remote.text[key].read_bytes() else "retained")
            print(store.name, key, status)
        send.update(notes)

    ours = photo_groups(store, local.shots)
    theirs = photo_groups(store, remote.shots, downloaded=True)
    changed = set()
    blocked = set()
    for group in sorted(ours.keys() | theirs.keys()):
        mine, live = ours.get(group, []), theirs.get(group, [])
        if not mine:
            print(store.name, *group, "remote only:", len(live), "images")
            continue
        different = [file_hash(local.shots[k]) for k in mine] != [file_hash(remote.shots[k]) for k in live]
        print(store.name, *group, "%d local images," % len(mine),
              ("%d remote images" % len(live)) if live else "cannot compare (missing download)",
              "— replacement requested" if different and live else "— unchanged" if live else "")
        if different and live:
            changed.add(group)
        elif not live:
            # An absent download is not proof that an existing gallery is empty.
            # Include a new slot only with a comparable locale-wide Apple replacement.
            blocked.add(group)
    if store.name == "apple" and changed:
        locales = {loc for loc, _ in changed}
        print("WARNING: overwrite_screenshots deletes every screenshot set for each locale being uploaded,"
              " including any uploaded by hand.")
        protected = {loc for t in plan.targets(store.data, "apple") for loc in target_locales(store, t)
                     if t.get("upload", specs.slot(store.rules, "apple", t["slot"])["upload"]) == "console"
                     } if store.data else set()
        missing = {loc for loc, slot in theirs if (loc, slot) not in ours}
        if (locales & (protected | missing | {"default"})
                or any(slot.endswith("unknown") for loc, slot in ours if loc in locales)):
            raise ValueError("Apple replacement could erase an unrestorable slot; use the hand-upload folder")
        for group, members in ours.items():
            if group[0] in locales:
                print("restore", *group, "%d local images replace %d downloaded" %
                      (len(members), len(theirs.get(group, []))))
                send.update((key, local.shots[key]) for key in members)
                blocked.discard(group)
    else:
        for group in sorted(changed):
            send.update((key, local.shots[key]) for key in ours[group])
    if blocked:
        print("Uncompared screenshot slots require the hand-upload folder.")
    return send


def upload_args(store, send, folder):
    has_shots = any(p.suffix.lower() in IMAGE for p in send.values())
    has_text = any(p.suffix == ".txt" and "/changelogs/" not in k for k, p in send.items())
    meta = str(folder / "metadata")
    if store.name == "apple":
        args = ["deliver", *store.key_args(), "--skip_binary_upload", "--force", "--submit_for_review",
                "false", "--run_precheck_before_submit", "false", "--metadata_path", meta]
        if not has_text:
            args.append("--skip_metadata")
        if has_shots:
            args.extend(["--screenshots_path", str(folder / "screenshots"), "--overwrite_screenshots"])
        else:
            args.append("--skip_screenshots")
        return args
    args = ["supply", *store.key_args(), "--metadata_path", meta, "--skip_upload_apk", "--skip_upload_aab",
            "--skip_upload_images", "--changes_not_sent_for_review", "true",
            "--rescue_changes_not_sent_for_review", "false"]
    if store.code:
        args.extend(["--version_code", store.code])
    if not any("/changelogs/" in key for key in send):
        args.append("--skip_upload_changelogs")
    elif {k.split("/")[1] for k in send if "/changelogs/" not in k} - {
            k.split("/")[1] for k in send if "/changelogs/" in k}:
        raise ValueError("These locales would receive blank release notes; supply notes or omit --version-code")
    if not has_shots:
        args.append("--skip_upload_screenshots")
    if not has_text:
        args.append("--skip_upload_metadata")
    return args


def publish(store, local, scratch, yes):
    remote = download(store, scratch / "before")
    send = summary(store, local, remote)
    receipt = store.state("publish.receipt.json")
    previous = read_json(receipt, {}).get("stores", {}).get(store.name, {})
    if not send:
        print(store.name, "no comparable changes to publish")
        if previous.get("identity") == store.identity:
            print("Checked previous receipt against fresh store download.")
        return
    folder = scratch / "upload"
    (folder / "metadata").mkdir(parents=True)
    for key, path in send.items():
        dest = folder / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    args = upload_args(store, send, folder)
    print("Would run", shlex.join(store.tool()[0] + args), flush=True)
    enabled = PUBLISH_ENABLED[store.name] or os.environ.get("LK_PUBLISH_UNVERIFIED") == "1"
    if not enabled:
        print("publishing to %s is not enabled in this version of listing-kit until it has passed a live test;"
              " use the hand-upload folder" % store.name)
        if not yes:
            return
    elif not yes and (not sys.stdin.isatty() or input("Type yes to approve this transfer: ") != "yes"):
        raise ValueError("No confirmation; non-interactive publish requires --yes")
    approval = dict(identity=store.identity, files={k: file_hash(folder / k) for k in send},
                    baseline=fingerprint(remote.hashes()), versionCode=store.code, approvedAt=now())
    record(store.state("publish.approved.json"), store.name, approval)
    if not enabled:
        return
    latest = download(store, scratch / "recheck")
    if fingerprint(latest.hashes()) != approval["baseline"]:
        print("Remote baseline changed. Review the new summary and confirm again.")
        summary(store, local, latest)
        raise ValueError("Rerun publish for a new confirmation")
    store.run(args, folder)
    history = previous.get("operations", [])
    history.append(dict(approval, completedAt=now()))
    record(receipt, store.name, dict(identity=store.identity, operations=history))
    print("Completed", store.name)


def configure(store, args, config):
    field, _, _ = CREDENTIAL[store.name]
    flag = args.apple_api_key_path if store.name == "apple" else args.play_json_key_path
    if flag:
        local = store.state("local.json")
        if secret_scan.tracked(local):
            raise ValueError(".listing-kit/local.json is tracked; remove it from the git index first")
        ignore = safe(store.root, store.root / ".gitignore")
        raw = ignore.read_bytes() if ignore.exists() else b""
        line = b".listing-kit/local.json"
        if line not in raw.splitlines():
            atomic(ignore, raw + (b"\n" if raw and not raw.endswith(b"\n") else b"") + line + b"\n", 0o644)
        config.setdefault("fastlane", {})[field] = str(store.key)
        write_json(local, config)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("setup", "pull", "publish"):
        sub = subs.add_parser(name)
        sub.add_argument("root", nargs="?", default=".")
        sub.add_argument("--app-root")
        sub.add_argument("--store", choices=CREDENTIAL)
        sub.add_argument("--app-identifier")
        sub.add_argument("--package-name")
        sub.add_argument("--track", default="production")
        if name == "setup":
            sub.add_argument("--apple-api-key-path")
            sub.add_argument("--play-json-key-path")
        if name == "publish":
            sub.add_argument("--yes", action="store_true")
            sub.add_argument("--version-code", type=version_code)
    args = parser.parse_args(argv)
    root = Path(args.app_root or args.root).resolve(strict=True)
    repo = plan._repo_root(root) or root
    rules = specs.load(root)
    stores = selected(args, root, rules)
    config = read_json(stores[0].state("local.json"), {})
    for store in stores:
        field, env, description = CREDENTIAL[store.name]
        given = getattr(args, "apple_api_key_path" if store.name == "apple" else "play_json_key_path", None)
        account = given or os.environ.get(env) or config.get("fastlane", {}).get(field, "(unconfigured)")
        print("%s app %s | %s %s | account credential %s" % (
            store.name, store.app, "version" if store.name == "apple" else "track", store.selector, account))
        print("fastlaneDir={fastlaneDir} metadata={metadata} screenshots={screenshots}".format(**store.trees))
        print("Requires an editable version in App Store Connect." if store.name == "apple" else
              "Requires a first build already uploaded in Play Console.", flush=True)
    state = safe(root, root / ".listing-kit")
    state.mkdir(exist_ok=True)
    # Lock the directory itself, avoiding stale lock files after interruption.
    fd = os.open(str(state), os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        config = read_json(stores[0].state("local.json"), {})
        with tempfile.TemporaryDirectory(prefix="listing-kit-fastlane-") as tmp:
            scratch = Path(tmp)
            views = {}
            for store in stores:
                store.run(["--version"], scratch, version=True)
                if args.command == "setup":
                    field, env, description = CREDENTIAL[store.name]
                    print("Keep the %s outside the repository; set %s or .listing-kit/local.json fastlane.%s."
                          % (description, env, field))
                store.key = read_key(root, repo, store.name, args, config)
            scan_credentials(repo)
            if args.command == "publish":
                if stores[0].data:
                    subprocess.run([sys.executable, "-EsB", str(SCRIPTS / "lib/plan.py"), "check", str(root),
                                    "--for", "publish"], check=True)
                for store in stores:
                    views[store.name] = prepared(store, scratch / (store.name + "-view"))
            conflicts = False
            for store in stores:
                dest = scratch / store.name
                if args.command == "publish":
                    dest.mkdir()
                    publish(store, views[store.name], dest, args.yes)
                elif args.command == "setup":
                    configure(store, args, config)
                    download(store, dest)
                    print("Read-only access confirmed for", store.name, store.app)
                else:
                    remote = download(store, dest)
                    conflicts |= pull(store, remote)
                    if not store.data:
                        print("Initialize listing targets and flows with the listing-kit planning step.")
            return int(conflicts)
    finally:
        os.close(fd)


def version_code(value):
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise argparse.ArgumentTypeError("expected a positive Play version code")
    return value


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except MissingFastlane as exc:
        print(exc, file=sys.stderr)
        sys.exit(3)
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError, specs.SpecsError) as exc:
        print("listing-kit:", exc, file=sys.stderr)
        sys.exit(1)
