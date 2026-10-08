---
name: listing-kit
description: Use when a user wants App Store / Google Play listing assets for a mobile app — screenshots, store copy, metadata, or a feature graphic — generated from their repo. Triggers on "store screenshots", "app store listing", "play store assets", "prepare my app for submission", "fastlane metadata", or pointing the agent at an iOS/Android/Flutter/React Native repo to produce listing material. Captures store-compliant screenshots and writes a complete, version-controlled listing into the repo as the source of truth.
---

# listing-kit

**App-store presence, in your repo.** This is *not* "a screenshot tool." It produces a complete, version-controlled source of truth for what appears on the App Store and Google Play — screenshots, copy, keywords, URLs, graphics — stored in the repo in a fastlane-compatible layout, kept in sync with the running app.

Publishing to the stores is **out of scope** (v1). Everything is structured so a later step or existing fastlane actions can publish it.

## When to use this

Use when the user points you at a mobile-app repository and wants store listing material. If they only want one screenshot of one screen, you can still run the relevant steps — but the value is the full, regenerable listing.

## Operating principles (read before acting)

1. **The repo is the source of truth — for non-secrets only.** Listing copy, screenshots, and graphics get committed. **Credentials and seed secrets NEVER get committed** — see `references/metadata/fastlane-layout.md` §secrets and `scripts/lib/secret-scan.sh`.
2. **Preserve existing listings on reruns.** If `fastlane/` already contains metadata or screenshots, treat it as the baseline, not disposable generated output. Read the existing `.txt` files before drafting copy, keep wording that is still accurate and within limits, and make surgical edits for new features, changed positioning, missing required fields, or validation failures. Do not rewrite a good description, title, subtitle, keyword list, release note, or caption just to make it sound new. Prefer a short inserted sentence or phrase in the best existing spot, then show the diff for review.
3. **Store specs drift.** The numbers in `references/stores/*.md` are a snapshot. When a build actually targets the stores, prefer verifying against current App Store Connect / Play Console docs (use web search if available) and treat the reference docs as defaults, not gospel.
4. **Stay portable.** Core logic is markdown + shell. Shell out to `xcrun simctl`, `adb`, `flutter`, the Expo/RN CLI, `maestro`, and ImageMagick — never to an agent-specific browser/MCP capability. See `references/platforms/tool-mapping.md` for tool-name equivalents across AI platforms.
5. **Gate heavy dependencies.** Maestro + JDK are only needed at the **Drive** step; ImageMagick only from **Capture** onward (screenshot normalization, feature graphic). Don't make the user install them up front.
6. **Preserve release metadata.** Preparing listing assets does not require a marketing-version bump. Keep the app's current release version and follow its existing build-number policy; do not invent a release to capture screenshots.
7. **Confirm before expensive work.** Get the user to commit to a screen list *before* building (the Discover step), and confirm target stores/devices before running.

## The pipeline

```
detect → doctor → discover → plan → configure → run → drive → capture → assemble → validate
```

Run these in order. Each step has a reference doc; load it when you reach the step.

### 1. Detect — classify the stack and locate the app root
Identify the stack from manifest signals. See `references/stacks/` (each stack doc opens with its detection signatures). A repo may be cross-platform (RN/Flutter) or contain both a native iOS and native Android project. **Report what you found and ask the user to confirm targets.**

**Record the app root** — the directory that holds the manifest (`app.json`/`package.json`, `pubspec.yaml`, `*.xcodeproj`, `build.gradle`). This is the repo root for a single-app repo, but a **subdirectory in a monorepo** (e.g. `apps/mobile/`). All output — `fastlane/` and `.listing-kit/` — is written relative to the app root, never assumed at the repo root. If multiple apps are found, ask which to target; each gets its own `fastlane/` under its own root.

### 2. Doctor — pre-flight the environment
Verify required toolchains before any build: per-stack SDKs (Xcode + CocoaPods, JDK + Android SDK, Flutter SDK, Node), plus `xcrun simctl` / `adb`, and `python3` (the validator, review page, and commit hook use it). Report **optional** tools and what their absence degrades to:
- **ImageMagick** missing → screenshots can't be normalized to RGB at Capture (prompt to install it then), and feature-graphic generation falls back to asking the user for one.
- **Maestro + JDK** missing → the Drive step falls back to manual-assist. (Do not install Maestro here; it is gated to first use in Drive.)
- **Optional device tooling** missing → defer only that target, with a reason in
  the plan and review; continue buildable targets and store copy/graphics. Check
  stack-specific capabilities before proposing the plan. Do not install or
  switch SDKs automatically, or silently drop an already approved active target.

