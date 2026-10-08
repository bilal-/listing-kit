# listing-kit architecture

How listing-kit is put together and why. For using it, see the [guide](GUIDE.md);
for the instructions an agent follows, see
[`skills/listing-kit/SKILL.md`](../skills/listing-kit/SKILL.md).

## The idea

listing-kit is not a screenshot tool. Its output is a complete, version-controlled
listing (copy, keywords, URLs, screenshots, graphics) stored in the app's repo, in
the layout fastlane's `deliver` and `supply` already read. Keeping it in the repo
means store copy is reviewed like code, screenshots can be regenerated instead of
hand-curated, and publishing tools get clean input with no translation.

Publishing itself is out of scope. Anything that can run `fastlane deliver` /
`supply` can publish what listing-kit writes.

## Layout

```
skills/listing-kit/
  SKILL.md               the orchestration core: the pipeline and its decision rules
  references/            modules the core loads when it reaches a step
    stores/              per-store rules (sizes, limits, required assets)
    stacks/              per-stack detect / build / launch / capture
    driving/maestro.md   the shared drive layer
    metadata/            the fastlane tree, file names, secrets boundary
    platforms/           tool-name equivalents across AI agents
  scripts/               deterministic helpers the agent runs
    capture/  generate/  validate/  package/  lib/
tests/                   zero-dependency bash suite (unit, structure, integration)
examples/                apps to run the skill against, with their committed output
```

## Core and modules

`SKILL.md` holds the pipeline and the judgment calls (what to ask, when to stop,
what never to invent). It never contains stack- or store-specific commands; those
live in `references/`. Adding a stack or a store means writing a module, not
editing the core. The core loads a module only when it reaches the step that
needs it, which keeps the agent's context small.

## The pipeline

```
detect → doctor → discover → plan → configure → run → drive → capture → assemble → validate
```

Two ordering choices matter:

- **Discover and Curate come before any build.** Screens are found from static
  signals (routes, nav graphs, storyboards) and the user picks, orders, names, and
  describes the desired state of each one before the expensive build starts.
- **Validate runs last**, against the tree Assemble actually wrote, so generated
  metadata and graphics are checked too.

Heavy tools are installed only when a step needs them: Maestro and its JDK at
Drive, ImageMagick from Capture onward. Doctor reports what's missing and what
each gap degrades to.

## Driving with Maestro

Maestro is the one UI driver that works across native iOS, native Android,
Flutter, and React Native / Expo, on both simulators and emulators, through the
accessibility hierarchy. Standardizing on it shrinks each stack module to "build,
install, launch", and turns driving into one shared capability instead of four.

Each flow is saved to `.listing-kit/flows/` and committed: it's the rerunnable
recipe that makes reruns and CI possible. Flows start from a clean launch, tap
accessibility labels, and assert real content, so an empty or wrong screen fails
instead of being captured. (On iOS, custom-scheme deep links raise a system alert
Maestro can't dismiss reliably, so labels are preferred.) Screens Maestro can't
reach (canvas UIs, missing semantics, unscriptable auth) fall back to manual
assist.

Screenshots are taken with `simctl` / `adb`, not Maestro, for full-resolution
output with the sanitized status bar intact, then flattened to 24-bit RGB because
both stores reject the raw RGBA captures.

## Scripts: where determinism lives

The agent handles judgment; anything that must be exact is a script with tests.

| Area | Scripts |
|---|---|
| Capture | `sanitize-status-bar.sh`, `grant-permissions.sh`, `normalize-screenshot.sh` |
| Generate | `feature-graphic.sh` |
| Validate | `validate-listing.sh` (the store-rule gate), `visual-diff.sh` (informational) |
| Package | `build-review.sh`, `install-review-hook.sh`, `generate-manifests.sh` |

Shared logic lives once in `scripts/lib/`:

- `imginfo.py` reads PNG/JPEG headers (size, depth, alpha) with no ImageMagick.
- `apple-screenshot-sizes.tsv` maps App Store sizes to display classes.
- `fields.py` defines every copy field's limit, unit, and required flag.
- `listing.py` discovers locales and images within the fastlane tree.
- `apple_assets.py` adds header and upload-plan locales for Apple, and validates
  headers and planned upload sets.
- `imagemagick.sh` finds ImageMagick 7 or 6.
- `secret-scan.sh` enforces the secrets boundary.

The validator and review page share `fields.py` for copy rules,
`apple_assets.apple_locales` for Apple locale discovery, and `listing.py` for Play
locales and image discovery. This keeps the validation results and preview aligned.

Scripts are bash 3.2+ (macOS's default) plus Python 3.8+ standard library. Each
documents its exit codes in its header. Generally `0` is success, `1` means a check
or operation failed, `2` means bad usage or an unusable setup, and `3` means an
optional tool is missing and the caller should fall back.

## Secrets boundary

The committed tree is the source of truth for non-secrets only. Login
credentials, API tokens, and seed-data secrets live in a git-ignored
`.listing-kit/secrets.local` or environment variables, and flows reference them
rather than inlining them. `validate-listing.sh` runs `secret-scan.sh` on `fastlane/`,
`store-assets/`, `.listing-kit/flows/`, and the public `.listing-kit/asset-plan.json`
file. It checks known credential formats and generic `key = value` assignments;
Assemble and Validate fail on a hit. Private `.listing-kit/secrets.local` files
remain outside these scans.

## Store rules drift

Apple and Google change sizes and limits often. The numbers in
`references/stores/*.md` (and the size table) are a dated snapshot. The skill
tells agents to re-verify against live store docs when a build targets the
stores, and the validator's checks are kept in sync with the references.

## Cross-agent portability

Everything is markdown plus shell-outs to `xcrun simctl`, `adb`, `flutter`, the
Expo / RN CLI, `maestro`, ImageMagick, and Python, so any agent that can run a
shell can run the skill. There is one canonical `SKILL.md`; the Claude Code plugin
manifests are maintained by hand, and `generate-manifests.sh` emits
`gemini-extension.json`, `AGENTS.md`, and a Kiro steering doc from `plugin.json`.
A test fails CI if the committed copies drift from the generator.

## Review page and commit hook

`build-review.sh` writes a static `listing-review.html` (copy with copy buttons,
screenshots grouped by device class, the validator's output) for reviewing the
listing and pasting copy into the store consoles. `install-review-hook.sh` adds a
pre-commit hook that rebuilds the page from the staged tree whenever
`fastlane/**` changes, without altering how an existing hook behaves.
