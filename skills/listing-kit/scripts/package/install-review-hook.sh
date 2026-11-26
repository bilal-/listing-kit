#!/usr/bin/env bash
# Register an app's staged listing inputs with its repository's pre-commit hook.
# --status is read-only and exits zero only for an active, current registration.
set -euo pipefail
status=0
if [ "${1:-}" = --status ]; then status=1; shift; fi
case "${1:-}" in
  -h|--help)
    operation=install
    if [ "$status" = 1 ]; then operation=status; fi
    echo "Usage: listing-kit hook $operation [app-root]"
    exit 0 ;;
esac
[ "$#" -le 1 ] || { echo "Usage: install-review-hook.sh [--status] [app-root]" >&2; exit 2; }
ROOT="${1:-.}"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The runner must still work after the recorded installation disappears.
runner_body() {
  cat "$SELF_DIR/../lib/install_lookup.py"
  sed '/^from install_lookup import /d' "$SELF_DIR/../lib/review_hook.py"
}
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
raw = subprocess.check_output(["git", "rev-parse", "--git-path", "hooks"], cwd=worktree)
configured = Path(os.path.abspath(worktree / os.fsdecode(raw[:-1])))
hooks = configured.resolve()
user_hooks = hooks.parent if hooks.name == "_" and (hooks / "h").is_file() else hooks
for path in (hooks, user_hooks):
    dest = path.resolve()
    if not any(root == dest or root in dest.parents for root in (worktree, common)):
        sys.exit(f"inactive (hooks path outside repository: {dest})")
    parent = dest if dest.is_dir() else dest.parent
    while not parent.exists():
        parent = parent.parent
    if git_path(parent, "--git-common-dir") != common:
        sys.exit(f"inactive (hooks path belongs to another repository: {dest})")
# A sentinel protects a trailing newline from shell command substitution.
manual = worktree in configured.parents and common not in configured.parents
print(("manual|" if manual else "auto|") + str(hooks) + ".", end="")
PYHOOK
)" || exit 2
case "$hook_dir" in manual\|*) manual=1 ;; *) manual=0 ;; esac
hook_dir="${hook_dir#*|}"
hook_dir="${hook_dir%.}"
hook="$hook_dir/pre-commit"
common="$(cd "$ROOT" && dir="$(git rev-parse --git-common-dir && printf .)" && cd "${dir%??}" && pwd -P && printf .)"
common="${common%??}"
runner="$common/listing-kit-review"
if [ "${hook_dir##*/}" = "_" ] && [ -f "$hook_dir/h" ]; then
  hook="${hook_dir%/*}/pre-commit"
fi
case "$hook_dir/" in "$common/"*) ;; *) manual=1 ;; esac
if [ -L "$hook" ] || [ -L "$hook_dir/pre-commit" ]; then manual=1; fi
kit="$(cd "$SELF_DIR/../.." && pwd -P)"
CALL_MARK='# listing-kit review refresh'
call='r="$(git rev-parse --git-common-dir && printf .)" || exit 1; r="${r%??}/listing-kit-review"; [ ! -x "$r" ] || "$r" || exit $?'
call="$call $CALL_MARK"
app_rel="$(git -C "$ROOT" rev-parse --show-prefix && printf .)"
app_rel="${app_rel%$'\n.'}"
app_rel="${app_rel%/}"
export LC_ALL=C
printf -v q "%q" "$app_rel"
has_call() { grep -Fxq -e "$call" -e "$call"$'\r' "$hook"; }

shell_hook() {
  python3 -I -B - "$hook" <<'PYSHELL'
import re
import sys
with open(sys.argv[1], "rb") as source:
    data = source.read()
if b"\0" in data:
    sys.exit(1)
first = data.partition(b"\n")[0]
if first.startswith(b"#!") and not re.search(rb"[/\s](?:ba|da|k|z)?sh(?:\s|$)", first):
    sys.exit(1)
PYSHELL
}