Fail fast with clear fix instructions. Building mobile apps is fragile — a clean Doctor report saves the user a long, confusing build failure later.

### 3. Discover — build the candidate screen inventory (static, before building)
Enumerate screens/features from **static repo signals** (route configs, storyboards/SwiftUI, nav graphs, deep links) per the discovery table in each `references/stacks/*.md`. This is cheap and happens before any build. Produce a candidate inventory.

### 4. Curate — let the user choose (part of Discover)
Present the inventory and capture **four things per screen** the user keeps:
1. **Select** — in the store set or not.
2. **Order** — sequence on the listing (the first screenshot matters most).
3. **Name** — the marketing caption/intent (differs from the in-app screen name). You may propose captions from component analysis; the user edits them.
4. **Desired state** — free text, e.g. "Library, populated with books, not empty." You will reason about the UI to reach this.

### 5. Plan — stores, devices, locales
Ask which stores to target, then device classes. Detect hints (iPad support in `Info.plist`, Wear OS module, watchOS target) and pre-select, but always confirm. Default locale is `en-US` (single-locale in v1). Defaults: target both stores if both buildable; **5 hero screens** per device class. See `references/stores/`. For Apple, select exact console upload slots and any Header Asset variants, then persist the approved coverage in `.listing-kit/asset-plan.json` as described in `references/metadata/fastlane-layout.md`. Treat deferred targets as deferred, not missing launch requirements.

