#!/usr/bin/env bash
# Assert the secrets boundary (skill §9.1): the committed listing tree must
# contain NO credentials. Run during Assemble; FAIL the run on any hit.
#
# Usage:
#   secret-scan.sh [<dir>]    # default: fastlane
#
# Exit codes: 0 = clean, 1 = secret(s) found, 2 = scan error (e.g. unreadable file).
set -euo pipefail

dir="${1:-fastlane}"
if [ ! -d "$dir" ]; then
  echo "Nothing to scan: '$dir' does not exist." >&2
  exit 0
fi

# Known secret patterns (extend as needed). Case-insensitive.
# NOTE: the last (generic keyword=value) pattern can occasionally false-positive on
# marketing copy or a long URL that directly follows a word like "token"/"password".
# It errs toward caution by design — review a flagged line; if it's genuinely public
# copy, reword it slightly. Better a false alarm than a leaked credential.
# Token prefixes are anchored to a non-word character so hyphenated copy
# ("task-management-...") can't match "sk-...".
B='(^|[^A-Za-z0-9_])'
patterns=(
  "${B}(AKIA|ASIA)[0-9A-Z]{16}"                         # AWS access key id
  'aws_secret_access_key'
  "${B}gh[pousr]_[A-Za-z0-9]{36,}"                      # GitHub tokens (PAT, OAuth, app, refresh)
  'github_pat_[A-Za-z0-9_]{22,}'                        # GitHub fine-grained PAT
  "${B}glpat-[A-Za-z0-9_-]{20,}"                        # GitLab PAT
  "${B}xox[abposr]-[A-Za-z0-9-]{10,}"                   # Slack token
  "${B}sk-(proj-|ant-|svcacct-)?[A-Za-z0-9_-]{20,}"     # OpenAI / Anthropic / generic sk- keys
  "${B}(sk|rk)_(live|test)_[A-Za-z0-9]{16,}"            # Stripe secret / restricted key
  'AIza[0-9A-Za-z_-]{35}'                               # Google API key
  '"(private_key_id|private_key)"[[:space:]]*:'         # Google service-account JSON
  "${B}eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"   # JWT
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'                  # private key block
  '(api[_-]?key|secret|password|passwd|token|bearer)["'"'"' :=]+[A-Za-z0-9/_+.=-]{12,}'
)

# Text files only — screenshots and other binaries are never scanned.
includes=(--include='*.txt' --include='*.json' --include='*.yaml' --include='*.yml' --include='*.md')

found=0
for pat in "${patterns[@]}"; do
  rc=0; hits="$(grep -rEil "${includes[@]}" -e "$pat" "$dir")" || rc=$?
  case "$rc" in
    0) while IFS= read -r file; do
         echo "POTENTIAL SECRET in committed listing: $file (pattern: $pat)" >&2
       done <<<"$hits"
       found=1 ;;
    1) ;;   # no match
    *) echo "ERROR: secret scan could not read '$dir' (grep exit $rc); refusing to report clean." >&2
       exit 2 ;;
  esac
done

if [ "$found" -ne 0 ]; then
  echo "FAIL: secrets must never be committed (see skill §9.1). Move them to .listing-kit/secrets.local or env, then re-run." >&2
  exit 1
fi

echo "Secret scan clean: '$dir' contains no detected credentials."