needs_line() {
  echo "inactive: needs one line in $hook"
  printf '%s\n' "$call"
  return 1
}
check_status() {
  if [ "$manual" = 1 ] && { [ ! -f "$hook" ] || ! has_call; }; then
    needs_line; return 1
  fi
  if [ ! -f "$hook" ]; then echo "inactive (pre-commit missing)"; return 1; fi
  if [ ! -x "$hook_dir/pre-commit" ]; then echo "inactive (pre-commit is not executable)"; return 1; fi
  if ! shell_hook; then echo "inactive (foreign pre-commit; configure the hook manager to run $runner)"; return 1; fi
  if grep -q '# BEGIN listing-kit review hook' "$hook" ||
      { grep -qF "$CALL_MARK" "$hook" && ! has_call; }; then
    echo outdated; return 1
  fi
  if ! has_call; then echo "inactive (pre-commit is not wired)"; return 1; fi
  if ! awk -v call="$call" '{sub(/\r$/, "")} NR == 1 && /^#!/ {next} {found = ($0 == call); exit} END {exit !found}' "$hook"; then
    echo "inactive (runner call must precede existing hook commands)"; return 1
  fi
  if [ ! -x "$runner" ]; then echo "inactive (runner missing or disabled)"; return 1; fi
  if ! sed -n '/^# listing-kit isolated review runner$/,/^PYREVIEW$/{ /^# listing-kit isolated review runner$/d; /^PYREVIEW$/d; p; }' "$runner" | cmp -s - <(runner_body); then
    echo outdated; return 1
  fi
  if ! grep -Fxq "apps+=($q)" "$runner"; then echo "inactive (app is not registered)"; return 1; fi
  if ! python3 -I -B - "$kit" "$runner" <<'PYSTATUS'
import json, sys
from pathlib import Path
kit, runner = map(Path, sys.argv[1:])
sys.path.insert(0, str(kit / "scripts/lib"))
from install_lookup import newest, version
with runner.open() as stream:
    for line in stream:
        if line.startswith("# installation "):
            path, channel, release = json.loads(line[len("# installation "):])
            latest = newest(Path(path), Path(channel) if channel else None)
            sys.exit(0 if version(latest) and (latest / "VERSION").read_text().strip() == release
                     and version(kit) <= version(latest) else 1)
sys.exit(1)
PYSTATUS
  then echo outdated; return 1; fi
  echo active
}
if [ "$status" = 1 ]; then check_status; exit $?; fi

# Keep the shell-quoted registrations written by previous installers.
legacy_q="$q"
if [[ "$app_rel" == *[![:print:]]* ]]; then
  # Earlier installers used the caller's locale for printable Unicode.
  utf8="$(locale -a | awk 'tolower($0) ~ /utf-?8$/ && !seen++ {print}')"
  if [ -n "$utf8" ]; then
    legacy_q="$(export LC_ALL="$utf8"; printf '%q' "$app_rel")"
  fi
fi
apps=()
add_app() {
  local a entry="$1"
  [ "$entry" != "$legacy_q" ] || entry="$q"
  for a in ${apps[@]+"${apps[@]}"}; do [ "$a" != "$entry" ] || return 0; done
  apps+=("$entry")
}
previous="$runner"
if [ ! -f "$previous" ] && [ "$manual" = 0 ]; then previous="$hook_dir/listing-kit-review"; fi
if [ -f "$previous" ]; then
  while IFS= read -r a; do add_app "$a"; done < <(sed -n 's/^apps+=(\(.*\))$/\1/p' "$previous")
fi
if [ -f "$hook" ] && grep -q '# BEGIN listing-kit review hook' "$hook"; then
  legacy="$(sed -n 's/^listing_kit_app_rel=//p' "$hook" | head -1)"
  [ -z "$legacy" ] || add_app "$legacy"
fi
add_app "$q"

# Replace directory entries atomically so hard links retain their original data.
if [ "$manual" = 0 ]; then mkdir -p "$hook_dir"; fi
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

