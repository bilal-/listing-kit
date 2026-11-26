#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

new_tempdir app
it "documented commands, options, links and example agree with the installed kit"
if python3 - "$ROOT" "$app" <<'PY'
from functools import lru_cache
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit

root, app = map(Path, sys.argv[1:])
skill = root / "skills/listing-kit"
cli = skill / "bin/listing-kit"
errors = []

def run(*args, cwd=app):
    return subprocess.run([str(cli), *args], cwd=cwd, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

# Parse the dispatcher's usage, including e.g. "plan check|manifest|outputs".
commands = {}
for line in run("help").stdout.splitlines():
    match = re.match(r"^  ([a-z-]+)(?: ([a-z][a-z|]*))?(?=\s|$)", line)
    if match:
        name, children = match.groups()
        commands[name] = children.split("|") if children else []

flag = re.compile(r"(?<![\w-])--[a-zA-Z][\w-]*")

@lru_cache(None)
def options(command):
    for switch in ("--help", "-h"):
        result = run(*command, switch)
        if result.returncode or not re.search(r"^usage:", result.stdout, re.I | re.M):
            errors.append(f"{' '.join((*command, switch))}: expected usage and exit 0, "
                          f"got {result.returncode}: {result.stdout.strip()}")
        if switch == "--help":
            available = set(flag.findall(result.stdout))
    return available

# Exercise the whole launcher, including commands with no flags in the docs.
for name, children in commands.items():
    options((name,))
    for child in children:
        options((name, child))

def headings(path):
    ids = set()
    for title in re.findall(r"^#{1,6}\s+(.+?)\s*#*$", path.read_text(), re.M):
        slug = re.sub(r"[^\w -]", "", title.lower()).replace(" ", "-")
        unique = slug
        counter = 0
        while unique in ids:
            counter += 1
            unique = f"{slug}-{counter}"
        ids.add(unique)
    return ids

def check_link(file, dest, where):
    url = urlsplit(dest.strip("<>"))
    if url.scheme or url.netloc:
        return
    target = file.parent / unquote(url.path) if url.path else file
    if not target.exists():
        errors.append(f"{where}: missing link {dest}")
    elif url.fragment and target.suffix == ".md" and unquote(url.fragment) not in headings(target):
        errors.append(f"{where}: missing heading {dest}")

mention = re.compile(r"(?<![\w-])listing-kit[ \t]+([a-z][\w-]*)")
layout = skill / "references/metadata/fastlane-layout.md"
maestro = skill / "references/driving/maestro.md"
for file in [root / "README.md", skill / "SKILL.md", layout, maestro, *sorted((root / "docs").glob("*.md"))]:
    content = file.read_text()
    # Join shell continuations so flags on following lines are checked too.
    lines = re.sub(r"\\\n\s*", " ", content).splitlines()
    fenced = False
    for num, line in enumerate(lines, 1):
        where = f"{file.relative_to(root)}:{num}"
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        matches = list(mention.finditer(line))
        for i, match in enumerate(matches):
            name = match[1]
            if name not in commands:
                errors.append(f"{where}: unknown command {name}")
                continue
            end = matches[i + 1].start() if i + 1 < len(matches) else len(line)
            tail = line[match.end():end]
            command = (name,)
            if commands[name]:
                child = re.match(r"[ \t]+([a-z][\w-]*)", tail)
                if not child or child[1] not in commands[name]:
                    errors.append(f"{where}: expected {name} {'|'.join(commands[name])}")
                    continue
                command += (child[1],)
            for switch in flag.findall(tail):
                if switch not in options(command):
                    errors.append(f"{where}: {' '.join(command)} has no {switch}")
        if fenced:
            continue
        prose = re.sub(r"`[^`]*`", "", line)
        for dest in re.findall(r"\]\((<[^>]+>|[^\s)]+)", prose):
            check_link(file, dest, where)
        for dest in re.findall(r'''(?:href|src)=["']([^"']+)["']''', prose):
            check_link(file, dest, where)
        ref = re.match(r"^\s*\[(?!\^)[^\]]+\]:\s*(<[^>]+>|\S+)", prose)
        if ref:
            check_link(file, ref[1], where)

doc = (skill / "references/plan-file.md").read_text()
example, = re.findall(r"^```json\n(.*?)^```$", doc, re.M | re.S)
if json.loads(example) != json.loads((root / "tests/fixtures/plan-example.json").read_text()):
    errors.append("documented plan differs from tests/fixtures/plan-example.json")
listing = app / ".listing-kit/listing.json"
listing.parent.mkdir()
# Parse the documented coverage with the same reader used by validation and handoff.
sys.path.insert(0, str(skill / "scripts/lib"))
import apple_assets
asset_example, = re.findall(r"^```json\n(.*?)^```$", layout.read_text(), re.M | re.S)
(listing.parent / "asset-plan.json").write_text(asset_example)
coverage = apple_assets.load_plan(app)["en-US"]
if not all(coverage.get(key) for key in ("screenshots", "headers", "deferredScreenshots")):
    errors.append("Apple asset plan example must demonstrate counts, headers and deferrals")

flow_doc = maestro.read_text()
if set(re.findall(r"`(LK_[A-Z_]+)`", flow_doc)) - {"LK_CAPTURE_TIMEOUT", "LK_TOOL_TIMEOUT"} != {
        "LK_APP_ID", "LK_LOCALE", "LK_TARGET", "LK_SCREEN"}:
    errors.append("Maestro reference must name the four explicit flow variables")
for term in (".listing-kit/secrets.local", "${MAESTRO_DEMO_PASSWORD}"):
    if term not in flow_doc:
        errors.append(f"Maestro login instructions missing {term}")

workflow = (skill / "SKILL.md").read_text()
if not re.search(r"never pass `--yes` or set `LK_PUBLISH_UNVERIFIED`", workflow, re.I):
    errors.append("Agent workflow must forbid both live publish controls")
hook_example = 'git config --local --add listingKit.reviewedDeviceBlob "$(git rev-parse :app.json) app.json"'
if hook_example not in layout.read_text().splitlines():
    errors.append("Missing staged blob review command in the layout reference")

listing.write_text(example)
result = run("plan", "check")
if result.returncode:
    errors.append(result.stdout)
# Exercise the first-run recipe too. Reuse an existing frame for the HTML
# preview so missing fonts or colors fail here without a simulator or browser.
guide = (root / "docs/GUIDE.md").read_text()
recipe, = re.findall(r"^```json\n(.*?)^```$", guide, re.M | re.S)
source = root / "examples/expo-recipe-box"
copy = app / "recipe-box"
copy.mkdir()
for name in (".gitignore", "app.json"):
    shutil.copyfile(source / name, copy / name)
for name in ("fastlane", ".listing-kit/flows"):
    shutil.copytree(source / name, copy / name)
subprocess.run(["git", "init", "-q", str(copy)], check=True)
for cmd, status, evidence in [
    (("validate",), 1, "no iPhone Dynamic Island (medium display) screenshots"),
    (("review",), 0, "listing-review.html"),
    (("hook", "install"), 0, "Installed"),
    (("hook", "status"), 0, "active"),
]:
    result = run(*cmd, cwd=copy)
    if result.returncode != status or evidence not in result.stdout:
        errors.append(f"Recipe Box {' '.join(cmd)}: {result.stdout}")
for path in ("local.json", "upload/INDEX.html", "logs/flow.log", "compose.flock", "secrets.local"):
    if subprocess.run(["git", "check-ignore", "-q", f".listing-kit/{path}"], cwd=copy).returncode:
        errors.append(f"Recipe Box should ignore .listing-kit/{path}")

(copy / ".listing-kit/listing.json").write_text(recipe)
plan_check = run("plan", "check", "--for", "capture", cwd=copy)
if plan_check.returncode:
    errors.append(plan_check.stdout)
else:
    manifest = json.loads(run("plan", "manifest", cwd=copy).stdout)
    for job in manifest["captures"]:
        path = copy / job["rawPath"]
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / "fastlane/screenshots/en-US/01_recipes.png", path)
    preview = run("compose", "--preview", cwd=copy)
    if preview.returncode or not (copy / ".listing-kit/preview.html").is_file():
        errors.append("guide preview failed: " + preview.stdout)
if errors:
    sys.exit("\n".join(errors))
PY
then pass "commands, flags, links and plan example"; else fail "documentation checks failed"; fi

remove_fixture "$app"
summary
