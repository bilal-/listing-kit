# Agents & skills in this repo

## listing-kit (v0.5.0)

Walk any mobile-app repo, run it, capture store-compliant screenshots, and assemble the full App Store + Google Play listing (copy, metadata, graphics) into the repo as the source of truth — fastlane-compatible, cross-stack, cross-AI.

**Skill instructions:** [`skills/listing-kit/SKILL.md`](skills/listing-kit/SKILL.md)

Codex installs it as a plugin (`codex plugin marketplace add bilal-/listing-kit`,
then `codex plugin add listing-kit@listing-kit`). Under Copilot CLI, load the
skill file above as context, then follow its pipeline. All work is plain shell-outs; see
`skills/listing-kit/references/platforms/tool-mapping.md` for tool-name
equivalents on your platform.
