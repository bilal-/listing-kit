#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

# ---- JSON manifests are valid ----
for j in .claude-plugin/plugin.json .claude-plugin/marketplace.json gemini-extension.json; do
  it "valid JSON: $j"
  if json_valid "$ROOT/$j"; then pass "$j"; else fail "invalid JSON: $j"; fi
done

# ---- name is consistent everywhere ----
it "skill/plugin/marketplace names all agree"
skill_name="$(grep -E '^name:' "$SKILL_DIR/SKILL.md" | head -1 | sed -E 's/^name:[[:space:]]*//')"
plugin_name="$(json_get "$ROOT/.claude-plugin/plugin.json" name)"
mkt_name="$(json_path "$ROOT/.claude-plugin/marketplace.json" "['plugins'][0]['name']")"
assert_eq "listing-kit" "$skill_name" "SKILL.md frontmatter name"
assert_eq "$skill_name" "$plugin_name" "plugin.json matches skill"
assert_eq "$skill_name" "$mkt_name" "marketplace matches skill"

# ---- SKILL.md frontmatter is well-formed ----
it "SKILL.md has name + description frontmatter"
assert_contains "$(head -5 "$SKILL_DIR/SKILL.md")" "name:"
assert_contains "$(head -5 "$SKILL_DIR/SKILL.md")" "description:"

# ---- all expected reference docs exist ----
for d in stores/apple-app-store stores/google-play \
         stacks/ios-native stacks/android-native stacks/flutter stacks/react-native-expo \
         driving/maestro metadata/fastlane-layout platforms/tool-mapping; do
  it "reference doc exists: $d.md"
  assert_file "$SKILL_DIR/references/$d.md"
done

# ---- all scripts exist and are executable ----
for s in capture/sanitize-status-bar capture/grant-permissions \
         generate/feature-graphic lib/secret-scan package/generate-manifests \
         validate/validate-listing; do
  it "script present + executable: $s.sh"
  assert_exec "$SKILL_DIR/scripts/$s.sh"
done

# ---- every references/ or scripts/ path referenced in SKILL.md resolves ----
it "all references/ + scripts/ paths in SKILL.md resolve"
missing=0
while read -r p; do
  case "$p" in *"{"*|*"*"*) continue;; esac   # skip glob/brace listings
  if [ ! -e "$SKILL_DIR/$p" ]; then echo "      broken ref: $p"; missing=1; fi
done < <(grep -oE '`(references|scripts)/[^`]+`' "$SKILL_DIR/SKILL.md" | tr -d '`' | sort -u)
[ "$missing" -eq 0 ] && pass "no broken in-skill references" || fail "SKILL.md references a missing file"

# ---- gemini contextFileName points at a real file ----
it "gemini-extension.json contextFileName resolves"
ctx="$(json_get "$ROOT/gemini-extension.json" contextFileName)"
assert_file "$ROOT/$ctx"

# ---- relative markdown links resolve ----
check_links() {
  local file="$1" dir; dir="$(dirname "$file")"
  local broken=0 target
  while read -r target; do
    case "$target" in http*|https*|mailto:*|\#*) continue;; esac
    target="${target%%#*}"; [ -z "$target" ] && continue
    if [ ! -e "$dir/$target" ]; then echo "      broken link in ${file#$ROOT/}: $target"; broken=1; fi
  done < <(grep -oE '\]\([^)]+\)' "$file" | sed -E 's/^\]\(//; s/\)$//')
  return $broken
}
for md in README.md docs/GUIDE.md CONTRIBUTING.md examples/README.md; do
  it "relative links resolve: $md"
  if check_links "$ROOT/$md"; then pass "$md"; else fail "broken link(s) in $md"; fi
done

summary
