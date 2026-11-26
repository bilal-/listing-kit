#!/usr/bin/env python3
"""Manage a single app's listing through fastlane deliver and supply."""
import argparse
from collections import defaultdict
from dataclasses import dataclass
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

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "lib"))
import apple_assets
import imginfo
import listing
import plan
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


def account_name(store):
    # UNVERIFIED in S3: optional public issuer_id / client_email identity fields.
    # Use the external path when the key supplies no recognized public identifier.
    try:
        data = read_json(store.key, {})
    except (ValueError, UnicodeError):
        return str(store.key)
    if store.name == "apple":
        field, pattern = "issuer_id", r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}"
    else:
        field, pattern = "client_email", r"[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+"
    name = data.get(field)
    return name if isinstance(name, str) and re.fullmatch(pattern, name) else str(store.key)


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

    def run(self, args, cwd, version=False, upload=False):
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
        for name, flag, supplied in (("apple", "--app-identifier", args.app_identifier),
                                     ("play", "--package-name", args.package_name)):
            if supplied is not None and ids.get(name) != supplied:
                raise argparse.ArgumentError(None, "%s %r conflicts with plan id %r for %s" %
                                             (flag, supplied, ids.get(name), name))
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
    return inventory(store, metadata, scratch / "screenshots" if store.name == "apple" else metadata, downloaded=True)


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


