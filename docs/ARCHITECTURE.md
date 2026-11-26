# How the kit works

An agent selects screens and writes copy with the user. The [launcher](../skills/listing-kit/bin/listing-kit) dispatches the repeatable work to Bash and Python. Each app has its own plan, listing files and review page.

## Rules and detection

[stores.json](../skills/listing-kit/specs/stores.json) defines store fields, limits, screenshot slots, accepted sizes, graphics, upload routes and conditional requirements. The rules loader merges an app's `.listing-kit/specs.override.json` before checking the result. Record the source URL for a local difference. The [Apple](../skills/listing-kit/references/stores/apple-app-store.md) and [Play](../skills/listing-kit/references/stores/google-play.md) reference tables are rendered from the bundled file.

`listing-kit detect` reads app-owned native declarations and static Expo settings and reports yes, no or unknown with evidence. A valid plan's explicit `platforms` flags take precedence. For validation, the iPhone and iPad environment overrides can supply facts, and the build SDK can resolve a dated rule's exception. Ask about an unknown capability.

## Plan and capture

[Format 2](../skills/listing-kit/references/plan-file.md) describes the app, ordered screens, locale mappings, target slots and style. `listing-kit plan check` checks relationships, sizes, counts and destination collisions. `listing-kit plan manifest` expands active combinations into capture jobs and output records. The records carry resolved trees, raw and final paths, localized copy and the route to each store slot.

`listing-kit capture` selects devices for the manifest's jobs and checks that the app is installed. Maestro receives the app ID, device locale, target ID and screen ID. The flow handles navigation, permissions and orientation. Capture sanitizes the status bar, reads the native display with simctl or adb, checks the frame and replaces the raw PNG after normalization. A framed shot can keep its native size. Raw mode requires the exact upload size.

## Composition and ownership

`listing-kit compose` uses the resolved style. Framed phone shots normally use caption-top. Play tablet and Chromebook slots supply band as their template default. The plan can also request a panel, headers, a feature graphic or an icon derived from local artwork. Raw output bypasses the browser.

For template output, the renderer starts a Chromium-family browser over a debugging pipe. It intercepts page requests and serves the template and allowed assets from memory. Requests outside the allow-list fail the render. ImageMagick produces the final RGB screenshot. Preview writes a self-contained HTML page.

The composer compares content and style keys, tracks renderer details and checks the existing output hash. The [ownership code](../skills/listing-kit/scripts/compose/ownership.py) serializes writes, records pending replacements and recovers them on rerun. A style-only redraw needs explicit approval. An unowned or edited destination is a conflict unless the user authorizes adoption. Unchanged stale files move to the held directory. See the [lock, inventory and tree layout](../skills/listing-kit/references/metadata/fastlane-layout.md).

## Validation, review and handoff

`listing-kit validate` scans listing inputs for secrets, checks copy and images and prints failures and warnings. `listing-kit review` builds a static page from the listing and the validation report. The Git hook checks inputs from the index, blocks credentials and updates the page for staged listing changes. It watches staged changes under `fastlane/`, `store-assets/` and `.listing-kit/`, plus root Expo config and app-owned Xcode project and Info.plist files. Staging private local settings or an incomplete secret scan blocks the commit. If page generation fails after a clean scan, the hook warns. Use `listing-kit hook status` to check the registration after updating the kit.

`listing-kit handoff` reads the conventional listing trees and builds a disposable folder with console destinations. It records file hashes to protect local edits during a rebuild. The folder includes its own ignore file. The builder does not read split root settings from the format-2 plan.

## Fastlane and CI

`listing-kit fastlane setup` checks read access. When given a key-path option it saves the external credential path in ignored local settings. `listing-kit pull` downloads into scratch space, merges text against a hash baseline and keeps remote screenshots for comparison. `listing-kit publish` prepares a filtered validation tree, reads the live listing, reports differences and shows the proposed command when there are changes to send. Both upload gates are off until the corresponding live tests pass.

`listing-kit ci init` generates GitHub or GitLab jobs for listing validation, a review artifact and a store-specific manual publish job. Pin the kit ref used by the runner. [CI configuration](CI.md)

## Drift watch

The [weekly workflow](../.github/workflows/drift.yml) compares selected facts from store pages and fastlane sources with committed digests. It opens or updates one maintainer issue when facts change or a source cannot be checked. A maintainer reviews the differences, updates the rules, regenerates the tables and accepts new digests. Offline tests use saved pages. [Rule change procedure](../CONTRIBUTING.md)
