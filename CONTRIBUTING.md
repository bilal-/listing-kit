# Contributing to listing-kit

Edit the [agent workflow](skills/listing-kit/SKILL.md) for decisions the agent makes with a user. Put build instructions in the stack references. Implement repeatable operations under `skills/listing-kit/scripts/` and expose them through the launcher. Check the public help and update the guide when a command changes.

## When a store changes its rules

The weekly drift watch reports changes and sources it could not check in one issue, **Store rules drift detected**. Inspect the named sources. If extraction broke, fix the parser and its offline fixture before accepting a new digest.

1. Edit [stores.json](skills/listing-kit/specs/stores.json) and set its verification date to the day you checked the source.
2. Run `python3 skills/listing-kit/scripts/specs/render.py` to regenerate the tables in the store references.
3. Run `bash tests/run.sh`. Include coverage for the rule change.
4. After checking the live sources, run `python3 skills/listing-kit/scripts/specs/drift.py update --fetch`. Review the digest changes alongside the rules and tables before closing the issue.

## Generated files

Edit [.claude-plugin/plugin.json](.claude-plugin/plugin.json) for plugin metadata. Run `bash skills/listing-kit/scripts/package/generate-manifests.sh` to update the marketplace manifest, Gemini extension manifest and installed skill VERSION. The README version badge must carry the plugin version in its alt text and URL.

The example app contains historical listing output. Regenerate its screenshots deliberately on matching devices. Keep the status in [examples/README.md](examples/README.md) accurate when the validator changes.

## Screenshot renderer changes

The composer fingerprints each rendered style with the contents of the selected template HTML, the shared `base.css`, and `RENDERER_VERSION` from `compose.py`. An HTML or CSS edit already changes the affected style fingerprints and only needs a re-record.

For changes to `render.py`, `cdp.py`, `pixels.py`, or `fontcheck.py`, review the effect on rendered pixels. If the code changes pixels, bump `RENDERER_VERSION` before recording. If pixels are unchanged, keep the version. Run this command from the repository root to record the reviewed source hashes and current version.

```sh
python3 tests/unit/renderer_version.py --record
```

Commit the updated `tests/fixtures/renderer-version.json` with the change. Run `LK_REQUIRE_RENDER=1 bash tests/run.sh` to exercise the rendered layouts, including the Arabic system-font fallback.

## Development and review

- Run `bash tests/run.sh`. Put new tests under `tests/unit/`, `tests/integration/` or `tests/structure/` with a `.test.sh` suffix. Use the suite's temporary fixtures for Git operations and stub device or store access.
- Keep shell helpers compatible with Bash 3.2 and Python helpers compatible with Python 3.8. Reuse the shared checks for paths, plans, store rules and secrets.
- Keep store credentials outside the repository. Use synthetic values for tests.
- Open a focused pull request with the reason for the change, affected platforms and test results. See the [code of conduct](CODE_OF_CONDUCT.md) and [license](LICENSE).
