#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

PLAN="$SCRIPTS/lib/plan.py"
FIXTURES="$ROOT/tests/fixtures"
REPO="$(mktemp -d)" || exit 1
trap 'rm -rf "$REPO"' EXIT
T="$REPO/apps/demo"
mkdir -p "$REPO/.git"
mkdir -p "$T/.listing-kit"
FILE="$T/.listing-kit/listing.json"
export PYTHONPATH="$SCRIPTS/lib${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1

# The fixtures describe an app, so create its referenced files in this isolated repo.
python3 - "$REPO" "$T" "$FIXTURES" <<'PYINPUT'
import json
from pathlib import Path
import sys

repo, app, fixtures = map(Path, sys.argv[1:])
for file in (fixtures / "plan-example.json", fixtures / "shellbell/listing.new.json"):
    data = json.loads(file.read_text())
    refs = [data["app"]["demoEntry"], data["style"]["logo"], data["graphics"]["play"]["icon"]["from"]]
    for profile in data["style"]["fonts"].values():
        for fonts in profile.values():
            refs.extend(fonts)
    for screen in data["screens"]:
        if "flow" in screen:
            refs.append(screen["flow"])
        refs.extend(screen.get("flows", {}).values())
    for entries in data["graphics"].values():
        refs.extend(g["logo"] for g in entries.values() if "logo" in g)
    for ref in refs + [".listing-kit/flows/one.yaml", ".listing-kit/flows/two.yaml"]:
        if ref.startswith("bundled:"):
            continue
        path = repo / ref[5:] if ref.startswith("repo:") else app / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
PYINPUT

it "missing plan has status 2"
python3 "$PLAN" check "$T" > "$T/result" 2>&1
assert_eq 2 "$?"

it "invalid JSON has a single TSV diagnostic and status 1"
printf '{' > "$FILE"
python3 "$PLAN" check "$T" > "$T/result"
assert_eq 1 "$?"
python3 - "$T/result" <<'PYROW'
import json
from pathlib import Path
import sys
try:
    json.loads("{")
except ValueError as exc:
    expected = "ERROR\t.listing-kit/listing.json\t%s\n" % exc
    sys.exit(Path(sys.argv[1]).read_bytes() != expected.encode())
PYROW
assert_eq 0 "$?"

it "the design example flags the deferred-only screen"
cp "$FIXTURES/plan-example.json" "$FILE"
OUT="$(python3 "$PLAN" check "$T")"
assert_eq 0 "$?"
assert_eq $'WARN\tscreens[1]\tscreen applies to no active target' "$OUT"

it "malformed plans report the offending field without raising"
if python3 - "$FILE" <<'PY'
from copy import deepcopy
import json
import sys

import plan
import specs

from pathlib import Path
root = Path(sys.argv[1]).parents[1]
with open(sys.argv[1], encoding="utf-8") as f:
    example = json.load(f)
rules = specs.load()
missing = object()

def change(key, value, path=None, message=""):
    # Dotted fixture locations use numeric array indices.
    data = deepcopy(example)
    obj = data
    parts = key.split(".")
    for k in parts[:-1]:
        obj = obj[int(k) if isinstance(obj, list) else k]
    k = int(parts[-1]) if isinstance(obj, list) else parts[-1]
    if value is missing:
        del obj[k]
    else:
        obj[k] = value
    if path is None:
        path = parts[0] + "".join("[" + n + "]" if n.isdigit() else "." + n for n in parts[1:])
    problems = plan.check(data, rules, root)
    assert any(level == "ERROR" and p == path and message in m for level, p, m in problems), (
        key, value, path, message, problems)

for value in (True, [], None, "plan"):
    assert plan.check(value, rules, root)[0][:2] == ("ERROR", "$")
for key in ("format", "app", "locales", "targets", "screens",
            "targets.0.id", "targets.0.store", "targets.0.slot", "targets.0.state",
            "targets.0.size", "screens.0.id", "screens.3.panel.headline", "screens.3.panel.rows",
            "screens.3.panel.rows.0.text", "graphics.apple.header-16x9.headline", "graphics.play.icon.from"):
    change(key, missing, message="required")