printf -v kit_q "%q" "$kit"
channel=
case "$kit" in */listing-kit/*/skills/listing-kit)
  channel="$(cd "$kit/../../.." && pwd -P)" ;;
esac
printf -v channel_q "%q" "$channel"
tmp="$(mktemp "$common/.listing-kit.XXXXXX")"
{
  printf '#!/usr/bin/env bash\n# Generated by listing-kit install-review-hook.sh\nrecorded_kit=%s\nchannel=%s\napps=()\n' "$kit_q" "$channel_q"
  printf 'installer_python=%q\n' "$(python3 -I -B -c 'import sys; print(sys.executable)')"
  python3 -I -B -c 'import json,sys; print("# installation " + json.dumps(sys.argv[1:]))' "$kit" "$channel" "$(cat "$kit/VERSION")"
  for a in "${apps[@]}"; do printf 'apps+=(%s)\n' "$a"; done
  cat <<'RUN'
# Git passes no arguments to pre-commit. Find the invoking Git, including
# through hook-manager shells. Only inspect argv further for possible amends.
darwin_argv() {
  # A GUI may omit Python from PATH. The system interpreter, when present,
  # can still disambiguate Git options from commit messages and filenames.
  local python
  python="$installer_python"
  [ -x "$python" ] || python="$(command -v python3 || true)"
  [ -x "$python" ] || python=/usr/bin/python3
  [ -x "$python" ] || return 1
  "$python" -I -B - "$1" <<'PYARGV'
import ctypes
import os
import struct
import sys

# Darwin KERN_PROCARGS2: argc, executable, padding, argv, environment.
mib = (ctypes.c_int * 3)(1, 49, int(sys.argv[1]))
size = ctypes.c_size_t(os.sysconf("SC_ARG_MAX"))
buf = ctypes.create_string_buffer(size.value)
if ctypes.CDLL(None).sysctl(mib, 3, buf, ctypes.byref(size), None, 0):
    sys.exit(1)
argc, = struct.unpack_from("i", buf)
argv = buf.raw[4:size.value].partition(b"\0")[2].lstrip(b"\0").split(b"\0", argc)[:argc]
sys.stdout.buffer.write(b"\0".join(argv) + b"\0")
PYARGV
}

amending() {
  local pid=$PPID parent comm command_line arg short amend=1 exact=1
  local args=() key value
  while [ "$pid" -gt 1 ]; do
    if [ -r "/proc/$pid/status" ]; then
      parent=; comm=
      while read -r key value; do
        case "$key" in Name:) comm=$value ;; PPid:) parent=$value; break ;; esac
      done < "/proc/$pid/status"
      [ -n "$parent" ] || return 1
    else
      read -r parent comm < <(/bin/ps -p "$pid" -o ppid= -o comm= 2>/dev/null) || return 1
    fi
    case "${comm##*/}" in git|git-commit) break ;; esac
    pid=$parent
  done
  [ "$pid" -gt 1 ] || return 1
  if [ -r "/proc/$pid/cmdline" ]; then
    while IFS= read -r -d '' arg; do args+=("$arg"); done < "/proc/$pid/cmdline"
  else
    command_line="$(/bin/ps -ww -p "$pid" -o args=)"
    case " $command_line " in *' --amend '*) ;; *) return 1 ;; esac
    if [[ "$OSTYPE" == darwin* ]]; then
      while IFS= read -r -d '' arg; do args+=("$arg"); done < <(darwin_argv "$pid")
    fi
  fi
  if [ "${#args[@]}" = 0 ]; then
    # ps flattens whitespace. Only trust options before free-form operands.
    echo "listing-kit: Warning: Git argument boundaries unavailable; amend detection is limited." >&2
    read -r -a args <<< "$command_line"
    exact=0
  fi
  set -- "${args[@]}"
  if [ "${1##*/}" != git-commit ]; then
    shift
    while [ "$#" -gt 0 ] && [ "$1" != commit ]; do
      case "$1" in -c|-C|--git-dir|--work-tree|--namespace) shift ;; esac
      [ "$#" -gt 0 ] && shift
    done
    [ "$#" -gt 0 ] || return 1
  fi
  shift
  while [ "$#" -gt 0 ]; do
    arg=$1; shift
    case "$arg" in
      --) break ;;
      --amend) amend=0 ;;
      --no-amend) amend=1 ;;
      --message|--file|--author|--date|--trailer|--template|--reuse-message|--reedit-message|--cleanup|--fixup|--squash|--pathspec-from-file)
        [ "$exact" = 1 ] || break
        shift ;;
      --*) ;;
      -*) short="${arg#-}"
          while [ -n "$short" ]; do
            case "$short" in
              [mFcCt]*)
                [ "$exact" = 1 ] || return "$amend"
                [ "${#short}" != 1 ] || shift
                break ;;
              [Su]*) break ;;
            esac
            short="${short#?}"
          done ;;
      *) [ "$exact" = 1 ] || break ;;
    esac
  done
  return "$amend"
}

