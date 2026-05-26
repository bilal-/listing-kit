#!/usr/bin/env bash
# Assert the secrets boundary (skill §9.1): the committed listing tree must
# contain NO credentials. Run during Assemble; FAIL the run on any hit.
#
# Usage:
#   secret-scan.sh [<dir>]    # default: fastlane
#
# Exit codes: 0 = clean, 1 = secret(s) found, 2 = usage/error.
set -euo pipefail

dir="${1:-fastlane}"
if [ ! -d "$dir" ]; then
  echo "Nothing to scan: '$dir' does not exist." >&2
  exit 0
fi

# Known secret patterns (extend as needed). Case-insensitive.
patterns=(
  'AKIA[0-9A-Z]{16}'                                   # AWS access key id
  'aws_secret_access_key'
  'ghp_[A-Za-z0-9]{36}'                                # GitHub PAT
  'github_pat_[A-Za-z0-9_]{22,}'
  'xox[baprs]-[A-Za-z0-9-]{10,}'                        # Slack token
  'sk-[A-Za-z0-9]{20,}'                                 # generic API secret
  'AIza[0-9A-Za-z_-]{35}'                               # Google API key
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'                  # private key block
  '(api[_-]?key|secret|password|passwd|token|bearer)["'"'"' :=]+[A-Za-z0-9/_+.=-]{12,}'
)

found=0
while IFS= read -r -d '' file; do
  for pat in "${patterns[@]}"; do
    if grep -Eil "$pat" "$file" >/dev/null 2>&1; then
      echo "POTENTIAL SECRET in committed listing: $file (pattern: $pat)" >&2
      found=1
    fi
  done
done < <(find "$dir" -type f \( -name '*.txt' -o -name '*.json' -o -name '*.yaml' -o -name '*.yml' -o -name '*.md' \) -print0)

if [ "$found" -ne 0 ]; then
  echo "FAIL: secrets must never be committed (see skill §9.1). Move them to .listing-kit/secrets.local or env, then re-run." >&2
  exit 1
fi

echo "Secret scan clean: '$dir' contains no detected credentials."
