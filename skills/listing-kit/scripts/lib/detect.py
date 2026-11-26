#!/usr/bin/env python3
"""Resolve store conditions from a valid listing plan, overrides and static project files."""
import json
import os
from pathlib import Path
import plistlib
import re
import sys
from xml.etree import ElementTree
from xml.parsers.expat import ExpatError

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout
import plan
import specs

from project_files import ANDROID, app_manifest, project_files
from xcode_project import application_settings

UNKNOWN = (None, "no static evidence")


# Scan object keys and literal values without importing or executing a JS config.
JS_TOKEN = re.compile(r"""//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|[\w$]+|[^\s]""")


def expo_literals(text):
    tokens = [t for t in JS_TOKEN.findall(text) if not t.startswith(("//", "/*"))]
    for i, key in enumerate(tokens):
        if key.strip("\"'") != "ios" or tokens[i + 1:i + 3] != [":", "{"]:
            continue
        depth = 1
        flags = {}
        for j in range(i + 3, len(tokens)):
            token = tokens[j]
            if token == "{":
                depth += 1
            elif token == "}":
                depth -= 1
                if not depth:
                    break
            elif depth == 1 and token.strip("\"'") in ("supportsTablet", "isTabletOnly"):
                value = tokens[j + 1:j + 4]
                if len(value) == 3 and value[0] == ":" and value[2] in (",", "}") and value[1] in ("true", "false"):
                    flags[token.strip("\"'")] = value[1] == "true"
                else:
                    flags[token.strip("\"'")] = None
        if flags:
            yield flags


def expo_families(ios):
    tablet_only = ios.get("isTabletOnly", False)
    tablet = ios.get("supportsTablet", False)
    return (not tablet_only if type(tablet_only) is bool else None,
            tablet if type(tablet) is bool else None)


def device_families(config, directory):
    value = config.get("TARGETED_DEVICE_FAMILY")
    if value is None and isinstance(config.get("INFOPLIST_FILE"), str):
        name = config["INFOPLIST_FILE"].replace("$(SRCROOT)/", "").replace("${SRCROOT}/", "")
        path = (directory / name).resolve()
        if directory.resolve() in path.parents and path.is_file():
            try:
                value = plistlib.loads(path.read_bytes()).get("UIDeviceFamily")
            except (ValueError, ExpatError, plistlib.InvalidFileException):
                pass
    parts = value if isinstance(value, list) else str(value).split(",")
    if all(str(part).strip().isdigit() for part in parts):
        return {str(part).strip() for part in parts}
    return None


def platforms(config):
    value = config.get("SUPPORTED_PLATFORMS", "")
    names = set(value if isinstance(value, list) else value.split())
    if config.get("SDKROOT"):
        names.add(config["SDKROOT"])
    return names


def xcode(path, project, evidence):
    settings = list(application_settings(path))
    if not settings:
        return
    ios = False
    for config in settings:
        if config is None:
            project["families"].append((evidence, None))
            continue
        family = device_families(config, path.parent.parent)
        supported = platforms(config)
        family_only = not supported.difference({"$(inherited)"}) and family and family.intersection({"1", "2"})
        if supported.intersection({"iphoneos", "iphonesimulator"}) or family_only:
            ios = True
            project["families"].append((evidence, family))
    project["targets"].append((evidence, ios, settings))


def read_project(root):
    project = {k: [] for k in ("families", "expo", "targets", "android")}
    for path in project_files(root):
        evidence = str(path.relative_to(root))
        try:
            if path.suffix == ".pbxproj":
                try:
                    xcode(path, project, evidence)
                except (KeyError, ValueError, TypeError, AttributeError, plistlib.InvalidFileException):
                    project["targets"].append((evidence, False, [None]))
                    project["families"].append((evidence, None))
            elif path.name == "AndroidManifest.xml":
                doc = ElementTree.parse(path)
                if not app_manifest(path, doc):
                    continue
                features = [(f.get(ANDROID + "name", ""), f.get(ANDROID + "required", "true") != "false")
                            for f in doc.findall("uses-feature")]
                launcher = any(c.get(ANDROID + "name") == "android.intent.category.LEANBACK_LAUNCHER"
                               for c in doc.findall("application//intent-filter/category"))
                project["android"].append((evidence, (features, launcher)))
            elif path.suffix == ".json":
                cfg = json.loads(path.read_text(encoding="utf-8"))
                ios = cfg.get("expo", cfg).get("ios")
                if isinstance(ios, dict):
                    project["expo"].append((evidence, expo_families(ios)))
            elif path.suffix in (".ts", ".js", ".mjs", ".cjs"):
                text = path.read_text(encoding="utf-8")
                for ios in expo_literals(text):
                    project["expo"].append((evidence, expo_families(ios)))
        except (OSError, ValueError, AttributeError, ElementTree.ParseError, ExpatError, plistlib.InvalidFileException):
            continue
    return project


def find(entries, test):
    negative = unknown = None
    for path, value in entries:
        result = test(value) if value is not None else None
        if result:
            return True, path
        if result is None:
            unknown = (None, path)
        else:
            negative = (False, path)
    return unknown or negative or UNKNOWN