for key, value in (
    ("schema", 1), ("schema", False), ("format", True), ("format", "1"), ("format", 1.0),
    ("app", []), ("app", {}), ("app", {"id": "x", "ios": "y"}), ("app.ios", 5),
    ("locales", []), ("locales", "en-US"),
     ("targets.0.suffix", "../path"),
    ("targets", {}), ("targets.0", 1), ("targets.0.store", "ios"),
    ("targets.0.slot", "phone"), ("targets.0.size", "1206x2622"),
    ("targets.0.size", [1206]), ("targets.0.size", [True, 2622]), ("targets.0.size", [0, 2622]),
    ("targets.0.size", [1398, 2034]), ("targets.0.state", "prepared"), ("targets.0.upload", "manual"),
    ("targets.1.id", "iphone-medium"), ("targets.0.id", "../iphone"), ("targets.0.capture", []),
    ("targets.0.capture.deviceType", False), ("targets.0.capture.orientation", "square"),
    ("targets.1.reason", missing), ("targets.1.reason", "  "), ("targets.1.reason", 1),
    ("targets.1.reason", "later\ntoday"), ("targets.1.reason", "later\n"),
    ("targets.2.size", [319, 500]), ("targets.2.size", [3841, 3841]), ("targets.2.size", [1000, 2301]),
    ("targets.3.size", [200, 1200]),
    ("screens", {}), ("screens.0", "agents"), ("screens.3.id", "agents"), ("screens.0.id", "a/b"),
    ("screens.0.id", "Upper"), ("screens.0.id", "-start"), ("screens.0.id", "a_b"),
    ("screens.0.flow", ""), ("screens.0.flows", []), ("screens.0.flows.play-tablet", 1),
    ("screens.0.route", []), ("screens.0.state", {}), ("screens.0.draft", "true"),
    ("screens.0.caption", "unlocalized"), ("screens.0.detail.en-US", []),
    ("screens.0.altText.fr", "..."), ("screens.3.panel.rows.0.label", 7),
    ("screens.3.panel.headline.de", "..."), ("screens.1.only", "duo-outer"),
    ("style.mode", 0), ("style.palette.background", "amber"), ("style.bezel.bleed", 1),
    ("style.fonts.default.headline", "font.ttf"),
    ("graphics", []), ("graphics.apple.header-16x9.headline", "square"),
    ("graphics.apple.header-21x9.headline", "..."), ("graphics.play.featureGraphic.detail.de", "..."),
    ("graphics.play.featureGraphic.altText.en-US", 1), ("console.contactEmail", False), ("notes", [])
):
    change(key, value)
change("targets.0.locales", ["de"], "targets[0].locales[0]")
change("style.fonts.default.detail", [True], "style.fonts.default.detail[0]")
change("format", plan.FORMAT + 1, message="update listing-kit")
change("screens.1.only", ["typo"], "screens[1].only[0]", "unknown target")
change("screens.3.except", ["typo"], "screens[3].except[0]", "unknown target")
change("screens.0.flows.typo", "path", message="unknown target")
change("screens.1.except", [], "screens[1]", "both")
change("screens.0.flow", missing, "screens[0]", "exactly one")
change("screens.3.flow", "path", "screens[3]", "exactly one")
change("screens.3.flows", {"play-phone":"path"})
for key, nearest in (("targtes", "targets"), ("targets.0.capture.devcieType", "deviceType"),
                     ("style.fonts.default.headlien", "headline"), ("screens.0.capton", "caption"),
                     ("graphics.apple.header-21x9.altTetx", "altText"), ("console.playCategroy", "playCategory")):
    change(key, "typo", message="did you mean %r" % nearest)
PY
then pass; else fail "one or more checker cases failed"; fi

it "slot orientation, framing inheritance, exact ratio boundaries and upload defaults"
if python3 - "$FILE" <<'PY'
import json
import sys
import plan
import specs

from pathlib import Path
root = Path(sys.argv[1]).parents[1]
with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)
rules = specs.load()
def slot(store, name, size, mode="raw", target_style=None, upload=None):
    t = {"id":"one", "store":store, "slot":name, "size":size, "state":"active"}
    if target_style is not None:
        t["style"] = {"mode":target_style}
    if upload:
        t["upload"] = upload
    data.update(targets=[t], style={"mode":mode}, screens=[])
    return [path for level, path, _ in plan.check(data, rules, root) if level == "ERROR"]

