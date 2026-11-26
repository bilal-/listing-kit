# Working on this repository

Edit the agent workflow in [SKILL.md](skills/listing-kit/SKILL.md). Check commands against the bundled launcher and their implementations. Run `bash tests/run.sh` before committing. Use temporary fixtures for tests that need Git or a listing.

Change store facts in [stores.json](skills/listing-kit/specs/stores.json), then run `python3 skills/listing-kit/scripts/specs/render.py`. The marked tables in the store references are generated.

Edit [.claude-plugin/plugin.json](.claude-plugin/plugin.json) and run `bash skills/listing-kit/scripts/package/generate-manifests.sh` to regenerate the marketplace, Gemini manifest and skill VERSION. Keep credentials and private settings out of commits.
