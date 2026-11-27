# Changelog

Notable changes to listing-kit. Versions follow the plugin manifest
(`.claude-plugin/plugin.json`).

## Unreleased

### Store publishing

- `publish --expect-send '<sha256> <file>'` (repeatable) refuses unless the files to send match an approved preview exactly.

- Fastlane failures now print fixed Play and App Store Connect diagnostics. Verbose response bodies, URLs and fastlane error text stay out of CI logs.

- Publish previews list every staged file and its SHA-256, with unified text diffs against the last pull. Play compares and stages text without trailing newlines.
- Protected CI jobs and local runs can validate an approved Play edit with `publish --validate-only`. Its receipt records validation separately from publication. Real uploads remain gated for both stores.
- Interrupted uploads accept an explicit `--resolve STORE applied|not-applied` outcome in CI. An unchanged readback after a failed fastlane command permits retry. Apple screenshot replacement waits through the normal timeout.
- Apple text sends use Spaceship to update staged fields on existing localizations and optional copyright. The preview lists the write scope. Real Play sends fail if Google rejects a review hold. Explicit `--send-for-review` consent is previewed and recorded. Clearing a Play video requires per-locale plan consent.

### Existing listings

- Detect finds Android application modules directly in workspace app folders, shows both native siblings with a root plan example, and prints paths for configured or detected stores.
- Plan check shows where flat Play artwork belongs under the configured metadata directory. Validate and review name missing planned output files. Empty listings fail validation.

- Doctor identifies unversioned plans and reports the installed hook status. Detect and validate can inspect the existing listing while the maintainer ports the plan. Detect also reports declared Play phone coverage separately from device capability evidence.
- Compose filters previews and dry runs by target and screen. Preview labels missing captures alongside available artwork. Targets can read archived PNGs through `rawPattern`, and bundled feature and header graphics support start alignment and per-graphic spacing.
- Review and handoff preserve localized image descriptions. The manual upload guide includes Play console fields and completed receipt entries. Validation explains that other repository tools may still use the old Apple coverage file.
- Validation fails when a planned output is missing or a Play screenshot count differs from the plan.
- Handoff writes the upload index and exits non-zero when the package is incomplete.

### Composition

- Framed screenshots can place captions below the device with `caption-bottom` or over an edge-to-edge capture with `full-bleed`.

- Apps can keep marketing templates, styles and assets in `.listing-kit/templates/`. Create a starter with `listing-kit template new <name>`. Plan checks include source locations, preview embeds the rendered PNG, and template edits use the existing restyle approval.

### Rules and validation

- Validation checks optional App Review contact details and Play video URLs. Validation and the Git review hook reject demo credential files, including empty ones. The hand-upload index lists the App Review fields and each store’s rating questionnaire.

- Validation, review, handoff and publish previews use `listing.json` for Apple screenshot counts, headers and deferrals. Older listings can still use their Apple asset plan.
- Store fields, locales, slot sizes, upload routes and dated requirements live in one rules file. It supplies validation and the generated reference tables and supports app-local overrides.
- Validation reports platform evidence, supports submission-date and iOS SDK checks, and checks image structure and decoding when ImageMagick is available. A weekly drift check reports changed upstream facts or unreadable sources.

### Plan and capture

- Plan format 2 is stable. Newer plans report the required and supported formats and ask you to update listing-kit.
- Format 2 records targets, ordered screens, locales, flow overrides and split fastlane roots. Plan commands check it and print capture jobs and output paths.
- Capture selects simulators or emulators, runs Maestro flows and saves checked raw PNGs. It supports manual navigation, device pins, job selection and a dry run.

### Marketing screenshots

- Compose renders framed shots, bands, panels and store graphics from local assets. It can preview the plan in HTML. Content and style keys avoid unnecessary redraws. A style-only redraw requires explicit approval.

### Hand-upload folder

- Handoff builds an indexed Apple and Play upload folder with text, ordered screenshots, graphics and console destinations. Rebuilds check for changed files before replacing the folder.

### Fastlane commands

- Apple pull recognizes the optional localized Apple TV privacy policy, secondary category and four subcategory files in deliver downloads.
- Setup checks read access using external credential paths. Pull merges downloaded text against a baseline and saves remote screenshot references.
- Publish validates a scratch copy, compares listings and previews the proposed command and gallery replacements. Uploads are disabled for both stores pending live tests.

### Command and CI

- A weekly and manually dispatched macOS job runs the Expo example from checked-in captures through compose, validation, review, and handoff. Run it locally with `bash tests/e2e/example.sh`.

- The launcher exposes plan, capture, compose, validation, review, hook and delivery commands. CI templates generate listing checks, review artifacts and manual store jobs for GitHub or GitLab.
- The marketplace metadata and Gemini manifest come from the plugin manifest. Gemini uses on-demand skill loading. Contributor instructions and installation instructions now have separate homes.
- Tests check the version badge, the example's validation status, documented commands and the plan example.

### Safety fixes

- The review hook scans staged inputs and blocks credential findings and incomplete scans. Fixture Git commands run with isolated configuration.
- Compose checks ownership and content hashes before replacing files, recovers interrupted writes and moves unchanged stale outputs to the held directory.

## 0.5.0 (2026-10-07)

- Apple upload slots are validated by exact size: a large-display iPhone
  screenshot no longer fills the required medium-display slot.
- Apple header assets under `store-assets/apple/<locale>/`, validated and shown
  on the review page.
- `.listing-kit/asset-plan.json` records the approved Apple screenshot sets and
  headers, with deferrals; store-required sets cannot be deferred.
- iPhone Duo sizes, with a preflight that defers Duo capture when the tooling is
  missing.
- `capture-ios.sh` rejects wrong-size and blank captures before replacing a file.
- The commit hook refreshes `listing-review.html` when any staged listing input
  changes, including creative asset folders, flows and app configuration.
- Malformed URLs and non-UTF-8 copy are reported without breaking the review page.
- The asset plan and creative asset folders are scanned for credentials.
- Brand kit and logo set; project site at listing-kit.bilal.sh; Codex install
  instructions; `docs/ARCHITECTURE.md` replaces the earlier plans and specs.

## 0.4.0 (2026-10-04)

- Truncated PNGs are rejected, and ImageMagick is checked per operation.
- Play phone screenshots are cropped to 9:16, and promotion eligibility is
  checked by aspect ratio.
- The secret scan catches more current credential formats and stops flagging
  ordinary copy.
- One locale inventory is shared by the validator and the review page.
- Maestro flows are committed; the skill drives by accessibility labels rather
  than deep links.
- `python3` is listed as a requirement.

## 0.3.1 and earlier

See the [release list](https://github.com/bilal-/listing-kit/releases).
