#!/usr/bin/env bash
# Register an app's staged listing inputs with its repository's pre-commit hook.
# --status is read-only and exits zero only for an active, current registration.
set -euo pipefail
status=0
if [ "${1:-}" = --status ]; then status=1; shift; fi
[ "$#" -le 1 ] || { echo "Usage: install-review-hook.sh [--status] [app-root]" >&2; exit 2; }
ROOT="${1:-.}"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
body="$SELF_DIR/../lib/review_hook.py"
[ -x "$SELF_DIR/build-review.sh" ] || { echo "inactive (review builder missing)" >&2; exit 2; }
[ "$(git -C "$ROOT" rev-parse --is-inside-work-tree 2>/dev/null)" = true ] || {
  echo "inactive (Not inside a git worktree: $ROOT)" >&2
  exit 2
}

# Git resolves relative hooksPath at the worktree root. Check the repository
# owning the nearest existing ancestor as well as the resolved destination.
hook_dir="$(cd "$ROOT" && python3 -I -B - <<'PYHOOK'
import os
from pathlib import Path
import subprocess
import sys

def git_path(cwd, *args):
    raw = subprocess.check_output(["git", "rev-parse", *args], cwd=cwd)
    return (cwd / os.fsdecode(raw[:-1])).resolve()

app = Path.cwd()
worktree = git_path(app, "--show-toplevel")
common = git_path(app, "--git-common-dir")
hooks = git_path(worktree, "--git-path", "hooks")
user_hooks = hooks.parent if hooks.name == "_" and (hooks / "h").is_file() else hooks
for path in (hooks, user_hooks / "pre-commit", hooks / "listing-kit-review"):
    dest = path.resolve()
    if not any(root == dest or root in dest.parents for root in (worktree, common)):
        sys.exit(f"inactive (hooks path outside repository: {dest})")
    parent = dest if dest.is_dir() else dest.parent
    while not parent.exists():
        parent = parent.parent
    if git_path(parent, "--git-common-dir") != common:
        sys.exit(f"inactive (hooks path belongs to another repository: {dest})")
# A sentinel protects a trailing newline from shell command substitution.
print(str(hooks) + ".", end="")
PYHOOK
)" || exit 2
hook_dir="${hook_dir%.}"
hook="$hook_dir/pre-commit"
runner="$hook_dir/listing-kit-review"
if [ "${hook_dir##*/}" = "_" ] && [ -f "$hook_dir/h" ]; then
  hook="${hook_dir%/*}/pre-commit"
fi
CALL_MARK='# listing-kit review refresh'
call='r="$(git rev-parse --git-path hooks && printf .)" || exit 1; r="${r%??}/listing-kit-review"; [ ! -x "$r" ] || "$r" || exit $?'
call="$call $CALL_MARK"
app_rel="$(git -C "$ROOT" rev-parse --show-prefix && printf .)"
app_rel="${app_rel%$'\n.'}"
app_rel="${app_rel%/}"
printf -v q "%q" "$app_rel"

shell_hook() {
  local first
  IFS= read -r first < "$hook" || :
  case "$first" in
    '#!'*) [[ "$first" =~ [/[:space:]](ba|da|k|z)?sh([[:space:]]|$) ]] ;;
    *) return 0 ;;
  esac
}

