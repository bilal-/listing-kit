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
2. **Store specs drift.** The numbers in `references/stores/*.md` are a snapshot. When a build actually targets the stores, prefer verifying against current App Store Connect / Play Console docs (use web search if available) and treat the reference docs as defaults, not gospel.
3. **Stay portable.** Core logic is markdown + shell. Shell out to `xcrun simctl`, `adb`, `flutter`, the Expo/RN CLI, `maestro`, and ImageMagick — never to an agent-specific browser/MCP capability. See `references/platforms/tool-mapping.md` for tool-name equivalents across AI platforms.
4. **Gate heavy dependencies.** Maestro + JDK are only needed at the **Drive** step; ImageMagick only at feature-graphic generation. Don't make the user install them up front.
5. **Confirm before expensive work.** Get the user to commit to a screen list *before* building (the Discover step), and confirm target stores/devices before running.

## The pipeline

```
detect → doctor → discover → plan → configure → run → drive → capture → validate → assemble
```

Run these in order. Each step has a reference doc; load it when you reach the step.

### 1. Detect — classify the stack and locate the app root
Identify the stack from manifest signals. See `references/stacks/` (each stack doc opens with its detection signatures). A repo may be cross-platform (RN/Flutter) or contain both a native iOS and native Android project. **Report what you found and ask the user to confirm targets.**

**Record the app root** — the directory that holds the manifest (`app.json`/`package.json`, `pubspec.yaml`, `*.xcodeproj`, `build.gradle`). This is the repo root for a single-app repo, but a **subdirectory in a monorepo** (e.g. `apps/mobile/`). All output — `fastlane/` and `.listing-kit/` — is written relative to the app root, never assumed at the repo root. If multiple apps are found, ask which to target; each gets its own `fastlane/` under its own root.

### 2. Doctor — pre-flight the environment
Verify required toolchains before any build: per-stack SDKs (Xcode + CocoaPods, JDK + Android SDK, Flutter SDK, Node), plus `xcrun simctl` / `adb`. Report **optional** tools and what their absence degrades to:
- **ImageMagick** missing → feature-graphic generation falls back to prompting the user.
- **Maestro + JDK** missing → the Drive step falls back to manual-assist. (Do not install Maestro here; it is gated to first use in Drive.)

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
Ask which stores to target, then device classes. Detect hints (iPad support in `Info.plist`, Wear OS module, watchOS target) and pre-select, but always confirm. Default locale is `en-US` (single-locale in v1). Defaults: target both stores if both buildable; **5 hero screens** per device class. See `references/stores/`.

### 6. Configure — inputs, credentials, seed data
Gather/confirm metadata inputs (name, subtitle, URLs, copyright, category). Detect **Auth/Demo modes** (`mock_data.json`, `--demo` flags, demo build configs). **Secrets never enter the committed tree** — store them in a git-ignored `.listing-kit/secrets.local` or environment variables and reference (don't inline) them in Maestro flows.

### 7. Run — build, launch, sanitize
Bootstrap dependencies, build, and launch on each required simulator/emulator (see the per-stack doc for exact commands). Then:
- **Sanitize status bars** to 9:41 AM, full battery/signal: run `scripts/capture/sanitize-status-bar.sh`.
- **Pre-grant permissions** to avoid blocking dialogs: run `scripts/capture/grant-permissions.sh` (note its caveats — camera/ATT can't be pre-granted on iOS).

### 8. Drive — reach each curated state
Driving is a **shared capability via Maestro** (one YAML flow language across all stacks/platforms). See `references/driving/maestro.md`. This is where Maestro + JDK get installed (prompt now, not earlier). For each screen:
1. Confirm it exists at runtime (`maestro studio` / UI snapshot) and reconcile against the static inventory.
2. Author a Maestro flow, preferring deep links/URL schemes, else tap-by-accessibility-label.
3. Reach the desired state via demo mode / mock data / mock-auth; prioritize bypass routes for social logins (they often fail on simulators).
4. **Manual-assist fallback** when Maestro can't reach a state (canvas/game UIs, missing semantics, unscriptable auth). Under `--non-interactive`, skip and mark the screen **Missing**.

Persist each Maestro flow — it is the rerunnable navigation recipe for next time.

### 9. Capture — screenshot at required dimensions
Capture with **SDK tooling** (`xcrun simctl io ... screenshot`, `adb exec-out screencap`) rather than Maestro's own `takeScreenshot`, for clean full-resolution output with the status-bar override intact. Sizes come from `references/stores/`. Default: capture the largest required size per device family and let the store derive the rest, unless the user wants explicit per-size captures.

**Normalize the format — raw `simctl`/`adb` output is 32-bit RGBA, which both stores reject for screenshots.** Flatten every screenshot to RGB / no-alpha / 8-bit (`magick in.png -background white -alpha remove -alpha off -depth 8 PNG24:out.png`), and crop to satisfy Play's ≤2:1 aspect. **Capture tablet sets when the app supports them** (iPad if `supportsTablet`/device-family 2; Android tablet if not restricted) — see the detection sections in `references/stores/`.

### 10. Validate — check everything against store rules
Validate every asset and metadata field against `references/stores/*.md`: character-limit overflows, dimension/format/aspect violations, missing required assets (e.g. Play feature graphic). If previous screenshots exist, produce a **visual diff** to flag regressions.

### 11. Assemble — write the fastlane tree, then assert the secrets boundary
Write everything into the fastlane layout **at the app root from step 1** (`references/metadata/fastlane-layout.md` §Where the tree lives — repo root for single-app repos, a subdirectory in a monorepo). Encode the curated order as numeric filename prefixes (`01_…`, `02_…`) — fastlane derives store display order from filename sort. Generate the Play **feature graphic** with `scripts/generate/feature-graphic.sh` (ImageMagick; falls back to prompting). **Finally, run `scripts/lib/secret-scan.sh` against the committed tree and FAIL the run if any credential leaked.**

Then produce a **report**: per platform/locale, what exists vs. required vs. missing, with next actions.

## Headless / CI mode

`--non-interactive` skips manual-assist and any prompt, reports missing assets instead of hanging, and depends on persisted Maestro flows from a prior interactive run.

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
| `scripts/capture/grant-permissions.sh` | Pre-grant permissions via `simctl privacy` / `adb pm grant` (with caveats) |
| `scripts/generate/feature-graphic.sh` | 1024×500 icon-on-gradient Play feature graphic (ImageMagick) |
| `scripts/lib/secret-scan.sh` | Fail the run if secrets leaked into the committed tree |
| `scripts/package/generate-manifests.sh` | Emit per-AI-platform install manifests from this canonical skill |
