#!/usr/bin/env bash
# Install a git pre-commit hook that keeps listing-review.html in sync whenever
# staged files under the app root's fastlane/ tree change.
#
# Usage: install-review-hook.sh [<app-root>]    (default: current directory)
# Exit:  0 = installed/updated hook, 2 = usage / not a git worktree.
#
# Honors linked worktrees and core.hooksPath (e.g. husky) via `git rev-parse
# --git-path hooks`. Rerunning replaces the previous listing-kit block in place.
set -euo pipefail

ROOT="${1:-.}"
[ -d "$ROOT" ] || { echo "Not a directory: $ROOT" >&2; exit 2; }

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_REVIEW="$SELF_DIR/build-review.sh"
[ -x "$BUILD_REVIEW" ] || { echo "Missing executable: $BUILD_REVIEW" >&2; exit 2; }

git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "Not inside a git worktree: $ROOT" >&2
  exit 2
}

# --git-path is relative to $ROOT unless git returns an absolute path.
hook_dir="$(git -C "$ROOT" rev-parse --git-path hooks)"
case "$hook_dir" in
  /*) ;;
  *) hook_dir="$(cd "$ROOT" && pwd)/$hook_dir" ;;
esac
hook="$hook_dir/pre-commit"
mkdir -p "$hook_dir"

# App root relative to the worktree root ("" at the root), without trailing slash.
app_rel="$(git -C "$ROOT" rev-parse --show-prefix)"
app_rel="${app_rel%/}"

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
listing_kit_app_root="\$listing_kit_repo_root\${listing_kit_app_rel:+/\$listing_kit_app_rel}"
listing_kit_prefix="\${listing_kit_app_rel:+\$listing_kit_app_rel/}"

if ! git diff --cached --quiet --diff-filter=ACMR -- "\${listing_kit_prefix}fastlane/"; then
  if [ -x "\$listing_kit_build_review" ]; then
    "\$listing_kit_build_review" "\$listing_kit_app_root"
    git add -- "\${listing_kit_prefix}listing-review.html"
  else
    echo "listing-kit: \$listing_kit_build_review not found; listing-review.html not refreshed." >&2
    echo "listing-kit: rerun install-review-hook.sh from the current listing-kit install." >&2
  fi
fi
# END listing-kit review hook
EOF

mv "$tmp" "$hook"
chmod +x "$hook"

echo "Installed listing-kit review hook: $hook"
