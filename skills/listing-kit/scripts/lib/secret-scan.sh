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
  'aws_secret_access_key'
  "${B}gh[pousr]_[A-Za-z0-9_]{36,}"                     # GitHub tokens (PAT, OAuth, app incl. ghs_APPID_JWT, refresh)
  'github_pat_[A-Za-z0-9_]{22,}'                        # GitHub fine-grained PAT
  "${B}glpat-[A-Za-z0-9_-]{20,}"                        # GitLab PAT
  "${B}(xox[abposre]|xapp|xwfp)-[A-Za-z0-9-]{10,}"     # Slack bot/user/app/refresh/workflow tokens
  "${B}sk-(proj-|ant-|svcacct-)?[A-Za-z0-9_-]{20,}"     # OpenAI / Anthropic / generic sk- keys
  "${B}(sk|rk)_(live|test)_[A-Za-z0-9]{16,}"            # Stripe secret / restricted key
  "${B}whsec_[A-Za-z0-9]{24,}"                          # Stripe webhook signing secret
  'AIza[0-9A-Za-z_-]{35}'                               # Google API key
  '"(private_key_id|private_key)"[[:space:]]*:'         # Google service-account JSON
  "${B}ey[A-Za-z0-9_-]{8,}\.ey[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"   # JWT ('{"' and '{ ' both encode to "ey")
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'                  # private key block
  "${B}bearer[[:space:]]+[A-Za-z0-9._~+/-]{20,}"        # Authorization: Bearer <token>
)
# Case-sensitive patterns (grep without -i): AWS key ids are upper-case, and
# matching "asia..." in an ordinary URL would be a false alarm.
cs_patterns=(
  "${B}(AKIA|ASIA)[0-9A-Z]{16}([^A-Za-z0-9]|$)"         # AWS access key id
)

# Generic "keyword = value" credentials: an explicit : or = and a value of 12+
# characters that either contains a digit (filtered by awk below) or ends the
# assignment (end of line, quote, comma, semicolon). So "password: Correct
# HorseBatteryStaple" on its own line is caught, while copy like "Password:
# synchronization made easy" (more words follow) stays clean.
generic_kw='(api[_-]?key|client[_-]?secret|secret|password|passwd|token|bearer)'
generic="${generic_kw}[\"']?[[:space:]]*[:=][[:space:]]*[\"']?[A-Za-z0-9/_+.=-]{12,}"
patterns+=("${generic}([\"',;}]|[[:space:]]*$)")

# Text files only — screenshots and other binaries are never scanned.
includes=(--include='*.txt' --include='*.json' --include='*.yaml' --include='*.yml' --include='*.md')

found=0
scan_pattern(){ # grep-flags pattern
  local rc=0 hits
  hits="$(grep -rEl"$1" "${includes[@]}" -e "$2" "$dir")" || rc=$?
  case "$rc" in
    0) while IFS= read -r file; do
         echo "POTENTIAL SECRET in committed listing: $file (pattern: $2)" >&2
       done <<<"$hits"
       found=1 ;;
    1) ;;   # no match
    *) echo "ERROR: secret scan could not read '$dir' (grep exit $rc); refusing to report clean." >&2
       exit 2 ;;
  esac
}
for pat in "${patterns[@]}"; do scan_pattern i "$pat"; done
for pat in "${cs_patterns[@]}"; do scan_pattern "" "$pat"; done

# Generic rule: grep -o the candidates, keep only values with a digit.
rc=0; hits="$(grep -rEioH "${includes[@]}" -e "$generic" "$dir")" || rc=$?
case "$rc" in
  0) flagged="$(printf '%s\n' "$hits" | awk '{ f=$0; sub(/:.*/, "", f); m=substr($0, length(f) + 2); v=substr(m, match(m, /[:=]/) + 1); if (v ~ /[0-9]/) print f }' | sort -u)"
     if [ -n "$flagged" ]; then
       while IFS= read -r file; do
         echo "POTENTIAL SECRET in committed listing: $file (generic keyword = value)" >&2
       done <<<"$flagged"
       found=1
     fi ;;
  1) ;;
  *) echo "ERROR: secret scan could not read '$dir' (grep exit $rc); refusing to report clean." >&2
     exit 2 ;;
esac

if [ "$found" -ne 0 ]; then
  echo "FAIL: secrets must never be committed (see skill §9.1). Move them to .listing-kit/secrets.local or env, then re-run." >&2
  exit 1
fi

echo "Secret scan clean: '$dir' contains no detected credentials."