check_status() {
  if [ ! -f "$hook" ]; then echo "inactive (pre-commit missing)"; return 1; fi
  if [ ! -x "$hook_dir/pre-commit" ]; then echo "inactive (pre-commit is not executable)"; return 1; fi
  if ! shell_hook; then echo "inactive (foreign pre-commit; configure the hook manager to run $runner)"; return 1; fi
  if grep -q '# BEGIN listing-kit review hook' "$hook" ||
      { grep -qF "$CALL_MARK" "$hook" && ! grep -Fxq "$call" "$hook"; }; then
    echo outdated; return 1
  fi
  if ! grep -Fxq "$call" "$hook"; then echo "inactive (pre-commit is not wired)"; return 1; fi
  if ! awk -v call="$call" 'NR == 1 && /^#!/ {next} {found = ($0 == call); exit} END {exit !found}' "$hook"; then
    echo "inactive (runner call must precede existing hook commands)"; return 1
  fi
  if [ ! -x "$runner" ]; then echo "inactive (runner missing or disabled)"; return 1; fi
  if ! sed -n '/^# listing-kit isolated review runner$/,/^PYREVIEW$/{ /^# listing-kit isolated review runner$/d; /^PYREVIEW$/d; p; }' "$runner" | cmp -s - "$body"; then
    echo outdated; return 1
  fi
  if ! grep -Fxq "apps+=($q)" "$runner"; then echo "inactive (app is not registered)"; return 1; fi
  echo active
}
if [ "$status" = 1 ]; then check_status; exit $?; fi

# Keep the shell-quoted registrations written by previous installers.
apps=()
add_app() {
  local a
  for a in ${apps[@]+"${apps[@]}"}; do [ "$a" != "$1" ] || return 0; done
  apps+=("$1")
}
if [ -f "$runner" ]; then
  while IFS= read -r a; do add_app "$a"; done < <(sed -n 's/^apps+=(\(.*\))$/\1/p' "$runner")
fi
if [ -f "$hook" ] && grep -q '# BEGIN listing-kit review hook' "$hook"; then
  legacy="$(sed -n 's/^listing_kit_app_rel=//p' "$hook" | head -1)"
  [ -z "$legacy" ] || add_app "$legacy"
fi
add_app "$q"

# Replace directory entries atomically so hard links retain their original data.
mkdir -p "$hook_dir"
tmp=
trap '[ -z "$tmp" ] || rm -f -- "$tmp"' EXIT
install_file() {
  python3 -I -B - "$tmp" "$1" "$2" <<'PYINSTALL'
import os
import stat
import sys
src, dest, kind = sys.argv[1:]
mode = stat.S_IMODE(os.stat(dest).st_mode) if os.path.exists(dest) else 0o755
if kind == "runner" and not mode & 0o111:
    mode |= stat.S_IXUSR
os.chmod(src, mode)
os.replace(src, dest)
PYINSTALL
  tmp=
}

printf -v kit_q "%q" "$(cd "$SELF_DIR/../.." && pwd)"
tmp="$(mktemp "$hook_dir/.listing-kit.XXXXXX")"
{
  printf '#!/usr/bin/env bash\n# Generated by listing-kit install-review-hook.sh\nrecorded_kit=%s\napps=()\n' "$kit_q"
  for a in "${apps[@]}"; do printf 'apps+=(%s)\n' "$a"; done
  cat <<'RUN'
python3 -I -B - "$recorded_kit" "${apps[@]}" <<'PYREVIEW' || {
# listing-kit isolated review runner
RUN
  cat "$body"
  cat <<'RUN'
PYREVIEW
  echo "listing-kit: Commit blocked. Fix the cause, or knowingly commit with --no-verify." >&2
  exit 1
}
RUN
} > "$tmp"
install_file "$runner" runner

if [ ! -f "$hook" ]; then
  tmp="$(mktemp "${hook%/*}/.listing-kit.XXXXXX")"
  printf '#!/bin/sh\n%s\n' "$call" > "$tmp"
  install_file "$hook" hook
elif shell_hook; then
  tmp="$(mktemp "${hook%/*}/.listing-kit.XXXXXX")"
  awk -v call="$call" '
    NR == 1 && /^#!/ {print; print call; next}
    NR == 1 {print call}
    /# BEGIN listing-kit review hook/{skip=1;next}
    /# END listing-kit review hook/{skip=0;next}
    !skip && !/# listing-kit review refresh$/ {print}
    END {if (NR == 0) print call}
  ' "$hook" > "$tmp"
  install_file "$hook" hook
fi
result="$(check_status)" || { echo "$result" >&2; exit 2; }
echo "Installed listing-kit review hook: $hook (apps: ${apps[*]})"