size = ["targets[0].size"]
style = ["targets[0].style.mode"]
assert slot("apple", "iphone-di-medium", [2622,1206]) == []
assert slot("apple", "watch", [410,502], "framed") == style
assert slot("apple", "watch", [410,502], "framed", "raw") == []
assert slot("apple", "watch", [502,410]) == size
assert slot("play", "wear", [384,384], "raw", "framed") == style
assert slot("play", "wear", [384,385]) == size
assert slot("play", "phone", [736,320]) == []
assert slot("play", "phone", [400,920]) == []
assert slot("play", "ten-inch", [1080,1920]) == []
assert slot("play", "xr", [1920,1200]) == []
assert slot("play", "xr", [1200,1920]) == size
# Isolate minSize from the aspect ratio and short-side constraints.
specs.slot(rules, "play", "xr")["minSize"] = [1936, 1200]
assert slot("play", "xr", [1920,1200]) == size
assert slot("play", "chromebook", [1920,1080], upload="fastlane") == ["targets[0].upload"]
PY
then pass; else fail "slot checks failed"; fi

it "panels are counted after filtering, separately for active targets"
if python3 - "$FILE" <<'PY'
import json
import sys
import plan
import specs

from pathlib import Path
root = Path(sys.argv[1]).parents[1]
with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)
rules = specs.load()
capture = {"id":"one", "flow":".listing-kit/flows/one.yaml"}
second = {"id":"two", "flow":".listing-kit/flows/two.yaml"}
panel = {"id":"panel", "panel":data["screens"][-1]["panel"]}
target = data["targets"][0]
target_id = target["id"]
def problems(*screens):
    data["screens"] = list(screens)
    return plan.check(data, rules, root)
few = ("ERROR", "targets[0]", "panels require at least three applicable screens")
half = ("ERROR", "targets[0]", "panels must be fewer than half of the applicable screens")
warn = ("WARN", "targets[0]", "the first applicable screen is a panel")
data["targets"] = [target]
assert problems(panel) == [few, warn], problems(panel)
assert problems(capture, panel) == [few]
assert problems(panel, capture, second) == [warn]
assert problems(capture, panel, second) == []
assert problems(capture, panel, second, dict(panel, id="end")) == [half]
assert problems(capture, panel, dict(second, **{"except":[target_id]})) == [few, ("WARN", "screens[2]", "screen applies to no active target")]
for state in ("retired", "deferred"):
    target.update(state=state, reason="Unavailable")
    expected = [("WARN", "$", "no active targets"), ("WARN", "screens[0]", "screen applies to no active target")]
    if state == "deferred":
        expected.append(("WARN", "targets", "missing required apple slot iphone-di-medium"))
    assert problems(panel) == expected, problems(panel)
PY
then pass; else fail "panel limits failed"; fi

it "a warning on its own is printed and keeps CLI status zero"
python3 - "$FILE" <<'PY'
import json, sys
p = sys.argv[1]
with open(p) as f:
    data = json.load(f)
data["screens"].insert(0, data["screens"].pop())
with open(p, "w") as f:
    json.dump(data, f)
PY
OUT="$(python3 "$PLAN" check "$T")"
assert_eq 0 "$?"
assert_contains "$OUT" $'WARN\ttargets[0]\t'

it "load preserves the plan, helpers filter densely, and localized copy falls back"
cp "$FIXTURES/plan-example.json" "$FILE"
if python3 - "$T" <<'PY'
import json
from pathlib import Path
import sys
import plan
import specs

