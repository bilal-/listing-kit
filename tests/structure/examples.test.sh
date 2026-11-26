#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

# Detection, validation and secret scanning may consult Git. Run them only on
# the suite's isolated copies, including when this test runs from a worktree.
new_tempdir EXAMPLES
cp -R "$ROOT/examples/." "$EXAMPLES/" || exit 1
APP="$EXAMPLES/expo-recipe-box"

it "example app.json is valid JSON and registers the recipebox scheme"
assert_file "$APP/app.json"
if json_valid "$APP/app.json"; then pass "valid JSON"; else fail "invalid app.json"; fi
assert_eq "recipebox" "$(json_path "$APP/app.json" "['expo']['scheme']")" "expo.scheme"

it "expo-router is the entry point"
assert_eq "expo-router/entry" "$(json_get "$APP/package.json" main)" "package.json main"

it "all four screens exist"
for f in index.tsx "recipe/[id].tsx" shopping.tsx settings.tsx; do
  assert_file "$APP/app/$f"
done

it "each Maestro flow declares an appId, launches clean, and asserts content"
flows=0
for f in "$APP/.listing-kit/flows/"*.yaml; do
  flows=$((flows + 1))
  if grep -q '^appId:' "$f" && grep -q 'clearState: true' "$f" && grep -q 'assertVisible:' "$f"; then pass "${f##*/}"; else fail "malformed flow: $f"; fi
done
it "found the expected four flows"
assert_eq 4 "$flows"

it "committed example flows contain no inlined secrets"
OUT="$(bash "$SCRIPTS/lib/secret-scan.sh" "$APP/.listing-kit/flows" 2>&1)"; RC=$?
assert_eq 0 "$RC" "flows are secret-clean"

it "examples/README.md tells the truth about the example's validation state"
# Detection overrides in the caller's environment must not change what is checked.
OUT="$(env -u LK_SUPPORTS_IPHONE -u LK_SUPPORTS_IPAD bash "$SCRIPTS/validate/validate-listing.sh" "$APP" 2>&1)"; RC=$?
README="$(cat "$ROOT/examples/README.md")"
ROWS="$(grep -c '^| \[`expo-recipe-box`\](expo-recipe-box) |' "$ROOT/examples/README.md")"
assert_eq 1 "$ROWS" "one status row for the example"
STATUS="$(grep '^| \[`expo-recipe-box`\](expo-recipe-box) |' "$ROOT/examples/README.md")"
FAILS="$(printf '%s\n' "$OUT" | sed -n 's/^.* · \([0-9][0-9]*\) failures\{0,1\} .*$/\1/p' | tail -1)"
if [ "$RC" = 0 ]; then
  assert_contains "$STATUS" "passes validation" "example validates, so the row must say so"
  for stale in "needs recapture" "missing medium set" "predate Apple" "Recapture it" "historical listing output"; do
    assert_not_contains "$README" "$stale" "nothing in the README may still call the example stale"
  done
else
  assert_eq 1 "$RC" "the validator ran and reported failures (not a usage error)"
  assert_contains "$STATUS" "needs recapture" "example fails validation, so the row must say so"
  assert_contains "$STATUS" "medium" "the row names what is missing"
  assert_not_contains "$STATUS" "passes validation" "the row must not also claim it passes"
  assert_contains "$OUT" "no iPhone Dynamic Island (medium display) screenshots" "the known failure is the missing medium iPhone set"
  assert_eq 1 "$FAILS" "exactly one failure"
fi

LAUNCHER="$SKILL_DIR/bin/listing-kit"
for stack in expo ios android flutter; do
  app="$EXAMPLES/$stack-recipe-box"
  status_line="Source and plan only. Not yet built or captured on a device."
  case "$stack" in
    expo) kind=expo-managed; stores="apple play" ;;
    ios) kind=native-ios; stores=apple; status_line="Compiles for the iOS simulator. Not yet installed or captured on a device." ;;
    android) kind=native-android; stores=play ;;
    flutter) kind=flutter; stores="apple play" ;;
  esac

  it "$stack detection identifies its stack and stores"
  OUT="$("$LAUNCHER" detect "$app")"
  assert_eq 0 "$?" "detect $stack"
  assert_eq "$kind" "$(printf '%s\n' "$OUT" | awk -F '\t' '$1=="stack"{print $2}')" "$stack stack"
  assert_eq "$stores" "$(printf '%s\n' "$OUT" | awk -F '\t' '$1=="stores"{print $2}')" "$stack stores"
  [ "$stack" = expo ] && continue

  it "$stack plan is valid with all capture inputs present"
  "$LAUNCHER" plan check "$app" && "$LAUNCHER" plan check --for capture "$app" && pass || fail "invalid plan"
  it "$stack README and example index record device status"
  grep -Fxq "$status_line" "$app/README.md" && pass || fail "missing README status"
  row="$(grep -F "| [\`$stack-recipe-box\`]($stack-recipe-box) |" "$ROOT/examples/README.md")"
  assert_contains "$row" "$status_line" "$stack index status"

  it "$stack ships text sources and four flows with identifiers from the app"
  if python3 - "$app" "$stack" "$stores" <<'PY'
import json
import re
import sys
from pathlib import Path

app, stack, stores = Path(sys.argv[1]), sys.argv[2], sys.argv[3].split()
suffix = {"ios": ".swift", "android": ".kt", "flutter": ".dart"}[stack]
source = []
for path in app.rglob("*"):
    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            sys.exit(f"binary file: {path}")
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text):
            sys.exit(f"non-text file: {path}")
        if path.suffix == suffix:
            source.append(text)
literals = set(re.findall(r"""["']([a-z_0-9]+)["']""", "\n".join(source)))
plan = json.loads((app / ".listing-kit/listing.json").read_text())
app_id = "com.example.recipebox." + stack
platforms = {"apple": "ios", "play": "android"}
assert plan["format"] == 2 and plan["app"] == {platforms[s]: app_id for s in stores}
assert {t["store"] for t in plan["targets"] if t["state"] == "active"} == set(stores)
screens = plan["screens"]
assert not any(s.get("flows") for s in screens), "expected one shared flow per screen"
assert [s["id"] for s in screens] == ["recipes", "recipe-detail", "shopping", "settings"]
paths = {app / s["flow"] for s in screens}
assert len(paths) == 4 and paths == set((app / ".listing-kit/flows").glob("*.yaml"))
for path in sorted(paths):
    flow = path.read_text()
    assert f"appId: {app_id}" in flow.splitlines(), path
    assert "recipeBoxState: demo" in flow and "clearState: true" in flow, path
    # Accept the block selectors used by these examples. Reject any unexamined
    # command so a new action cannot silently introduce a stale identifier.
    commands = [line for line in flow.splitlines() if line.startswith("- ")]
    assert commands[0] == "- launchApp:" and "- assertVisible:" in commands, path
    selectors = re.findall(r"^- (tapOn|assertVisible):\n +id: ([a-z0-9_]+)$", flow, re.M)
    assert commands[1:] == [f"- {action}:" for action, _ in selectors], path
    for identifier in re.findall(r"^ +id: (.+)$", flow, re.M):
        assert identifier in literals, f"{path.name}: no {identifier!r} in {suffix} source"
PY
  then pass; else fail "$stack source or flow mismatch"; fi
done
it "Flutter host setup reports missing templates and only updates its own example"
if python3 "$ROOT/tests/structure/flutter-host.py" "$EXAMPLES/flutter-recipe-box"; then pass; else fail; fi

remove_fixture "$EXAMPLES"
summary
