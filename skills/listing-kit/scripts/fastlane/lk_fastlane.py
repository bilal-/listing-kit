#!/usr/bin/env python3
"""Manage a single app's listing through fastlane deliver and supply."""
import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "lib"))
import apple_assets
import detect
import imginfo
import listing
import plan
from review_inputs import write_view_plan
import secret_scan
import specs

# UNVERIFIED: real account access and store-side effects on versions, gallery
# order, builds, review state and Play tracks require the disposable-app tests.
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


class ChildTimeout(Exception):
    pass


def run_child(command, *, upload=False, check=False, **options):
    timeout = float(os.environ.get("LK_FASTLANE_TIMEOUT", 900 if upload else 300))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("LK_FASTLANE_TIMEOUT must be a positive finite number of seconds")
    with subprocess.Popen(command, start_new_session=True, **options) as child:
        try:
            stdout, stderr = child.communicate(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.communicate()
            if isinstance(exc, KeyboardInterrupt):
                raise
            raise ChildTimeout("%s timed out after %g seconds" % (Path(command[0]).name, timeout))
        result = subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result


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


def read_state(path):
    try:
        obj = read_json(path, {"format": 2, "stores": {}})
        if type(obj.get("format")) is not int or obj["format"] != 2:
            raise ValueError
        for name, entry in obj["stores"].items():
            if name not in CREDENTIAL or not isinstance(entry["identity"], dict):
                raise ValueError
            if path.name == "remote.lock.json":
                maps = ("files", "ancestors", "workingBytes", "galleries", "remoteGalleries")
                if not all(isinstance(entry[k], dict) for k in maps) or not isinstance(entry["appliedOperations"], list):
                    raise ValueError
            elif path.name == "publish.receipt.json":
                if not isinstance(entry["operations"], list):
                    raise ValueError
                for op in entry["operations"]:
                    if (op["store"] != name or op["identity"] != entry["identity"] or not op["operation"]
                            or op["status"] not in ("pending", "done", "resolved", "failed")
                            or op["manifestHash"] != fingerprint(dict(files=op["files"], galleries=op["galleries"]))):
                        raise ValueError
        return obj
    except (ValueError, TypeError, KeyError, AttributeError):
        pass
    raise ValueError("Unrecognized state format: delete %s and pull again" % path)


def record(path, store, entry):
    obj = read_state(path)
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


def read_key(root, repo, store, args, config):
    field, env, description = CREDENTIAL[store]
    given = getattr(args, "apple_api_key_path" if store == "apple" else "play_json_key_path", None)
    value = given or os.environ.get(env) or config.get("fastlane", {}).get(field)
    if not value:
        raise ValueError("Set %s to the external %s path, or use fastlane setup" % (env, description))
    if not isinstance(value, str) or not value.isprintable() or value.lstrip().startswith("{"):
        raise ValueError("Expected a credential file path for %s" % store)
    path = root / Path(value).expanduser()
    if repo in Path(os.path.abspath(path)).parents or repo in path.resolve().parents:
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
    screenshots: tuple = ()

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
        directory = self.trees["fastlaneDir"]
        for parent in (directory, directory.parent, self.root):
            gemfile = parent / "Gemfile"
            if gemfile.is_file() and re.search(r"(?m)^[^#\n]*\bfastlane\b", gemfile.read_text()):
                return ["bundle", "exec", "fastlane"], gemfile
        return ["fastlane"], None

    def run(self, args, cwd, upload=False):
        prefix, gemfile = self.tool()
        # A clean cwd precludes implicit Deliverfile, Supplyfile and binary discovery.
        # Remove inherited tool overrides, including JSON objects and submission settings.
        env = {k: v for k, v in os.environ.items() if not k.startswith(
            ("DELIVER_", "SUPPLY_", "FASTLANE_", "APP_STORE_CONNECT_", "BUNDLE_GEMFILE"))}
        # UNVERIFIED in S3: fastlane update-check and telemetry environment switches.
        env.update(FASTLANE_SKIP_UPDATE_CHECK="1", FASTLANE_OPT_OUT_USAGE="1")
        if gemfile:
            # UNVERIFIED in S3: Bundler resolves the selected project from BUNDLE_GEMFILE.
            env["BUNDLE_GEMFILE"] = str(gemfile)
        try:
            result = run_child(prefix + args, upload=upload, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except FileNotFoundError:
            raise MissingFastlane(INSTALL)
        if result.returncode == 127:
            raise MissingFastlane(INSTALL)
        if result.returncode:
            # Fastlane can include credentials in diagnostics. Only emit known error categories.
            hints = (b"unauthorized", b"forbidden", b"not found", b"invalid credentials",
                     b"permission denied", b"authentication failed")
            reason = next((h.decode() for h in hints if h in result.stdout.lower()), "action failed")
            raise ValueError("%s %s for %s (exit %d)" % (args[0], reason, self.app, result.returncode))

        return result.stdout


def report_version(store, cwd):
    # Global --version and its output are unverified against the S3 facts file.
    try:
        output = store.run(["--version"], cwd)
    except (MissingFastlane, ChildTimeout, ValueError, OSError):
        return
    match = re.search(rb"\bfastlane\s+(\d+(?:\.\d+)+)", output, re.I)
    if match:
        print("fastlane", match.group(1).decode())


def selected(args, root, rules):
    data = manifest = {}
    if (root / plan.LISTING).exists():
        data = plan.load(root)
        manifest = plan.manifest(data, rules, root)
        trees = manifest["trees"]
        ids = manifest["app"]
        for name, flag, supplied in (("apple", "--app-identifier", args.app_identifier),
                                     ("play", "--package-name", args.package_name)):
            if supplied is not None and ids.get(name) != supplied:
                raise argparse.ArgumentError(None, "%s %r conflicts with plan id %r for %s" %
                                             (flag, supplied, ids.get(name), name))
        active = {t["store"] for t in plan.targets(data)}
    else:
        trees = plan._trees({}, root)
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
    return inventory(store, metadata, scratch / "screenshots" if store.name == "apple" else metadata, downloaded=True)


def is_locale(name):
    return bool(plan.LOCALE.fullmatch(name)) and name != "android"


@dataclass
class Inventory:
    text: dict
    shots: dict
    graphics: dict
    listing_locales: set = field(default_factory=set)

    def snapshot_hash(self):
        return fingerprint(dict(files=self.hashes(), locales=sorted(self.listing_locales)))

    def missing_note_locales(self, code):
        suffix = "/changelogs/%s.txt" % code
        observed = {key.split("/")[1] for key in self.text if key.endswith(suffix)}
        return self.listing_locales - observed

    def files(self):
        return {**self.text, **self.shots, **self.graphics}

    def hashes(self):
        return {k: file_hash(v) for k, v in self.files().items()}


def inventory(store, meta, shots, downloaded=False):
    """Whitelist store listing fields. Never traverse console, review credentials or other stores."""
    result = Inventory({}, {}, {})
    fields = specs.fields(store.rules, store.name)
    app_files = {r["stem"] + ".txt" for r in fields if r["scope"] == "app"}
    localized_files = {r["stem"] + ".txt" for r in fields if r["scope"] == "locale"}
    if store.name == "apple":
        app_files.update(name for name in listing.DELIVER_APP_FILES if name.endswith(".txt"))
        localized_files = listing.localized_files(store.rules)
    for name in sorted(app_files):
        path = meta / name
        if path.is_file():
            result.text["metadata/" + name] = safe(meta, path)
    for loc in sorted(meta.iterdir()) if meta.is_dir() else []:
        if downloaded and store.name == "play" and loc.is_dir():
            if is_locale(loc.name) or (loc / "changelogs").is_dir():
                result.listing_locales.add(loc.name)
        if not loc.is_dir() or not (is_locale(loc.name) or (store.name == "apple" and loc.name == "default")):
            continue
        safe(meta, loc)
        for name in sorted(localized_files):
            path = loc / name
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
            if downloaded or ((len(parts) == 2 and (is_locale(parts[0]) or parts[0] == "default"))
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
    old = baseline(store, operations(store))
    local, _ = working_inventory(store)
    # Remember the common ancestor across incomplete downloads and unresolved conflicts.
    ancestors = old["ancestors"]
    conflicts = False
    staged = set()
    if plan._repo_root(store.root):
        raw = run_child(["git", "diff", "--cached", "--name-only", "--relative", "-z"],
                                      cwd=store.root, stdout=subprocess.PIPE, check=True).stdout
        staged = {store.root / os.fsdecode(p) for p in raw.split(b"\0") if p}
    for source in remote.text.values():
        if secret_scan.file_secret(source):
            raise ValueError("Credential-like content in downloaded listing; keeping it outside the repository")
    for key, source in remote.text.items():
        dest = workspace_file(store, key)
        raw = source.read_bytes()
        fresh = sha(comparable(store.name, raw))
        working = dest.read_bytes() if dest.is_file() else None
        current = sha(comparable(store.name, working)) if working is not None else None
        raw_hash = sha(working) if working is not None else None
        raw_base = old["workingBytes"].get(key)
        base = ancestors.get(key)
        if current != fresh and fresh != base:
            staged_change = False
            if dest in staged:
                index = run_child(["git", "show", ":./" + dest.relative_to(store.root).as_posix()],
                                       cwd=store.root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                indexed = None if index.returncode else sha(index.stdout)
                staged_change = indexed != raw_base
            if raw_hash != raw_base or staged_change or (base is None and working is not None):
                print("conflict", key, "— local file retained")
                atomic(store.state("remote/" + store.name + "/" + key), raw)
                conflicts = True
                continue
            atomic(dest, raw, 0o644)
            print("updated", dest)
            raw_hash = sha(raw)
        # A store-only observation must never bless an outstanding working edit.
        if key not in ancestors or fresh != base:
            old["workingBytes"][key] = raw_hash
            ancestors[key] = fresh
    for key, path in {**local.text, **local.graphics}.items():
        if key not in old["workingBytes"]:
            old["workingBytes"][key] = file_hash(path)
    for key, path in remote.shots.items():
        dest = store.state("remote/" + store.name + "/" + key)
        atomic(dest, path.read_bytes())
    old.update(identity=store.identity, pulledAt=now(), files=remote.hashes(),
               galleries=gallery_manifest(store, local.shots),
               remoteGalleries=remote_galleries(store, remote))
    record(store.state("remote.lock.json"), store.name, old)
    return conflicts


def target_locales(store, target):
    return [loc[store.name] for loc in plan._target_locales(
        [plan._locale(item) for item in store.data["locales"]], target)]


def working_inventory(store, require_outputs=False):
    source = inventory(store, store.trees["metadata"], store.trees["screenshots"])
    coverage = {}
    if store.data:
        active = [t for t in plan.targets(store.data, store.name) if t.get("status") != "held"]
        coverage = apple_assets.planned_coverage(
            store.root, store.data, store.rules, store.manifest["outputs"], publish_store=store.name,
            text_locales={path.parent.name for path in source.text.values()} if store.name == "apple" else ())
        locales = coverage[store.name].keys()
        if require_outputs and not any(entry.get("screenshots") for entry in coverage[store.name].values()):
            raise ValueError("No active %s target locales to publish" % store.name)
        active_ids = {t["id"] for t in active}
        approved = {store.root / row["outputPath"]: row for row in store.manifest["outputs"]
                    if row["targetId"] in active_ids and row["upload"] == "fastlane" and row["kind"] == "screenshot"}
        if require_outputs:
            missing = approved.keys() - source.shots.values()
            if missing:
                raise ValueError("Missing planned screenshot: %s" % min(missing))
        shots = {}
        for key, path in source.shots.items():
            if path not in approved:
                continue
            # Deliver needs its display hint for 12.9" and 13" images of the same size.
            if approved[path]["slotId"] == "ipad-12-9" and store.name == "apple":
                key = Path(key).with_name("APP_IPAD_PRO_129-" + path.name).as_posix()
            shots[key] = path
        source.shots = shots
        source.text = {k: p for k, p in source.text.items()
                       if len(k.split("/")) == 2 or k.split("/")[1] in locales | {"default"}}
        source.graphics = {k: p for k, p in source.graphics.items() if k.split("/")[1] in locales}
    elif store.name == "apple":
        coverage = {"apple": apple_assets.load_legacy(store.root, store.rules)}
        for key, path in list(source.shots.items()):
            deferred = coverage["apple"].get(path.parent.name, {}).get("deferredScreenshots")
            if deferred:
                slot = specs.apple_slot_for_file(store.rules, *imginfo.image_info(path)[:2], key)
                if slot and slot["id"] in apple_assets.deferred_slots(store.rules, deferred):
                    del source.shots[key]
    return source, coverage


def checked_copy(path, dest):
    # Inspect exactly the bytes that will be written, including inputs used only by validation.
    data = path.read_bytes()
    if (secret_scan.sensitive_name(path) or secret_scan.credential_file(path)
            or secret_scan.secret_content(path, data)):
        raise ValueError("Credential-like content in listing input; upload view rejected")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def prepared(store, view, platforms):
    source, coverage = working_inventory(store, require_outputs=True)
    metadata = view / ("fastlane/metadata" if store.name == "apple" else "fastlane/metadata/android")
    screenshots = view / "fastlane/screenshots" if store.name == "apple" else metadata
    snapshot = view.parent / (view.name + "-coverage.json")
    write_json(snapshot, coverage or {"apple": {}})
    if not store.data and coverage.get("apple"):
        if secret_scan.file_secret(store.state("asset-plan.json")):
            raise ValueError("Credential-like content in asset plan; upload view rejected")
        write_json(view / apple_assets.LEGACY, coverage)
    for loc in coverage.get("apple", {}):
        base = store.trees["storeAssets"] / loc
        for header in base.glob("*"):
            if header.is_file() and header.suffix.lower() in IMAGE:
                dest = view / "store-assets/apple" / loc / header.name
                checked_copy(safe(store.root, header), dest)
    if store.data:
        # Console images participate in validation but stay outside the upload inventory.
        assets = store.trees["storeAssets"]
        active = [t for t in plan.targets(store.data, store.name) if t.get("status") != "held"]
        ids = {t["id"] for t in active}
        held_paths = {store.root / row["outputPath"] for row in store.manifest["outputs"]
                      if row["kind"] == "screenshot" and row["targetId"] not in ids}
        folders = {assets / loc / "screenshots" / t["slot"] for t in active
                   if t.get("upload", specs.slot(store.rules, store.name, t["slot"])["upload"]) == "console"
                   for loc in target_locales(store, t)}
        for folder in sorted(folders):
            for path in map(Path, listing.images(safe(store.root, folder))):
                if path not in held_paths:
                    dest = view / "store-assets" / store.name / path.relative_to(assets)
                    checked_copy(safe(store.root, path), dest)
    for key, path in source.files().items():
        tree, rel = key.split("/", 1)
        dest = (metadata if tree == "metadata" else screenshots) / rel
        checked_copy(path, dest)
    override = store.root / specs.OVERRIDE
    if override.exists():
        dest = view / specs.OVERRIDE
        checked_copy(safe(store.root, override), dest)
    env = dict(os.environ, LK_REVIEW_DISPLAY_ROOT=str(store.root))
    write_view_plan(view, plan.listing_trees(view), {"platforms": platforms})
    run_child(["bash", str(SCRIPTS / "validate/validate-listing.sh"), str(view),
               "--coverage-view", str(snapshot)], env=env, check=True)
    return inventory(store, metadata, screenshots)


# S3, fastlane 2.242.0, Deliver::AppScreenshot. Some legacy sizes are directional.
DELIVER_SIZES = {
    "APP_IPHONE_67": {(1260, 2736), (2736, 1260), (1290, 2796), (2796, 1290), (1320, 2868), (2868, 1320)},
    "APP_IPHONE_65": {(1242, 2688), (2688, 1242), (1284, 2778), (2778, 1284)},
    "APP_IPHONE_61": {(1179, 2556), (2556, 1179), (1206, 2622), (2622, 1206)},
    "APP_IPHONE_58": {(1170, 2532), (2532, 1170), (1125, 2436), (2436, 1125), (1080, 2340), (2340, 1080)},
    "APP_IPHONE_55": {(1242, 2208), (2208, 1242)},
    "APP_IPHONE_47": {(750, 1334), (1334, 750)},
    "APP_IPHONE_40": {(640, 1096), (640, 1136), (1136, 600), (1136, 640)},
    "APP_IPHONE_35": {(640, 920), (640, 960), (960, 600), (960, 640)},
    "APP_IPHONE_DUO": {(1398, 2034), (2034, 1398), (2007, 2853), (2853, 2007)},
    "APP_IPAD_97": {(1024, 748), (1024, 768), (2048, 1496), (2048, 1536), (768, 1004), (768, 1024), (1536, 2008), (1536, 2048)},
    "APP_IPAD_105": {(1668, 2224), (2224, 1668)},
    "APP_IPAD_PRO_3GEN_11": {(1488, 2266), (2266, 1488), (1668, 2420), (2420, 1668), (1668, 2388), (2388, 1668), (1640, 2360), (2360, 1640)},
    "APP_IPAD_PRO_129": {(2048, 2732), (2732, 2048)},
    "APP_IPAD_PRO_3GEN_129": {(2048, 2732), (2732, 2048), (2064, 2752), (2752, 2064)},
    "APP_DESKTOP": {(1280, 800), (1440, 900), (2560, 1600), (2880, 1800)},
    "APP_WATCH_SERIES_3": {(312, 390)},
    "APP_WATCH_SERIES_4": {(368, 448)},
    "APP_WATCH_SERIES_7": {(396, 484)},
    "APP_WATCH_SERIES_10": {(416, 496)},
    "APP_WATCH_ULTRA": {(410, 502), (422, 514)},
    "APP_APPLE_TV": {(1920, 1080), (3840, 2160)},
    "APP_APPLE_VISION_PRO": {(3840, 2160)},
}


def deliver_display(path, key):
    size = imginfo.image_info(path)[:2]
    display = next((name for name, sizes in DELIVER_SIZES.items() if size in sizes), "unknown")
    hints = key.lower()
    if display == "APP_IPAD_PRO_129" and not (
        "app_ipad_pro_129" in hints or ("12.9" in hints and "2nd generation" in hints)
    ):
        display = "APP_IPAD_PRO_3GEN_129"
    if display == "APP_APPLE_TV" and size == (3840, 2160) and "vision" in hints:
        display = "APP_APPLE_VISION_PRO"
    if key.startswith("screenshots/iMessage/"):
        supported = display.startswith(("APP_IPHONE_", "APP_IPAD_")) and display not in (
            "APP_IPHONE_DUO", "APP_IPHONE_35")
        display = "IMESSAGE_" + display if supported else "unknown"
    return display


def photo_groups(store, images, downloaded=False):
    groups = defaultdict(list)
    for key, path in images.items():
        parts = key.split("/")
        if store.name == "apple":
            loc = parts[-2]
            display = deliver_display(path, key)
            if not (len(parts) == 3 and (is_locale(loc) or loc == "default") or
                    len(parts) == 4 and parts[1] in ("appleTV", "iMessage") and is_locale(loc)):
                loc, display = "*", "unknown"
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


def gallery_manifest(store, images, hashes=None):
    return {"/".join(group): [[k, hashes[k] if hashes is not None else file_hash(images[k])] for k in members]
            for group, members in photo_groups(store, images).items()}


def remote_galleries(store, remote):
    return {"/".join(group): [file_hash(remote.shots[k]) for k in members]
            for group, members in photo_groups(store, remote.shots, downloaded=True).items()}


def operations(store):
    entries = read_state(store.state("publish.receipt.json"))["stores"]
    if store.name not in entries:
        return []
    entry = entries[store.name]
    if entry["identity"] != store.identity:
        raise ValueError("Previous receipt for another app or track; review publish.receipt.json")
    return entry["operations"]


def save_operations(store, history):
    record(store.state("publish.receipt.json"), store.name,
           dict(identity=store.identity, operations=history))


def apply_publication(state, operation):
    # Apple replaces whole locales. Remove their former names and slots.
    # Play replaces just the image folders included in the upload.
    sent_shots = [Path(k) for k in operation["files"] if Path(k).suffix.lower() in IMAGE]
    apple_locales = {p.parent.name for p in sent_shots if p.parts[0] == "screenshots"}
    play_folders = {p.parent for p in sent_shots if p.parts[0] == "metadata"}
    for key in list(state["files"]):
        path = Path(key)
        if (path.parts[0] == "screenshots" and path.parent.name in apple_locales
                or path.parent in play_folders):
            del state["files"][key]
    for name in ("galleries", "remoteGalleries"):
        for group in list(state[name]):
            if group.split("/")[0] in apple_locales:
                del state[name][group]
    notes = {k: digest for k, digest in operation["files"].items() if "/changelogs/" in k}
    if notes:
        state.setdefault("publishedNotes", {})[operation["versionCode"]] = notes
    state["files"].update(operation["files"])
    state["ancestors"].update(operation["ancestors"])
    state["galleries"].update(operation["galleries"])
    state["remoteGalleries"].update({g: [digest for _, digest in members]
                                    for g, members in operation["galleries"].items()})
    state["workingBytes"].update({k: operation["files"][k] for k in operation["ancestors"]})
    state["appliedOperations"].append(operation["operation"])
    state["publishedAt"] = operation["completedAt"]


def baseline(store, history):
    lock = store.state("remote.lock.json")
    state = read_state(lock)["stores"].get(store.name)
    if state is None:
        state = dict(identity=store.identity, files={}, ancestors={}, workingBytes={},
                     galleries={}, remoteGalleries={}, appliedOperations=[])
    if state["identity"] != store.identity:
        raise ValueError("Previous baseline for another app or track; review remote.lock.json")
    # A completed receipt is durable before the baseline write. Replay it once.
    for op in history:
        if (op["identity"] == store.identity and op["status"] == "done"
                and op["operation"] not in state["appliedOperations"]):
            apply_publication(state, op)
            record(lock, store.name, state)
    return state


def summary(store, local, remote, state, pending=()):
    send = {}
    pending_files = {key for op in pending for key in op["files"]}
    pending_locales = {file_locale(key) for key in pending_files}
    print(store.name, "default values are not sent by publish")
    text = {k: p for k, p in local.text.items() if not k.startswith("metadata/default/")}
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
        if key in pending_files:
            print("held", key, "(pending upload)")
            continue
        other = remote.text.get(key)
        if other is None or raw != comparable(store.name, other.read_bytes()):
            print(store.name, key, "changed" if other else "added (cannot compare: absent from download)")
            send[key] = path

    if notes.keys() & pending_files:
        print(store.name, "release notes held pending readback")
    elif notes and {k: file_hash(p) for k, p in notes.items()} == state.get("publishedNotes", {}).get(store.code):
        print(store.name, "previously completed release-note replacement skipped for", store.code)
    elif any(k not in remote.text or p.read_bytes() != remote.text[k].read_bytes() for k, p in notes.items()):
        # Supply replaces release_notes. Include every observed translation for this version.
        # Missing notes in a supplied locale become empty strings in fastlane.
        suffix = "/changelogs/%s.txt" % store.code
        missing = remote.missing_note_locales(store.code)
        if not remote.listing_locales or missing:
            raise ValueError("Download did not establish the complete release-note locale set for "
                             "version code %s on track %s (missing: %s); refusing replacement" %
                             (store.code, store.track, ", ".join(sorted(missing)) or "all locales"))
        for key in remote.text:
            if key.endswith(suffix):
                if key not in notes:
                    raise ValueError("Replacing release notes would clear another translation (%s); "
                                     "supply its local notes or use the hand-upload folder" % key)
        for key, path in notes.items():
            status = "added" if key not in remote.text else (
                "changed" if path.read_bytes() != remote.text[key].read_bytes() else "retained")
            print(store.name, key, status)
        send.update(notes)

    for key in sorted(remote.text.keys() - text.keys() - notes.keys()):
        print(store.name, key, "remote only (no local field to upload)")

    shots = {k: p for k, p in local.shots.items()
             if not k.startswith(("screenshots/default/", "metadata/default/"))}
    ours = photo_groups(store, shots)
    theirs = photo_groups(store, remote.shots, downloaded=True)
    changed = set()
    explicit = set()
    for selector in store.screenshots:
        matches = {g for g in ours if g[:len(selector)] == selector}
        if not matches:
            raise ValueError("No local screenshot group matches --screenshots %s:%s" %
                             (store.name, ":".join(selector)))
        explicit.update(matches)
    local_manifest = gallery_manifest(store, shots)
    live_manifest = remote_galleries(store, remote)
    groups = set(ours) | set(theirs) | {tuple(k.split("/")) for k in state["remoteGalleries"]}
    for group in sorted(groups):
        key = "/".join(group)
        source = local_manifest.get(key, [])
        observed = live_manifest.get(key, [])
        prior = state["galleries"].get(key)
        if source and prior is None:
            print(store.name, *group, "never published from this repo; select with --screenshots",
                  ":".join((store.name, *group)))
        if group[0] in pending_locales or "*" in pending_locales:
            action = "held pending readback"
        elif (source and [digest for _, digest in source] != observed
                and (group in explicit or prior is not None and source != prior)):
            changed.add(group)
            action = "replacement requested"
        elif observed != state["remoteGalleries"].get(key, []):
            action = "the store's gallery differs from the last baseline; pull to review"
        else:
            action = "unchanged" if source else "remote only"
        print(store.name, *group, "%d local images, %d remote images — %s" % (len(source), len(observed), action))
    if store.name == "apple" and changed:
        locales = {loc for loc, _ in changed}
        print("WARNING: overwrite_screenshots deletes every screenshot set for each locale being uploaded,"
              " including any uploaded by hand.")
        protected = {loc for t in plan.targets(store.data, "apple") for loc in target_locales(store, t)
                     if t.get("upload", specs.slot(store.rules, "apple", t["slot"])["upload"]) == "console"
                     } if store.data else set()
        missing = {loc for loc, slot in theirs if (loc, slot) not in ours}
        if ("*" in missing or locales & (protected | missing | {"default"})
                or any(slot.endswith("unknown") for loc, slot in ours if loc in locales)):
            raise ValueError("Apple replacement could erase an unrestorable slot; use the hand-upload folder")
        for group, members in ours.items():
            if group[0] in locales:
                if "/".join(group) not in state["galleries"] and group not in explicit:
                    raise ValueError("Restoring this Apple locale requires --screenshots %s:%s" %
                                     (store.name, ":".join(group)))
                for key in members:
                    directory = Path(key).parent
                    if any(Path(k).parent == directory and Path(k).stem.lower().endswith("_framed")
                           for k in local.shots) and not any(h in key.lower() for h in ("watch", "framed")):
                        raise ValueError("Deliver would skip a screenshot in the _framed folder; "
                                         "use the hand-upload folder")
                count = str(len(theirs[group])) if group in theirs else "an unknown number of"
                print("restore", *group, "%d local images replace %s remote images" % (len(members), count))
                send.update((key, local.shots[key]) for key in members)
    else:
        if store.data and store.name == "play":
            for target in plan.targets(store.data, "play"):
                slot = specs.slot(store.rules, "play", target["slot"])
                if target.get("upload", slot["upload"]) == "console" and any(
                    (loc, slot.get("folder")) in changed for loc in target_locales(store, target)
                ):
                    raise ValueError("Play replacement overlaps a console slot; use the hand-upload folder")
        for group in sorted(changed):
            send.update((key, local.shots[key]) for key in ours[group])
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


@dataclass
class Transfer:
    store: Store
    local: Inventory
    folder: Path
    args: list
    approval: dict
    enabled: bool

    def confirm(self, yes):
        if not self.enabled:
            print("publishing to %s is not enabled in this version of listing-kit until it has passed "
                  "a live test; use the hand-upload folder" % self.store.name)
            if not yes:
                return
        elif not yes:
            try:
                approved = sys.stdin.isatty() and input("Type yes to approve %s: " % self.store.name) == "yes"
            except (EOFError, KeyboardInterrupt):
                approved = False
            if not approved:
                raise ValueError("Publish not approved; non-interactive publish requires --yes")
        record(self.store.state("publish.approved.json"), self.store.name, self.approval)

    def execute(self):
        if not self.enabled:
            return
        store = self.store
        latest = download(store, self.folder.parent / "recheck")
        history = operations(store)
        state = baseline(store, history)
        if len(history) != self.approval["receiptIndex"]:
            raise ValueError("Publish receipt changed; rerun publish for a fresh summary")
        if latest.snapshot_hash() != self.approval["baseline"]:
            print("Remote baseline changed. Review the new summary and confirm again.")
            summary(store, self.local, latest, state)
            raise ValueError("Rerun publish for a new confirmation")
        staged = {}
        for path in self.folder.rglob("*"):
            safe(self.folder, path)
            if path.is_file():
                staged[path.relative_to(self.folder).as_posix()] = file_hash(path)
        if staged != self.approval["files"]:
            raise ValueError("The approved files changed. Rerun publish for a new confirmation")
        current_plan = plan.load(store.root) if (store.root / plan.LISTING).exists() else {}
        if current_plan != store.data:
            raise ValueError("Listing plan changed. Rerun publish for a new confirmation")
        files = {k: self.folder / k for k in staged}
        ancestors = {k: sha(comparable(store.name, path.read_bytes())) for k, path in files.items()
                     if path.suffix == ".txt"}
        operation = dict(self.approval, store=store.name, operation=uuid.uuid4().hex,
                         status="pending", ancestors=ancestors)
        history.append(operation)
        save_operations(store, history)
        try:
            store.run(self.args, self.folder, upload=True)
        except (ChildTimeout, KeyboardInterrupt, ValueError, OSError, MissingFastlane) as exc:
            if "--overwrite_screenshots" in self.args:
                print("The Apple gallery may now be empty. Run listing-kit handoff . and restore each affected "
                      "locale’s complete screenshot set in App Store Connect from the hand-upload folder.",
                      file=sys.stderr)
            if isinstance(exc, ChildTimeout):
                raise ValueError("%s; upload outcome unknown. Run publish for readback." % exc)
            if isinstance(exc, MissingFastlane):
                operation.update(status="failed")
                save_operations(store, history)
            raise
        complete(store, history, operation, state)
        print("Completed", store.name)


def complete(store, history, operation, state):
    operation.update(status="done", completedAt=now())
    save_operations(store, history)
    apply_publication(state, operation)
    record(store.state("remote.lock.json"), store.name, state)


def preview(store, local, scratch, remote, history, pending):
    state = baseline(store, history)
    send = summary(store, local, remote, state, pending)
    if not send:
        print(store.name, "no comparable changes to publish")
        return None
    folder = scratch / "upload"
    (folder / "metadata").mkdir(parents=True)
    for key, path in send.items():
        dest = folder / key
        checked_copy(path, dest)
    args = upload_args(store, send, folder)
    display_args = [store.key.name if value == str(store.key) else value for value in args]
    print("Would run", shlex.join(store.tool()[0] + display_args), flush=True)
    enabled = PUBLISH_ENABLED[store.name] or (
        os.environ.get("LK_PUBLISH_UNVERIFIED") == "%s:%s" % (store.name, store.app))
    staged = {key: folder / key for key in send}
    files = {key: file_hash(path) for key, path in staged.items()}
    shots = {key: path for key, path in staged.items() if key in local.shots}
    galleries = gallery_manifest(store, shots, files)
    for group, members in sorted(galleries.items()):
        before = dict(state["galleries"].get(group, []))
        print(store.name, group, "upload order:")
        for key, digest in members:
            status = "new" if key not in before else "changed" if digest != before[key] else "unchanged"
            print(" ", status, digest[:12], key)
    manifest_hash = fingerprint(dict(files=files, galleries=galleries))
    approval = dict(identity=store.identity, receiptIndex=len(history), files=files, galleries=galleries,
                    manifestHash=manifest_hash, baseline=remote.snapshot_hash(),
                    versionCode=store.code, approvedAt=now())
    return Transfer(store, local, folder, args, approval, enabled)


def file_locale(key):
    parts = key.split("/")
    if parts[0] == "screenshots":
        return parts[-2]
    return parts[1] if len(parts) > 2 else "*"


def matches_manifest(store, op, remote, live):
    for key, digest in op["ancestors"].items():
        path = remote.text.get(key)
        if path is None or sha(comparable(store.name, path.read_bytes())) != digest:
            return False
    notes = {k for k in op["files"] if "/changelogs/" in k}
    if notes and remote.missing_note_locales(op["versionCode"]):
        return False
    if notes and notes != {k for k in remote.text if k.endswith("/changelogs/%s.txt" % op["versionCode"])}:
        return False
    expected = {g: [digest for _, digest in members] for g, members in op["galleries"].items()}
    if store.name == "apple" and expected:
        locales = {g.split("/")[0] for g in expected}
        if any(g not in expected and g.split("/")[0] in locales | {"*"} for g in live):
            return False
    return all(live.get(group) == digests for group, digests in expected.items())


def reconcile(store, history, scratch, resolve):
    state = baseline(store, history)
    try:
        remote = download(store, scratch)
    except (ChildTimeout, MissingFastlane, ValueError, OSError) as exc:
        print(store.name, "readback unavailable:", exc)
        remote = None
    live = remote_galleries(store, remote) if remote else {}
    pending = []
    for op in history:
        if op["status"] != "pending" or op["identity"] != store.identity:
            continue
        if remote and matches_manifest(store, op, remote, live):
            complete(store, history, op, state)
            print(store.name, op["operation"], "store matches the approved manifest; marked done")
            continue
        pending.append(op)
        print(store.name, "upload outcome unknown", op["operation"], "approved manifest", op["manifestHash"])
        for key, digest in sorted(op["ancestors"].items()):
            path = remote.text.get(key) if remote else None
            observed = sha(comparable(store.name, path.read_bytes()))[:12] if path else "unavailable"
            print(" ", key, "approved", digest[:12], "store", observed)
        for group, members in sorted(op["galleries"].items()):
            print(group, "approved order:")
            for key, digest in members:
                print(" ", digest[:12], key)
            observed = " ".join(d[:12] for d in live.get(group, [])) or "(empty)"
            print("  store order:", observed if remote else "unavailable")
    if pending:
        if resolve:
            prompt = "After checking the store, type yes to close these pending operations and permit a fresh publish: "
            if not sys.stdin.isatty() or input(prompt) != "yes":
                raise ValueError("Resolution requires interactive confirmation")
            for op in pending:
                op.update(status="resolved", resolvedAt=now())
            save_operations(store, history)
        else:
            print("Inspect the store and run publish --resolve", store.name, flush=True)
    elif resolve:
        print(store.name, "no pending operations")
    if remote is None and not resolve:
        raise ValueError("Cannot publish without a fresh download")
    return remote, pending


def configure(store, args, config):
    field, _, _ = CREDENTIAL[store.name]
    flag = args.apple_api_key_path if store.name == "apple" else args.play_json_key_path
    if flag:
        local = store.state("local.json")
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
            sub.add_argument("--screenshots", action="append", default=[], metavar="STORE:LOCALE[:GROUP]")
            sub.add_argument("--resolve", choices=CREDENTIAL, help="review a pending upload and confirm recovery")
            sub.add_argument("--yes", action="store_true")
            sub.add_argument("--version-code", type=version_code)
    args = parser.parse_args(argv)
    if args.command == "publish" and args.resolve:
        if args.store and args.store != args.resolve:
            parser.error("--resolve must match --store")
        args.store = args.resolve
    root = Path(args.app_root or args.root).resolve(strict=True)
    repo = plan._repo_root(root)
    rules = specs.load(root)
    try:
        stores = selected(args, root, rules)
    except argparse.ArgumentError as exc:
        parser.error(str(exc))
    if args.command == "publish":
        selected_stores = {s.name: s for s in stores}
        for value in args.screenshots:
            parts = value.split(":")
            if (len(parts) not in (2, 3) or parts[0] not in selected_stores
                    or not is_locale(parts[1]) or not all(parts)):
                parser.error("expected --screenshots <selected store>:<locale>[:<group>]")
            selected_stores[parts[0]].screenshots += (tuple(parts[1:]),)
    override = os.environ.get("LK_PUBLISH_UNVERIFIED")
    if args.command == "publish" and override is not None:
        if len(stores) != 1 or override != "%s:%s" % (stores[0].name, stores[0].app):
            parser.error("LK_PUBLISH_UNVERIFIED requires exactly one selected store and its exact store:app-id")
        print("WARNING: uploads are enabled for this run by LK_PUBLISH_UNVERIFIED=" + override, flush=True)
    for store in stores:
        print("%s app %s | %s %s" % (
            store.name, store.app, "version" if store.name == "apple" else "track", store.selector))
        print("fastlaneDir={fastlaneDir} metadata={metadata} screenshots={screenshots}".format(**store.trees))
        print("Requires an editable version in App Store Connect." if store.name == "apple" else
              "Requires a first build already uploaded in Play Console.", flush=True)
    state = safe(root, root / ".listing-kit")
    state.mkdir(exist_ok=True)
    # Lock the directory itself, avoiding stale lock files after interruption.
    fd = os.open(str(state), os.O_RDONLY)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another listing-kit command holds the lock on %s" % state)
        local_config = stores[0].state("local.json")
        if (local_config.exists() and repo and shutil.which("git") and
                run_child(["git", "ls-files", "-z", "--", ":(literal)local.json"], cwd=state,
                          stdout=subprocess.PIPE, check=True).stdout):
            raise ValueError(".listing-kit/local.json is tracked; remove it from the git index first")
        config = read_json(local_config, {})
        # Deliver can download review credentials before we apply the import allowlist.
        boundary = repo or root
        scratch_parent = Path(tempfile.gettempdir()).resolve()
        if scratch_parent == boundary or boundary in scratch_parent.parents:
            scratch_parent = Path("/tmp").resolve()
            if scratch_parent == boundary or boundary in scratch_parent.parents:
                raise ValueError("Set TMPDIR to a directory outside the repository for fastlane downloads")
        with tempfile.TemporaryDirectory(prefix="listing-kit-fastlane-", dir=scratch_parent) as tmp:
            scratch = Path(tmp)
            views = {}
            for store in stores:
                report_version(store, scratch)
                if args.command == "setup":
                    field, env, description = CREDENTIAL[store.name]
                    print("Keep the %s outside the repository; set %s or .listing-kit/local.json fastlane.%s."
                          % (description, env, field))
                store.key = read_key(root, repo or root, store.name, args, config)
                print(store.name, store.app, "credential", store.key.name, flush=True)
            secret_scan.check_store_credentials(repo or root)
            if args.command == "publish":
                histories = {store.name: operations(store) for store in stores}
                readbacks = {}
                for store in stores:
                    history = histories[store.name]
                    if any(op["status"] == "pending" for op in history):
                        readbacks[store.name] = reconcile(store, history, scratch / (store.name + "-recovery"),
                                                          args.resolve)
                    elif args.resolve:
                        print(store.name, "no pending operations")
                if args.resolve:
                    return 0
                if stores[0].data:
                    inputs = plan.input_files(stores[0].data, rules, root)
                    if run_child([sys.executable, "-EsB", str(SCRIPTS / "lib/secret_scan.py"),
                                  *[str(p) for p in inputs if p.is_file()]]).returncode:
                        raise ValueError("Plan inputs failed the secret scan")
                    run_child([sys.executable, "-EsB", str(SCRIPTS / "lib/plan.py"), "check", str(root),
                                    "--for", "publish"], check=True)
                platforms = {name: value for name, (value, _) in detect.resolve(root, rules).items()
                             if value is not None}
                for store in stores:
                    views[store.name] = prepared(store, scratch / (store.name + "-view"), platforms)
                transfers = []
                for store in stores:
                    dest = scratch / store.name
                    dest.mkdir()
                    if store.name in readbacks:
                        remote, pending = readbacks[store.name]
                    else:
                        remote = download(store, dest / "before")
                        pending = []
                    transfer = preview(store, views[store.name], dest, remote, histories[store.name], pending)
                    if transfer:
                        transfers.append(transfer)
                for transfer in transfers:
                    transfer.confirm(args.yes)
                for transfer in transfers:
                    transfer.execute()
                return int(any(pending for _, pending in readbacks.values()))
            conflicts = False
            for store in stores:
                dest = scratch / store.name
                if args.command == "setup":
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
    except KeyboardInterrupt:
        print("listing-kit: interrupted", file=sys.stderr)
        sys.exit(130)
    except EOFError:
        print("listing-kit: confirmation required", file=sys.stderr)
        sys.exit(1)
    except MissingFastlane as exc:
        print(exc, file=sys.stderr)
        sys.exit(3)
    except (ChildTimeout, ValueError, RuntimeError, OSError, subprocess.CalledProcessError, specs.SpecsError) as exc:
        print("listing-kit:", exc, file=sys.stderr)
        sys.exit(1)