root = Path(sys.argv[1])
data = plan.load(root)
rules = specs.load(root)
assert data == json.loads((root / plan.LISTING).read_text())
phone, duo, play_phone, tablet = data["targets"]
agents, layout, terminal, closing = data["screens"]
assert plan.targets(data, "apple") == [phone]
assert plan.targets(data, state="deferred") == [duo]
assert plan.targets(data, state=None) == data["targets"]
assert plan.screens_for(data, tablet["id"]) == [agents, terminal]
assert plan.screens_for(data, duo["id"]) == [agents, layout, terminal, closing]
assert plan.output_name(data, phone, closing, rules) == "03_closing_iphone-medium.png"
assert plan.output_name(data, tablet, terminal, rules) == "02_terminal.png"
assert plan.output_name(data, duo, layout, rules) == "02_duo-layout_duo-outer.png"
terminal["except"] = [phone["id"]]
assert plan.screens_for(data, phone["id"]) == [agents, closing]
assert plan.output_name(data, phone, closing, rules) == "02_closing_iphone-medium.png"
assert plan.flow_for(agents, tablet) == agents["flows"]["play-tablet"]
assert plan.flow_for(agents, play_phone) == agents["flow"]
assert plan.flow_for(closing, phone) is None
assert plan.raw_path(duo, layout, "en-US") == ".listing-kit/raw/duo-outer/en-US/duo-layout.png"
value = {"en-US":"Hello", "de":"Hallo"}
assert plan.text(value, "de", ["en-US","de"]) == ("Hallo", False)
assert plan.text(value, "fr", ["de","en-US","fr"]) == ("Hallo", True)
assert plan.text({"en-US":"Hello", "de":""}, "de", ["en-US","de"]) == ("", False)
# An invalid plan must never reach callers of load.
data["format"] += 1
(root / plan.LISTING).write_text(json.dumps(data))
try:
    plan.load(root)
except plan.PlanError as e:
    assert e.problems[0][:2] == ("ERROR", "format")
else:
    raise AssertionError("load accepted an invalid plan")
PY
then pass; else fail "helper contract failed"; fi
it "check returns errors and outputs never emits partial paths for an invalid plan"
OUT="$(python3 "$PLAN" check "$T")"
assert_eq 1 "$?"
assert_contains "$OUT" $'ERROR\tformat\t'
OUT="$(python3 "$PLAN" outputs "$T" 2>"$T/result")"
assert_eq 1 "$?"
assert_eq "" "$OUT"

it "ShellBell retains its screen text, panel rows, and planned counts"
cp "$FIXTURES/shellbell/listing.new.json" "$FILE"
if python3 - "$T" "$FIXTURES/shellbell" <<'PY'
import json
from pathlib import Path
import sys
import plan
import specs

data = plan.load(sys.argv[1])
source = Path(sys.argv[2])
old = json.loads((source / "listing.json").read_text())
assets = json.loads((source / "asset-plan.json").read_text())["apple"]["en-US"]
rules = specs.load()
assert plan.check(data, rules, sys.argv[1]) == []
assert [s["id"] for s in data["screens"]] == [s["id"] for s in old["screens"]]
for s, before in zip(data["screens"], old["screens"]):
    for field in ("caption", "detail", "altText"):
        assert s[field] == {"en-US":before.get(field, "")}
    for field in ("route", "state"):
        assert s[field] == before.get(field, "")
panel = data["screens"][-1]["panel"]
before = old["screens"][-1]["panel"]
assert panel["headline"]["en-US"] == before["headline"]
assert [[r["label"]["en-US"], r["text"]["en-US"]] for r in panel["rows"]] == before["rows"]
for t in plan.targets(data, "apple"):
    slot = specs.slot(rules, "apple", t["slot"])
    label = next(k for k in assets["screenshots"] if k in [slot["label"]] + slot.get("legacyLabels", []))
    assert len(plan.screens_for(data, t["id"])) == assets["screenshots"][label]
graphics = data["graphics"]
assert [key + ".png" for key in graphics["apple"]] == assets["headers"]
feature, headers = graphics["play"]["featureGraphic"], list(graphics["apple"].values())
for g in [feature] + headers:
    assert g["headline"] == {"en-US": "Your terminal,\nfrom anywhere."}
    assert g["palette"] == {"background": ["#F6BC4A", "#E79B19"], "ink": "#151719", "detail": "#493416"}
    assert g["logo"] == "repo:brand/png/horizontal-black@2x.png"
assert feature["detail"] == {"en-US": "Claude Code · Codex · Herdr · tmux · iTerm2"}
assert feature["altText"] == {"en-US": old["featureGraphic"]["altText"]}
for h in headers:
    assert h["detail"] == {"en-US": "Agents / Terminals / End-to-end encrypted / Open source"}
    assert h["altText"] == {"en-US": old["appleHeaders"]["altText"]}