def family(number, project):
    if project["families"]:
        return find(project["families"], lambda values: number in values)
    return find(project["expo"], lambda flags: flags[int(number) - 1])


def target(platform, setting=None, expected=None):
    def detect(project):
        entries = []
        for path, ios, settings in project["targets"]:
            for config in settings:
                if config is None:
                    entries.append((path, None))
                    continue
                match = platform in platforms(config)
                if setting and setting in config:
                    match = match or expected is None or config[setting] == expected
                if ios or match:
                    entries.append((path, match if ios else None))
        return find(entries, bool)
    return detect


def nonphone(feature):
    return (feature.startswith(("android.hardware.type.", "android.software.xr."))
            or feature in ("android.software.leanback", "android.software.leanback_only"))


def android(test):
    return lambda project: find(project["android"], lambda manifest: test(*manifest))


DETECTORS = {
    "supportsIphone": lambda p: family("1", p),
    "supportsIpad": lambda p: family("2", p),
    "hasWatchApp": target("watchos", "WATCHOS_DEPLOYMENT_TARGET"),
    "hasTvApp": target("appletvos", "TVOS_DEPLOYMENT_TARGET"),
    "hasVisionApp": target("xros"),
    "hasMacApp": target("macosx", "SUPPORTS_MACCATALYST", "YES"),
    "supportsAndroidPhone": android(lambda features, _: not any(nonphone(f) and required for f, required in features)),
    "hasAndroidTv": android(lambda features, launcher: launcher or any(f == "android.software.leanback" for f, _ in features)),
    "hasWearOs": android(lambda features, _: any(f == "android.hardware.type.watch" for f, _ in features)),
    "hasAndroidXr": android(lambda features, _: any(f.startswith("android.software.xr.") for f, _ in features)),
    "isUpdate": lambda _: UNKNOWN,
}


ENV_FLAGS = {"supportsIphone": "LK_SUPPORTS_IPHONE", "supportsIpad": "LK_SUPPORTS_IPAD"}


def resolve(root, rules, ios_sdk=None, errors=None):
    root = Path(root)
    project = read_project(root)
    explicit = {}
    try:
        explicit = plan.load(root).get("platforms", {})
    except FileNotFoundError:
        pass
    except plan.PlanError as exc:
        _, field, message = next(issue for issue in exc.problems if issue[0] == "ERROR")
        error = f"listing.json invalid; platform overrides ignored: {field}: {message}"
        if errors is None:
            print(error, file=sys.stderr)
        else:
            errors.append(error)
    facts = {}
    for name in rules.get("conditions", {}):
        env = ENV_FLAGS.get(name)
        if name in explicit:
            facts[name] = explicit[name], str(plan.LISTING)
        elif env and os.environ.get(env) in ("0", "1"):
            facts[name] = os.environ[env] == "1", env
        elif ios_sdk and name.startswith("iosSdkBelow:"):
            threshold = name.split(":", 1)[1]
            facts[name] = tuple(map(int, ios_sdk.split("."))) < tuple(map(int, threshold.split("."))), "--ios-sdk"
        else:
            facts[name] = DETECTORS.get(name, lambda _: UNKNOWN)(project)
    return facts


def word(value):
    return {True: "yes", False: "no", None: "unknown"}[value]


class Requirements:
    """Evaluate each rule against the same facts and retain the evidence used."""

    def __init__(self, root, rules, as_of=None, ios_sdk=None):
        self.errors = []
        self.reported_unknown = set()
        self.verbose = False
        self.facts = resolve(root, rules, ios_sdk, self.errors)
        self.values = {k: v for k, (v, _) in self.facts.items()}
        self.as_of = as_of
        self.used = set()

    def apply_inferred(self, inferred):
        for name, value in inferred.items():
            if self.values.get(name) is None:
                self.values[name] = value
                self.facts[name] = value, str(plan.LISTING)

    def evaluate(self, rule):
        return specs.requirement(rule, self.values, self.as_of, self.used)

    def evidence(self):
        for name in sorted(self.used):
            value, source = self.facts[name]
            yield ("WARN" if value is None else "NOTE",
                   "{}={} ({})".format(name, word(value), source))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(prog="listing-kit detect", description=__doc__)
    parser.add_argument("app_root", nargs="?", type=Path, default=Path("."))
    root = parser.parse_args().app_root.resolve()
    try:
        trees = plan.listing_trees(root)
    except plan.PlanError as exc:
        print(exc, file=sys.stderr)
        trees = {}
    except ValueError as exc:
        sys.exit(str(exc))
    kind, stores = layout.stack(root)
    print("stack", kind, sep="\t")
    print("stores", " ".join(stores), sep="\t")
    print("appRoot", root, sep="\t")
    for store, tree in trees.items():
        for key, path in tree.items():
            print(store + "." + key, path, sep="\t")
    for name, (value, source) in resolve(root, specs.load(root)).items():
        print(name, word(value), source, sep="\t")
