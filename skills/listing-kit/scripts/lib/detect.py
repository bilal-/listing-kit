#!/usr/bin/env python3
"""Resolve store conditions from a valid listing plan, overrides and static project files."""
import json
import os
from pathlib import Path
import plistlib
import re
import sys
from xml.etree import ElementTree

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan
import specs

SKIP = {".git", ".gradle", "build", "DerivedData", "node_modules", "Pods", ".expo", ".dart_tool", "dist"}
ANDROID = "{http://schemas.android.com/apk/res/android}"
UNKNOWN = (None, "no static evidence")


def project_files(root):
    for parent, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.endswith((".framework", ".xcframework")))
        for name in sorted(names):
            path = Path(parent) / name
            if name in ("AndroidManifest.xml", "Info.plist") or name.endswith(".pbxproj") or (
                    path.parent == root and (name == "app.json" or name.startswith("app.config."))):
                yield path


def read_project(root):
    project = {k: [] for k in ("families", "expo", "targets", "android")}
    for path in project_files(root):
        evidence = str(path.relative_to(root))
        try:
            if path.suffix == ".pbxproj":
                text = path.read_text(encoding="utf-8")
                project["targets"].append((evidence, text))
                for family in re.findall(r'TARGETED_DEVICE_FAMILY\s*=\s*"?([\d,\s]+)"?\s*;', text):
                    project["families"].append((evidence, family.replace(" ", "").strip().split(",")))
            elif path.name == "Info.plist":
                with path.open("rb") as f:
                    family = plistlib.load(f).get("UIDeviceFamily")
                if isinstance(family, list):
                    project["families"].append((evidence, list(map(str, family))))
            elif path.name == "AndroidManifest.xml":
                doc = ElementTree.parse(path)
                features = [(f.get(ANDROID + "name", ""), f.get(ANDROID + "required", "true") != "false")
                            for f in doc.findall("uses-feature")]
                launcher = any(c.get(ANDROID + "name") == "android.intent.category.LEANBACK_LAUNCHER"
                               for c in doc.findall(".//intent-filter/category"))
                project["android"].append((evidence, (features, launcher)))
            elif path.suffix == ".json":
                cfg = json.loads(path.read_text(encoding="utf-8"))
                ios = cfg.get("expo", cfg).get("ios")
                if isinstance(ios, dict):
                    project["expo"].append((evidence, (not ios.get("isTabletOnly", False), ios.get("supportsTablet", False))))
            elif path.suffix in (".ts", ".js", ".mjs", ".cjs"):
                text = path.read_text(encoding="utf-8")
                match = re.search(r"""\bios["\']?\s*:\s*\{[^{}]*?\bsupportsTablet["']?\s*:\s*(true|false)\b""", text)
                if match:
                    project["expo"].append((evidence, (True, match[1] == "true")))
        except (OSError, ValueError, AttributeError, ElementTree.ParseError, plistlib.InvalidFileException):
            continue
    return project


def find(entries, test):
    negative = UNKNOWN
    for path, value in entries:
        if test(value):
            return True, path
        negative = False, path
    return negative


def family(number, project):
    result = find(project["families"], lambda values: number in values)
    if result[0] is None:
        return find(project["expo"], lambda flags: flags[int(number) - 1])
    return result


def target(pattern):
    return lambda project: find(project["targets"], lambda text: re.search(pattern, text, re.I))


def nonphone(feature):
    return (feature.startswith(("android.hardware.type.", "android.software.xr."))
            or feature in ("android.software.leanback", "android.software.leanback_only"))


def android(test):
    return lambda project: find(project["android"], lambda manifest: test(*manifest))


DETECTORS = {
    "supportsIphone": lambda p: family("1", p),
    "supportsIpad": lambda p: family("2", p),
    "hasWatchApp": target(r'\b(?:SDKROOT\s*=\s*"?watchos\b|WATCHOS_DEPLOYMENT_TARGET\s*=)'),
    "hasTvApp": target(r'\b(?:SDKROOT\s*=\s*"?appletvos\b|TVOS_DEPLOYMENT_TARGET\s*=)'),
    "hasVisionApp": target(r'\b(?:SUPPORTED_PLATFORMS\s*=[^;]*\bxros\b|SDKROOT\s*=\s*"?xros\b)'),
    "hasMacApp": target(r'\b(?:SDKROOT\s*=\s*"?macosx\b|SUPPORTS_MACCATALYST\s*=\s*"?YES\b)'),
    "supportsAndroidPhone": android(lambda features, _: not any(nonphone(f) and required for f, required in features)),
    "hasAndroidTv": android(lambda features, launcher: launcher or any(f == "android.software.leanback" for f, _ in features)),
    "hasWearOs": android(lambda features, _: any(f == "android.hardware.type.watch" for f, _ in features)),
    "hasAndroidXr": android(lambda features, _: any(f.startswith("android.software.xr.") for f, _ in features)),
    "isUpdate": lambda _: UNKNOWN,
}


def resolve(root, rules, ios_sdk=None):
    root = Path(root)
    project = read_project(root)
    try:
        explicit = plan.load(root).get("platforms", {})
    except (FileNotFoundError, plan.PlanError):
        explicit = {}
    facts = {}
    for name in rules.get("conditions", {}):
        env = {"supportsIphone": "LK_SUPPORTS_IPHONE", "supportsIpad": "LK_SUPPORTS_IPAD"}.get(name)
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
        self.facts = resolve(root, rules, ios_sdk)
        self.values = {k: v for k, (v, _) in self.facts.items()}
        self.as_of = as_of
        self.used = set()

    def evaluate(self, rule):
        for key in ("condition", "unless"):
            if key in rule:
                self.used.add(rule[key])
        return specs.requirement(rule, self.values, self.as_of)

    def evidence(self):
        for name in sorted(self.used):
            value, source = self.facts[name]
            yield ("WARN" if value is None else "NOTE",
                   "{}={} ({})".format(name, word(value), source))


if __name__ == "__main__":
    root = Path(sys.argv[1])
    for name, (value, source) in resolve(root, specs.load(root)).items():
        print(name, word(value), source, sep="\t")