def inventory(store, meta, shots, downloaded=False):
    """Whitelist store listing fields. Never traverse console, review credentials or other stores."""
    result = Inventory({}, {}, {})
    fields = specs.fields(store.rules, store.name)
    app_files = {r["stem"] + ".txt" for r in fields if r["scope"] == "app"}
    localized_files = {r["stem"] + ".txt" for r in fields if r["scope"] == "locale"}
    if store.name == "apple":
        app_files.update(name for name in listing.DELIVER_APP_FILES if name.endswith(".txt"))
        localized_files.update(listing.LOCALIZED_FILES)
    for name in sorted(app_files):
        path = meta / name
        if path.is_file():
            result.text["metadata/" + name] = safe(meta, path)
    for loc in sorted(meta.iterdir()) if meta.is_dir() else []:
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
    local, _ = working_inventory(store)
    old = baseline(store, local, remote, operations(store), pulling=True)
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
        current = sha(comparable(store.name, dest.read_bytes())) if dest.is_file() else None
        base = ancestors.get(key)
        if current != fresh and fresh != base:
            staged_change = False
            if dest in staged:
                index = run_child(["git", "show", ":./" + dest.relative_to(store.root).as_posix()],
                                       cwd=store.root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                indexed = None if index.returncode else sha(comparable(store.name, index.stdout))
                staged_change = indexed != base
            if current != base or staged_change:
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
    live = gallery_hashes(store, remote.shots, downloaded=True)
    working = gallery_hashes(store, local.shots)
    # Pull keeps images as references. Remember the local sources independently
    # of the store encoding, without accepting an outstanding local edit.
    sources = old["galleries"]
    known_locales = {group.split("/")[0] for group in sources}
    new_locales = {group.split("/")[0] for group in live} - known_locales
    for group in live.keys() | working.keys():
        current = working.get(group)
        if group.split("/")[0] in new_locales:
            sources[group] = current if current is not None else live[group]
        elif current is None and group in live:
            sources[group] = live[group]
        elif current is not None and current in (live.get(group), old["remoteGalleries"].get(group)):
            sources[group] = current
    old.update(identity=store.identity, pulledAt=now(), files=remote.hashes(),
               ancestors=ancestors, remoteGalleries=live)
    record(store.state("remote.lock.json"), store.name, old)
    return conflicts


def target_locales(store, target):
    return [loc[store.name] for loc in plan._target_locales(
        [plan._locale(item) for item in store.data["locales"]], target)]


def working_inventory(store, require_outputs=False):
    source = inventory(store, store.trees["metadata"], store.trees["screenshots"])
    legacy = {}
    if store.data:
        active = [t for t in plan.targets(store.data, store.name) if t.get("status") != "held"]
        locales = {loc for target in active for loc in target_locales(store, target)}
        if require_outputs and not locales:
            raise ValueError("No active %s target locales to publish" % store.name)
        active_ids = {t["id"] for t in active}
        approved = {store.root / row["outputPath"] for row in store.manifest["outputs"]
                    if row["targetId"] in active_ids and row["upload"] == "fastlane" and row["kind"] == "screenshot"}
        if require_outputs:
            missing = approved.difference(source.shots.values())
            if missing:
                raise ValueError("Missing planned screenshot: %s" % min(missing))
        source.shots = {k: p for k, p in source.shots.items() if p in approved}
        source.text = {k: p for k, p in source.text.items() if len(k.split("/")) == 2
                       or k.split("/")[1] in locales | {"default"}}
        source.graphics = {k: p for k, p in source.graphics.items() if k.split("/")[1] in locales}
    if store.name == "apple":
        legacy = apple_assets.load_plan(store.root)
        if store.data:
            legacy = {loc: entry for loc, entry in legacy.items() if loc in locales}
        source.shots = {k: p for k, p in source.shots.items() if not apple_assets.is_deferred(
            p, legacy.get(p.parent.name, {}).get("deferredScreenshots", {}))}
    return source, legacy


def prepared(store, view):
    source, legacy = working_inventory(store, require_outputs=True)
    metadata = view / ("fastlane/metadata" if store.name == "apple" else "fastlane/metadata/android")
    screenshots = view / "fastlane/screenshots" if store.name == "apple" else metadata
    if legacy:
        write_json(view / ".listing-kit/asset-plan.json", {"apple": legacy})
    for loc in legacy:
        base = store.trees["storeAssets"] / loc
        for header in base.glob("*"):
            if header.is_file() and header.suffix.lower() in IMAGE:
                dest = view / "store-assets/apple" / loc / header.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(safe(store.root, header), dest)
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
    run_child(["bash", str(SCRIPTS / "validate/validate-listing.sh"), str(view)], env=env, check=True)
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


def gallery_hashes(store, images, downloaded=False, recorded=None):
    groups = photo_groups(store, images, downloaded)
    return {"/".join(group): [recorded[k] if recorded is not None else file_hash(images[k])
                              for k in members] for group, members in groups.items()}


def operations(store):
    entries = read_json(store.state("publish.receipt.json"), {}).get("stores", {})
    return entries.get(store.name, {}).get("operations", [])


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
    state["remoteGalleries"].update(operation["galleries"])
    state["publishedAt"] = operation["completedAt"]


def baseline(store, local, remote, history, pulling=False):
    lock = store.state("remote.lock.json")
    state = read_json(lock, {}).get("stores", {}).get(store.name, {})
    if state.get("identity", store.identity) != store.identity:
        raise ValueError("Previous baseline was for another app or track; review remote.lock.json")
    files = state.setdefault("files", {})
    state.setdefault("identity", store.identity)
    state.setdefault("ancestors", files.copy())
    if "galleries" not in state:
        # Older pull locks kept downloaded names and raw hashes, with the
        # corresponding image dimensions available in the reference directory.
        references = {}
        for key in files:
            if not (key.startswith("screenshots/") or
                    ("/images/" in key and len(key.split("/")) == 5 and Path(key).suffix.lower() in IMAGE)):
                continue
            path = store.state("remote/" + store.name + "/" + key)
            if path.is_file():
                references[key] = path
            elif key in remote.shots or key in local.shots:
                references[key] = remote.shots.get(key) or local.shots[key]
            elif not pulling:
                raise ValueError("Missing screenshot reference for %s; run pull to refresh the baseline" % key)
        state["galleries"] = gallery_hashes(store, references, downloaded=True, recorded=files)
    state.setdefault("remoteGalleries", state["galleries"].copy())
    # The receipt is durable first. Replay a completed send if the process
    # stopped before advancing the pull ancestor, including old-format receipts.
    cursor = state.get("receiptIndex", 0)
    legacy_pull = state.get("pulledAt", "") if "receiptIndex" not in state else ""
    for op in history[cursor:]:
        if op["identity"] != store.identity or "completedAt" not in op:
            continue
        if "galleries" not in op:
            shots = {k: path for k, path in local.shots.items() if k in op["files"]}
            ancestors = {k: sha(comparable(store.name, path.read_bytes()))
                         for k, path in local.text.items() if k in op["files"] and file_hash(path) == op["files"][k]}
            op = dict(op, galleries=gallery_hashes(store, shots, recorded=op["files"]), ancestors=ancestors)
        if op["completedAt"] <= legacy_pull:
            # A later legacy pull records the store encoding. Its text ancestors
            # are current, but the receipt still identifies our published images.
            state["galleries"].update(op["galleries"])
        else:
            apply_publication(state, op)
    state["receiptIndex"] = len(history)
    if cursor < len(history):
        record(lock, store.name, state)
    return state


def summary(store, local, remote, state):
    send = {}
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
        other = remote.text.get(key)
        if other is None or raw != comparable(store.name, other.read_bytes()):
            print(store.name, key, "changed" if other else "added (cannot compare: absent from download)")
            send[key] = path

    if notes and {k: file_hash(p) for k, p in notes.items()} == state.get("publishedNotes", {}).get(store.code):
        print(store.name, "previously completed release-note replacement skipped for", store.code)
    elif any(k not in remote.text or p.read_bytes() != remote.text[k].read_bytes() for k, p in notes.items()):
        # Supply replaces release_notes. Include every observed translation for this version.
        # Missing notes in a supplied locale become empty strings in fastlane.
        for key in remote.text:
            if key.endswith("/changelogs/%s.txt" % store.code):
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
    known_locales = {key.split("/")[0] for key in state["galleries"]}
    groups = set(ours) | set(theirs) | {tuple(k.split("/")) for k in state["remoteGalleries"]}
    for group in sorted(groups):
        key = "/".join(group)
        mine, live = ours.get(group, []), theirs.get(group, [])
        source = [file_hash(shots[k]) for k in mine]
        observed = [file_hash(remote.shots[k]) for k in live]
        prior_remote = state["remoteGalleries"].get(key, [])
        if source and source != state["galleries"].get(key) and source != prior_remote:
            changed.add(group)
            action = ("replacement requested" if group[0] in known_locales else
                      "first upload: replaces whatever is on the store")
        elif observed != prior_remote:
            action = "the store's gallery differs from the last baseline; pull to review"
        else:
            action = "unchanged" if mine else "remote only"
        print(store.name, *group, "%d local images, %d remote images — %s" %
              (len(mine), len(live), action))
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
        state = baseline(store, self.local, latest, history)
        if len(history) != self.approval["receiptIndex"]:
            raise ValueError("Publish receipt changed; rerun publish for a fresh summary")
        if fingerprint(latest.hashes()) != self.approval["baseline"]:
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
        shots = {k: path for k, path in files.items() if path.suffix.lower() in IMAGE}
        galleries = gallery_hashes(store, shots, recorded=staged)
        ancestors = {k: sha(comparable(store.name, path.read_bytes())) for k, path in files.items()
                     if path.suffix == ".txt"}
        try:
            store.run(self.args, self.folder, upload=True)
        except (ChildTimeout, ValueError, OSError, MissingFastlane) as exc:
            if "--overwrite_screenshots" in self.args:
                print("The Apple gallery may now be empty. Run listing-kit handoff . and restore each affected "
                      "locale’s complete screenshot set in App Store Connect from the hand-upload folder.",
                      file=sys.stderr)
            if isinstance(exc, ChildTimeout):
                history.append(dict(self.approval, outcome="outcome unknown", timedOutAt=now()))
                save_operations(store, history)
                raise ValueError("%s; upload outcome unknown. Run publish for a fresh summary." % exc)
            raise
        operation = dict(self.approval, galleries=galleries, ancestors=ancestors, completedAt=now())
        history.append(operation)
        save_operations(store, history)
        apply_publication(state, operation)
        state["receiptIndex"] = len(history)
        record(store.state("remote.lock.json"), store.name, state)
        print("Completed", store.name)


def preview(store, local, scratch):
    remote = download(store, scratch / "before")
    state = baseline(store, local, remote, operations(store))
    send = summary(store, local, remote, state)
    if not send:
        print(store.name, "no comparable changes to publish")
        return None
    folder = scratch / "upload"
    (folder / "metadata").mkdir(parents=True)
    for key, path in send.items():
        dest = folder / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    args = upload_args(store, send, folder)
    print("Would run", shlex.join(store.tool()[0] + args), flush=True)
    enabled = PUBLISH_ENABLED[store.name] or (
        os.environ.get("LK_PUBLISH_UNVERIFIED") == "%s:%s" % (store.name, store.app))
    approval = dict(identity=store.identity, receiptIndex=state["receiptIndex"], files={k: file_hash(folder / k) for k in send},
                    baseline=fingerprint(remote.hashes()), versionCode=store.code, approvedAt=now())
    return Transfer(store, local, folder, args, approval, enabled)


def review_unknown_uploads(stores, scratch):
    reviewed = False
    for store in stores:
        history = operations(store)
        pending = [op for op in history if op["identity"] == store.identity and
                   op.get("outcome") == "outcome unknown" and not op.get("reviewedAt")]
        if not pending:
            continue
        print(store.name, "previous upload outcome unknown. Downloading a fresh summary for review.", flush=True)
        local, _ = working_inventory(store)
        remote = download(store, scratch / store.name)
        state = baseline(store, local, remote, history)
        summary(store, local, remote, state)
        for op in pending:
            op["reviewedAt"] = now()
        save_operations(store, history)
        print("Inspect the affected listing in the store before running publish again.")
        reviewed = True
    return reviewed


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
            sub.add_argument("--yes", action="store_true")
            sub.add_argument("--version-code", type=version_code)
    args = parser.parse_args(argv)
    root = Path(args.app_root or args.root).resolve(strict=True)
    repo = plan._repo_root(root)
    rules = specs.load(root)
    try:
        stores = selected(args, root, rules)
    except argparse.ArgumentError as exc:
        parser.error(str(exc))
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
        with tempfile.TemporaryDirectory(prefix="listing-kit-fastlane-") as tmp:
            scratch = Path(tmp)
            views = {}
            for store in stores:
                store.run(["--version"], scratch, version=True)
                if args.command == "setup":
                    field, env, description = CREDENTIAL[store.name]
                    print("Keep the %s outside the repository; set %s or .listing-kit/local.json fastlane.%s."
                          % (description, env, field))
                store.key = read_key(root, repo or root, store.name, args, config)
                print(store.name, "account", account_name(store), flush=True)
            secret_scan.check_store_credentials(repo or root)
            if args.command == "publish":
                if review_unknown_uploads(stores, scratch):
                    return 1
                if stores[0].data:
                    inputs = plan.input_files(stores[0].data, rules, root)
                    if run_child([sys.executable, "-EsB", str(SCRIPTS / "lib/secret_scan.py"),
                                  *[str(p) for p in inputs if p.is_file()]]).returncode:
                        raise ValueError("Plan inputs failed the secret scan")
                    run_child([sys.executable, "-EsB", str(SCRIPTS / "lib/plan.py"), "check", str(root),
                                    "--for", "publish"], check=True)
                for store in stores:
                    views[store.name] = prepared(store, scratch / (store.name + "-view"))
                transfers = []
                for store in stores:
                    dest = scratch / store.name
                    dest.mkdir()
                    transfer = preview(store, views[store.name], dest)
                    if transfer:
                        transfers.append(transfer)
                for transfer in transfers:
                    transfer.confirm(args.yes)
                for transfer in transfers:
                    transfer.execute()
                return 0
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
    except MissingFastlane as exc:
        print(exc, file=sys.stderr)
        sys.exit(3)
    except (ChildTimeout, ValueError, RuntimeError, OSError, subprocess.CalledProcessError, specs.SpecsError) as exc:
        print("listing-kit:", exc, file=sys.stderr)
        sys.exit(1)