# GUI clients can have a minimal PATH. Match Git's raw NUL-delimited paths.
export LC_ALL=C
base=()
if amending; then
  parent="$(git rev-parse --verify -q HEAD^1)" || parent="$(git hash-object -t tree --stdin </dev/null)"
  base+=("$parent")
fi
if [ "$(git config --bool core.ignorecase)" = true ]; then shopt -s nocasematch; fi
git diff --cached --name-only --no-renames -z "${base[@]}" -- | (
  found=1
  while IFS= read -r -d '' path; do
    for app in "${apps[@]}"; do
      prefix="${app:+$app/}"
      case "$path" in "$prefix"*) rel="${path:${#prefix}}" ;; *) continue ;; esac
      case "$rel" in
        fastlane/*|store-assets/*|.listing-kit/*|app.json) found=0 ;;
        *.pbxproj|Info.plist|*/Info.plist|AndroidManifest.xml|*/AndroidManifest.xml|build.gradle|*/build.gradle|build.gradle.kts|*/build.gradle.kts)
          case "/$rel/" in
RUN
  python3 -I -B - "$SELF_DIR/../lib" <<'PYSKIP'
import sys
sys.path.insert(0, sys.argv[1])
from review_hook import SKIP, SKIP_SUFFIXES
patterns = ["*/" + name + "/*" for name in sorted(SKIP)] + ["*" + ext + "/*" for ext in SKIP_SUFFIXES]
print("            " + "|".join(patterns) + ") ;;")
PYSKIP
  cat <<'RUN'
            *) found=0 ;;
          esac ;;
        app.config.*) case "$rel" in */*) ;; *) found=0 ;; esac ;;
      esac
    done
  done
  exit "$found"
)
scope=("${PIPESTATUS[@]}")
if [ "${scope[0]}" != 0 ]; then echo "listing-kit: could not inspect staged paths" >&2; exit 1; fi
if [ "${scope[1]}" != 0 ]; then exit 0; fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "listing-kit: Commit blocked. Staged listing inputs require python3 for the credential scan." >&2
  exit 1
fi
python3 -I -B - "$recorded_kit" "$channel" "${base[0]:-}" "${apps[@]}" <<'PYREVIEW' || {
# listing-kit isolated review runner
RUN
  runner_body
  cat <<'RUN'
PYREVIEW
  echo "listing-kit: Commit blocked. Check python3 and fix the cause, or knowingly commit with --no-verify." >&2
  exit 1
}
RUN
} > "$tmp"
install_file "$runner" runner
if [ "$manual" = 1 ]; then
  check_status || exit 2
  exit 0
fi

if [ ! -f "$hook" ]; then
  tmp="$(mktemp "${hook%/*}/.listing-kit.XXXXXX")"
  printf '#!/bin/sh\n%s\n' "$call" > "$tmp"
  install_file "$hook" hook
elif shell_hook; then
  tmp="$(mktemp "${hook%/*}/.listing-kit.XXXXXX")"
  awk -v call="$call" '
    {sub(/\r$/, "")}
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
