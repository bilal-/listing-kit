#!/usr/bin/env bash
# Install a git pre-commit hook that keeps listing-review.html in sync whenever
# staged files under the app root's fastlane/ tree change.
#
# Usage: install-review-hook.sh [<app-root>]    (default: current directory)
# Exit:  0 = installed/updated hook, 2 = usage / not a git worktree / missing python3.
set -euo pipefail

ROOT="${1:-.}"
[ -d "$ROOT" ] || { echo "Not a directory: $ROOT" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "Need python3 to install the review hook." >&2; exit 2; }

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_REVIEW="$SELF_DIR/build-review.sh"
[ -x "$BUILD_REVIEW" ] || { echo "Missing executable: $BUILD_REVIEW" >&2; exit 2; }

git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "Not inside a git worktree: $ROOT" >&2
  exit 2
}

repo_root="$(git -C "$ROOT" rev-parse --show-toplevel)"
git_dir="$(git -C "$ROOT" rev-parse --git-dir)"
case "$git_dir" in
  /*) hook_dir="$git_dir/hooks" ;;
  *) hook_dir="$repo_root/$git_dir/hooks" ;;
esac
hook="$hook_dir/pre-commit"
mkdir -p "$hook_dir"

app_rel="$(python3 - "$repo_root" "$ROOT" <<'PY'
import os, sys
repo, root = map(os.path.realpath, sys.argv[1:3])
rel = os.path.relpath(root, repo)
print("" if rel == "." else rel)
PY
)"

printf -v build_review_q "%q" "$BUILD_REVIEW"
printf -v app_rel_q "%q" "$app_rel"

tmp="$(mktemp)"
if [ -f "$hook" ]; then
  awk '
    /# BEGIN listing-kit review hook/ { skip=1; next }
    /# END listing-kit review hook/ { skip=0; next }
    !skip { print }
  ' "$hook" > "$tmp"
else
  {
    echo '#!/usr/bin/env bash'
    echo 'set -euo pipefail'
  } > "$tmp"
fi

cat >> "$tmp" <<EOF

# BEGIN listing-kit review hook
listing_kit_build_review=$build_review_q
listing_kit_app_rel=$app_rel_q

listing_kit_repo_root="\$(git rev-parse --show-toplevel)"
if [ -n "\$listing_kit_app_rel" ]; then
  listing_kit_app_root="\$listing_kit_repo_root/\$listing_kit_app_rel"
  listing_kit_fastlane_path="\$listing_kit_app_rel/fastlane/"
  listing_kit_report_path="\$listing_kit_app_rel/listing-review.html"
else
  listing_kit_app_root="\$listing_kit_repo_root"
  listing_kit_fastlane_path="fastlane/"
  listing_kit_report_path="listing-review.html"
fi

if git diff --cached --name-only --diff-filter=ACMR -- "\$listing_kit_fastlane_path" | grep -q .; then
  "\$listing_kit_build_review" "\$listing_kit_app_root"
  git add "\$listing_kit_report_path"
fi
# END listing-kit review hook
EOF

mv "$tmp" "$hook"
chmod +x "$hook"

echo "Installed listing-kit review hook: $hook"