### 6. Configure — inputs, credentials, seed data
Gather/confirm metadata inputs (name, subtitle, URLs, copyright, category). If `fastlane/` already exists, inventory the current metadata first and ask which app changes it should reflect (then follow principle 2). Detect **Auth/Demo modes** (`mock_data.json`, `--demo` flags, demo build configs). **Secrets never enter the committed tree** — store them in a git-ignored `.listing-kit/secrets.local` or environment variables and reference (don't inline) them in Maestro flows.

**Never fabricate metadata.** Values that can only come from the user — **support / marketing / privacy-policy URLs, copyright, category** — must never be invented. If you don't have a value, **ask**; under `--non-interactive`, **leave the field unwritten (omit the `.txt` file)** rather than writing a guessed or empty value. An omitted required field is then surfaced by Validate (and shown blank with a ⚠ marker on the review page); a fabricated URL could pass review while pointing somewhere wrong.

**Copy style (applies to any caption or store text you draft or suggest, here and in Curate):** write the way a person would, and on an existing listing keep the user's voice (principle 2). **Avoid em dashes and "X — Y" dash clauses** (a common AI tell that makes a listing look machine-written); use commas, periods, or parentheses instead. Also avoid other tells like "Whether you're…", "elevate", "seamless", "unleash". Keep ordinary hyphenated words (`step-by-step`) and product names (`listing-kit`). Prefer short, concrete sentences. The user reviews and edits all copy, so propose plain drafts they can keep as-is.

### 7. Run — build, install, sanitize, launch
Bootstrap dependencies, build, and install on each required simulator/emulator (see the per-stack doc for exact commands). Then, **before launching the app**:
- **Sanitize status bars** to 9:41 AM, full battery/signal: run `scripts/capture/sanitize-status-bar.sh`.
- **Pre-grant permissions** to avoid blocking dialogs: run `scripts/capture/grant-permissions.sh` (note its caveats — camera/ATT can't be pre-granted on iOS).
- Then launch the app (Maestro's `launchApp` in Drive does this).

### 8. Drive — reach each curated state
Driving is a **shared capability via Maestro** (one YAML flow language across all stacks/platforms). See `references/driving/maestro.md`. This is where Maestro + JDK get installed (prompt now, not earlier). For each screen:
1. Confirm it exists at runtime (`maestro studio` / UI snapshot) and reconcile against the static inventory.
2. Author a Maestro flow that starts from a clean launch and taps accessibility labels, asserting real content on the target screen. Deep links are fine on Android, but on iOS a custom-scheme link raises an "Open in app?" alert Maestro can't dismiss reliably (see `references/driving/maestro.md`).
3. Reach the desired state via demo mode / mock data / mock-auth; prioritize bypass routes for social logins (they often fail on simulators).
4. **Reject empty states before capturing.** A deep link or fresh launch lands on whatever state the app currently has, which is often empty ("No notes yet", an empty list, a zero-results screen) — the most common weak store screenshot. Confirm the screen is actually **populated** before you capture it; if it isn't, seed/mock data to fill it, go to a populated instance, or drop/replace the screen back in Curate. Don't ship an empty screen just because the route resolved.
5. **Manual-assist fallback** when Maestro can't reach a state (canvas/game UIs, missing semantics, unscriptable auth). Under `--non-interactive`, skip and mark the screen **Missing**.

Persist each Maestro flow — it is the rerunnable navigation recipe for next time.

### 9. Capture — screenshot at required dimensions
Capture with **SDK tooling** (`xcrun simctl io ... screenshot`, `adb exec-out screencap`) rather than Maestro's own `takeScreenshot`, for clean full-resolution output with the status-bar override intact. Sizes come from `references/stores/`. Capture each selected upload slot at its accepted native size. For Apple, Dynamic Island medium is currently required; a larger iPhone capture does not fill that slot. Verify current specs and the active asset plan before picking simulators.

**Normalize the format — raw `simctl`/`adb` output is 32-bit RGBA, which both stores reject for screenshots.** Flatten every screenshot to RGB / no-alpha / 8-bit by running `scripts/capture/normalize-screenshot.sh` (input, output); add `--play` for Play phone screenshots to also crop anything taller than 9:16 to exactly 9:16 (top-aligned), which meets Play's 2:1 limit and its promotion bar. **Capture tablet sets when the app supports them** (iPad if `supportsTablet`/device-family 2; Android tablet if not restricted) — see the detection sections in `references/stores/`.

### 10. Assemble — write the fastlane tree, then assert the secrets boundary
Write everything into the fastlane layout **at the app root from step 1** (`references/metadata/fastlane-layout.md` §Where the tree lives — repo root for single-app repos, a subdirectory in a monorepo). On reruns, update only files whose content actually changed, avoid churn in existing metadata and screenshots, and leave unrelated locales/stores untouched. Encode the curated order as numeric filename prefixes (`01_…`, `02_…`) — fastlane derives store display order from filename sort. Generate the Play **feature graphic** with `scripts/generate/feature-graphic.sh` (ImageMagick; falls back to prompting), writing it to `images/featureGraphic.png` and the 512×512 icon to `images/icon.png` directly under the Play locale (fastlane `supply` does not upload nested `featureGraphic/` or `icon/` folders). For Apple headers, follow the Header Asset section in `references/stores/apple-app-store.md`; save them outside Fastlane screenshots under `store-assets/apple/<locale>/` and include them in the review/handoff.

**Finally, run `scripts/lib/secret-scan.sh` against the committed tree and FAIL the run if any credential leaked.**

### 11. Validate & review — check the written tree against store rules
Validate what Assemble actually wrote, so generated metadata and graphics are covered. Run `scripts/validate/validate-listing.sh` (pass the app root). It checks the listing against the rules in `references/stores/*.md` (copy limits and required fields, screenshot sizes, formats and counts per locale, Play graphics, and the secret scan) and exits non-zero on any failure; warnings, such as missing Play promotion eligibility, don't fail the run. It checks **only the store(s) actually present**. If device-family detection is wrong (an iPad-only app, or `supportsTablet` computed at runtime), set `LK_SUPPORTS_IPHONE=0` / `LK_SUPPORTS_IPAD=0|1`. If a previous screenshot set exists (a prior commit or a backup dir), also run `scripts/validate/visual-diff.sh` (`<previous-dir> <current-dir>`) for a per-screen regression report; it never blocks. Fix failures (back in Configure, Capture, or Assemble) and rerun until it passes, or report what's left.

Then run `scripts/package/build-review.sh` (pass the app root) to emit `listing-review.html` at the app root — a single static page (copy buttons, screenshots per device class, the validator's results) for reviewing the listing and pasting copy into the store consoles. It is read-only and never writes into `fastlane/`.

#### Commit-time review refresh

If the app root is inside a git worktree, run `scripts/package/install-review-hook.sh` (pass the app root). This installs or updates a repo-local pre-commit hook that reruns `build-review.sh` and stages the refreshed `listing-review.html`.

The hook watches staged changes to `fastlane/**`, `store-assets/apple/**`, `.listing-kit/asset-plan.json`, `.listing-kit/flows/**`, root-level `app.json` and `app.config.*`, and any `*.pbxproj` or `Info.plist` files within the app. Deletions and moves out of these paths also trigger a refresh. The page reflects the staged files, including configuration that determines whether iPad screenshots are required. If the app root is not in git, skip this hook and mention that automatic commit-time refresh is unavailable.

Then produce a **report**: per platform/locale, what exists vs. required vs. missing, with next actions.

## Headless / CI mode

When the user asks for a non-interactive or CI run (written `--non-interactive` in these docs; it is a mode you adopt, not a CLI flag), skip manual-assist and any prompt, reports missing assets instead of hanging, and depends on persisted Maestro flows from a prior interactive run.

## Reference map

| Need | Doc |
|---|---|
| Apple sizes, char limits, asset list | `references/stores/apple-app-store.md` |
| Google Play sizes, char limits, asset list | `references/stores/google-play.md` |
| Build/launch/capture per stack | `references/stacks/{ios-native,android-native,flutter,react-native-expo}.md` |
| Driving the app (Maestro) | `references/driving/maestro.md` |
| Where files go + secrets boundary | `references/metadata/fastlane-layout.md` |
| Tool names across AI platforms | `references/platforms/tool-mapping.md` |

## Scripts

| Script | Purpose |
|---|---|
| `scripts/capture/sanitize-status-bar.sh` | iOS `simctl status_bar` + Android demo-mode clean status bar |
| `scripts/capture/normalize-screenshot.sh` | Flatten a raw capture to 24-bit RGB PNG; `--play` also crops to 9:16 |
| `scripts/capture/capture-ios.sh` | Capture an explicit simulator display; reject wrong dimensions or blank frames before replacing an asset |
| `scripts/doctor/iphone-duo.py` | Read-only SDK/device/runtime preflight; JSON result, exit 3 means Duo capture is unavailable |
| `scripts/capture/grant-permissions.sh` | Pre-grant permissions via `simctl privacy` / `adb pm grant` (with caveats) |
| `scripts/generate/feature-graphic.sh` | 1024×500 icon-on-gradient Play feature graphic (ImageMagick) |
| `scripts/lib/secret-scan.sh` | Fail the run if secrets leaked into the committed tree |
| `scripts/lib/imagemagick.sh` | Find ImageMagick 7 or 6 and check the tools an operation needs (sourced by the image scripts) |
| `scripts/lib/apple-screenshot-sizes.tsv` | App Store screenshot sizes → display class (keep in sync with `references/stores/apple-app-store.md`) |
| `scripts/lib/apple_assets.py` | Apple locales across metadata, screenshots, headers and plans; header/plan validation |
| `scripts/lib/imginfo.py` | PNG/JPEG size/depth/alpha facts + App Store display class (shared by validate and review) |
| `scripts/lib/fields.py` | Store copy fields: limits, units, required flags (shared by validate and review) |
| `scripts/lib/listing.py` | Locale and image discovery within the fastlane tree |
| `scripts/validate/validate-listing.sh` | Validate the listing tree against App Store + Play rules (Validate step) |
| `scripts/validate/visual-diff.sh` | Per-screen regression report between a previous and current screenshot set (Validate step) |
| `scripts/package/generate-manifests.sh` | Emit per-AI-platform install manifests from this canonical skill |
| `scripts/package/build-review.sh` | Emit a static `listing-review.html` (copy buttons, screenshots, embedded validation) for human review |
| `scripts/package/install-review-hook.sh` | Refresh `listing-review.html` when [staged listing inputs](#commit-time-review-refresh) change |