notes = {key: old[key] for key in ("capture", "manualConsoleFields", "releaseNotes", "sources")}
assert data["app"]["demoEntry"] == notes["capture"].pop("demoMode")
assert data["notes"] == notes
assert graphics["play"]["icon"]["from"] == "repo:brand/android/play-store-512.png"
PY
then pass; else fail "ShellBell port differs from its sources"; fi

it "outputs lists all 48 ShellBell screen paths, including the outer display and closing panel"
python3 "$PLAN" outputs "$T" > "$T/outputs"
assert_eq 0 "$?"
if python3 - "$T/outputs" <<'PYROWS'
from pathlib import Path
import sys
rows = [line.split("\t") for line in Path(sys.argv[1]).read_text().splitlines()]
expected = []
for target, suffix, folder in (("iphone", "_iphone", ""), ("iphone-medium", "_iphone-medium", ""),
                               ("iphone-duo", "_iphone-duo", ""), ("ipad", "_ipad13", ""),
                               ("android-phone", "", "phoneScreenshots"),
                               ("android-tablet", "", "tenInchScreenshots")):
    directory = "fastlane/metadata/android/en-US/images/" + folder if folder else "fastlane/screenshots/en-US"
    screens = "agents conversation terminal terminals answer direct reading shellbell".split()
    for n, screen in enumerate(screens, 1):
        expected.append([target, screen, "" if screen == "shellbell" else ".listing-kit/raw/%s/en-US/%s.png" % (target, screen),
                         "%s/%02d_%s%s.png" % (directory, n, screen, suffix)])
expected.extend([["apple", key, "", "store-assets/apple/en-US/" + key + ".png"] for key in ("header-16x9", "header-21x9")])
expected.extend([["play", key, "", "fastlane/metadata/android/en-US/images/" + key + ".png"] for key in ("featureGraphic", "icon")])
assert rows == expected
assert len({r[3].casefold() for r in rows}) == 52
PYROWS
then pass; else fail "ShellBell output manifest differs"; fi

it "routing honors app-specific rules, upload overrides, active state and target locales"
if python3 - "$T" <<'PY'
import json
from pathlib import Path
import sys
import plan
import specs

root = Path(sys.argv[1])
def write(path, data):
    path.write_text(json.dumps(data))
slots = [{"id":"ipad-13", "suffix":"tablet-special", "upload":"console"}]
write(root / ".listing-kit/specs.override.json", {"stores":{"apple":{"screenshots":{"slots":slots}}}})
data = plan.load(root)
rules = specs.load(root)
ipad = plan.targets(data, "apple")[-1]
assert plan.output_name(data, ipad, data["screens"][0], rules) == "01_agents_tablet-special.png"
data["locales"].append({"id":"de", "apple":"de-DE", "play":"de"})
ipad["locales"] = ["de"]
phone, tablet = plan.targets(data, "play")
phone["state"] = "retired"
tablet["upload"] = "console"
write(root / plan.LISTING, data)
PY
then pass; else fail "app override was lost"; fi
OUT="$(python3 "$PLAN" outputs "$T")"
assert_eq 0 "$?"
assert_contains "$OUT" "store-assets/apple/de-DE/screenshots/ipad-13/01_agents_tablet-special.png"
assert_not_contains "$OUT" "store-assets/apple/en-US/screenshots/ipad-13"
assert_contains "$OUT" "store-assets/play/en-US/screenshots/ten-inch/08_shellbell.png"
assert_contains "$OUT" "store-assets/play/de/screenshots/ten-inch/08_shellbell.png"
assert_not_contains "$OUT" "phoneScreenshots"
assert_contains "$OUT" "fastlane/screenshots/de-DE/07_reading_iphone.png"

it "format 2 manifest, rules, and review regressions"
if python3 "$ROOT/tests/unit/plan_format2.py"; then pass; else fail "format 2 regressions"; fi

it "adversarial plan and store-rule regressions"
if python3 "$ROOT/tests/unit/plan_review.py"; then pass; else fail "regression cases failed"; fi

summary
