# listing-kit — Requirements & Design

**Status:** Finalized — all major decisions resolved (§12); ready for build
**Date:** 2026-05-25
**Author:** Bilal Ahmad
**Name:** `listing-kit` (resolved; §12-A)

> A free, open-source, cross-AI skill that walks any mobile-app repository,
> learns how to run it, captures store-compliant screenshots, and assembles
> the full set of App Store + Google Play listing assets and metadata — all
> stored *in the repo* as the source of truth for the live store listings.

---

## 1. Problem & Motivation

Shipping a mobile app means producing a pile of store-listing assets by hand:
correctly-sized screenshots for several device classes, marketing copy under
strict character limits, URLs, copyright, and platform-specific graphics. This
is tedious, error-prone, and repeated on every release. The state shown in a
screenshot also matters — a good listing shows populated "hero" screens, not an
empty login form.

Today this work is scattered across simulators, manual cropping tools,
spreadsheets of copy, and the store consoles themselves. There is no single
source of truth that lives with the code.

**Goal:** a skill that an AI agent (Claude Code, Codex, Copilot CLI, Kiro,
Gemini CLI, etc.) can invoke against a mobile repo to (a) understand and run the
app, (b) drive it into the right states, (c) capture compliant screenshots, and
(d) generate and store all listing metadata in the repo using a convention
compatible with existing publishing tools.

**Non-goal (v1):** actually uploading/publishing to the stores. The metadata is
structured so that a *future* step (or existing fastlane actions) can publish it,
but publishing is explicitly out of scope here.

---

## 2. Core Concept

This is **not** "a screenshot tool." It is an **"app store presence, in your
repo"** tool. Screenshots are one (important) artifact among several. The unit
of value is: *the repo contains a complete, version-controlled source of truth
for what appears on the App Store and Google Play, and the skill keeps it in
sync with the running app.*

Storing this in the repo means:
- Store copy is reviewed like code (PRs, diffs, history).
- Screenshots are regenerable, not hand-curated one-offs.
- Future automation (publishing, A/B copy, localization) has a clean input.

---

## 3. Goals & Success Criteria

A v1 is successful if, run against a real mobile repo, the skill can:

1. **Detect the stack** (native iOS, native Android, Flutter, React Native /
   Expo) and identify how to build/run the app.
2. **Validate the environment** (the "Doctor" check) to ensure required SDKs,
   runtimes, and tools are present before attempting a build.
3. **Run the app** on the appropriate simulator/emulator for each required
   device class, with "sanitized" status bars (9:41 AM, full battery/signal).
4. **Discover and curate** which screens/states should be captured — enumerate
   them from static repo signals before building, then let the user
   select/order/name/state them — and, once running, **determine how to reach
   each** (auth, seed data, navigation, deep links).
5. **Capture screenshots** at all store-required dimensions for the selected
   platforms and device classes.
6. **Collect and write listing metadata** (copy, keywords, URLs, copyright) to
   the repo in a fastlane-compatible layout, prompting the user for anything it
   cannot infer.
7. **Validate** all assets against current store requirements and report what's
   missing or non-compliant.
8. **Work across AI platforms** with no Claude-specific dependencies in the core
   logic.

---

## 4. Scope Decisions (resolved during brainstorming + review)

| Decision | Choice | Rationale |
|---|---|---|
| Screen discovery | **Static-first, then user-curated** (dedicated Discover step, §8.1–8.2) | Enumerate screens from repo signals *before* building, then have the user select/order/name/state them. Gets commitment cheaply, before expensive build work. |
| State acquisition | **Drive interactively, Maestro as the sole driver** (§8.3–8.4) | One cross-stack/cross-platform driver instead of per-stack frameworks; works without the app's pre-existing UI test infra. Manual-assist is the bounded fallback. |
| Stack coverage | **All stacks, detection-driven** | Shared orchestration core + per-stack "actuator" modules (build/launch/capture only; driving is shared). "All stacks" is structurally true on day one; each module deepens over time. |
| Output | **Full listing assets + metadata**, fastlane convention | Beyond raw screenshots: copy, keywords, URLs, copyright, platform graphics. Stored in fastlane `deliver`/`supply` layout. |
| Metadata format | **fastlane convention (`fastlane/` root)** | Instantly compatible with existing publishing tooling; serves the future-publishing goal nearly for free. Industry standard. |
| Distribution | **Generator-driven, all platforms** (§10.2) | One canonical `SKILL.md`; a generator emits each tool's manifest so they never drift. CC/Copilot/Codex share the markdown-skill primitive; Gemini/Kiro/MCP get thin adapters. |
| Feature Graphic | **Auto-generate simple placeholder** | Satisfies the "required to publish" rule on Play Store immediately. 1024x500 PNG with icon on brand gradient. |
| Status Bar | **Sanitized (9:41 AM)** | Ensures professional, consistent screenshots. iOS: `xcrun simctl status_bar <device> override`. Android: **system demo mode** (`adb shell settings put global sysui_demo_allowed 1`, then `adb shell am broadcast -a com.android.systemui.demo` commands to set clock/battery/signal) — *not* plain `adb shell settings`. |
| Headless Mode | **`--non-interactive` flag** | Allows running in CI/CD; skips manual-assist screens and reports missing assets instead of hanging. |

---

## 5. Architecture

The skill is organized as a **shared orchestration core** plus **pluggable
modules**. The core never contains stack- or platform-specific commands; those
live in modules that the core dispatches to.

```
listing-kit/
  SKILL.md                      # entry: orchestration flow + decision logic
  references/
    stores/
      apple-app-store.md        # required device classes, sizes, char limits, asset list
      google-play.md            # required device classes, sizes, char limits, asset list
    stacks/                     # each module: build + launch + boot right device + capture
      ios-native.md             # Xcode projects (drive via shared Maestro layer)
      android-native.md         # Gradle projects (drive via shared Maestro layer)
      flutter.md                # Flutter (drive via shared Maestro layer)
      react-native-expo.md      # RN / Expo (drive via shared Maestro layer)
    driving/
      maestro.md                # shared cross-stack drive layer: flow authoring + studio
    metadata/
      fastlane-layout.md        # exact file tree + filenames for deliver/supply
    platforms/
      tool-mapping.md           # AI-platform tool-name equivalents (CC/Codex/Copilot/Gemini)
  assets/
    device-frames/              # (future) optional bezels for framing
  scripts/
    capture/                    # thin, portable helper scripts where shell isn't enough
    package/                    # generator: emits per-platform manifests from SKILL.md (see §10.2)
```

### 5.1 The pipeline (core flow)

```
detect → doctor → discover → plan → configure → run → drive → capture → validate → assemble
```

1. **Detect** — classify the stack from manifest files (see §6).
2. **Doctor** — verify the local environment (toolchain, SDKs, runtimes). Report missing **required** dependencies (e.g., CocoaPods, Java, Flutter SDK, `xcrun simctl`/`adb`) before starting expensive build work, and report missing **optional** ones that trigger graceful degradation: **ImageMagick** (feature-graphic generation → else prompt, §12-D) and **Maestro + JDK** (the Drive step → else manual-assist, §8.3). Doctor never installs Maestro itself; that is gated to first use (§8.3).
3. **Discover** — build a candidate feature/screen inventory from static repo
   signals, present it to the user, and let them **select, order, name, and
   specify the desired state** for each screen to showcase — *before* any build
   (see §8).
4. **Plan** — determine target platforms (iOS/Android), device classes, and
   locales; ask the user to confirm (see §7).
5. **Configure** — gather/confirm metadata inputs and credentials/seed data
   needed to reach states. Detect potential **Auth/Demo modes** (e.g., presence of `mock_data.json` or `--demo` flags). **Secrets never enter the committed tree** (see §9.1): credentials and seed secrets live in a git-ignored local path or environment variables; only non-secret listing metadata is written under `fastlane/`.
6. **Run** — bootstrap dependencies, build, and launch the app on each required simulator/emulator. **Pre-grant all permissions** (Location, Camera, etc.) via `simctl privacy` / `adb shell pm grant` to avoid blocking dialogs. **Sanitize status bars** (9:41 AM, full battery).
7. **Drive** — navigate to each curated state via the shared Maestro layer
   (`studio` confirms screens exist and fills gaps), with manual-assist fallback
   (see §8).
8. **Capture** — take screenshots at each required dimension.
9. **Validate** — check every asset and metadata field against the store
   reference docs. Include **Visual Diffing** if previous assets exist.
10. **Assemble** — write everything into the fastlane-layout metadata tree, then **assert the secrets boundary** (§9.1): scan the committed tree and fail if any credential leaked.

### 5.2 Why modules

Each stack module answers, in isolation: *how do I build, launch, boot the right
device for, and capture from this stack?* — while **driving is a shared core
capability via Maestro** (see §8), not a per-stack concern. Store modules answer
*what does this store require?* The core orchestrates without knowing the
internals. New stacks or stores are added by writing a module, not by editing the
core.

---

## 6. Stack Detection

Detection is signature-based, checked in priority order:

| Stack | Primary signals |
|---|---|
| React Native / Expo | `app.json`/`app.config.{js,ts}` with `expo`, `metro.config.js`, `react-native` in `package.json` |
| Flutter | `pubspec.yaml` with `flutter:` section, `lib/main.dart` |
| Native iOS | `*.xcodeproj` / `*.xcworkspace`, `Package.swift`, no JS/Dart bridge |
| Native Android | `build.gradle(.kts)` + `AndroidManifest.xml`, no JS/Dart bridge |

A repo may be **cross-platform** (RN/Flutter produce both iOS and Android). A
repo may also contain **both** a native iOS and native Android project. The
skill reports what it found and asks the user to confirm targets before running.

Within React Native, **Expo (managed/prebuild + EAS) and bare RN (metro) have
materially different build/run paths**; the `react-native-expo.md` module
branches on the Expo signals from the table above rather than treating them as a
single toolchain.

---

## 7. Platform & Device Matrix

The skill asks the user which stores to target, then which device classes. It
detects hints from the repo (e.g. iPad support in `Info.plist`
`UISupportedInterfaceOrientations~ipad` / target families; Wear OS module;
`watchOS` target) and pre-selects accordingly, but always confirms.

### 7.1 Apple App Store (current as of research date — re-verify at runtime)

| Class | Required? | Accepted pixel sizes (portrait or landscape) | Max count |
|---|---|---|---|
| iPhone 6.9"/6.7" | Yes (at least one iPhone size required) | 1290×2796 / 2796×1290, 1284×2778 / 2778×1284 | 10 |
| iPhone 6.5" | Acceptable alt | 1242×2688 / 2688×1242 | 10 |
| iPad 13"/12.9" | Required **iff** app supports iPad | 2064×2752 / 2752×2064, 2048×2732 / 2732×2048 | 10 |
| Apple Watch | Required **iff** app has a watchOS target | per watch series | 10 |

App Store Connect derives some smaller sizes from a larger uploaded set, so the
skill's default is to capture the largest required size per family and let the
store fill in the rest, unless the user wants explicit per-size captures.
**Apple changes which sizes are required/derived fairly often** — treat the
exact rules above as a snapshot and re-verify against current App Store Connect
docs at runtime (see §11). The trend is toward *fewer* mandatory sizes (App Store
Connect has been moving to requiring only the largest **6.9" iPhone** and **13"
iPad** and deriving the rest), so this table likely already needs narrowing on a
real run — which is exactly why §11 verifies against live docs rather than
hard-coding.

**Metadata fields (per locale):** name (30), subtitle (30), promotional text
(170), description (4000), keywords (100), support URL, marketing URL,
copyright. Plus app-level: category, content rating, privacy policy URL.

### 7.2 Google Play (current as of research date — re-verify at runtime)

| Asset | Required? | Spec |
|---|---|---|
| Phone screenshots | Yes (min 2) | 2–8 images, JPEG or 24-bit PNG (no alpha), 320–3840px/side, max aspect 2:1; 1080×1920 recommended |
| 7" tablet screenshots | If targeting tablets | 2–8, same format rules |
| 10" tablet screenshots | If targeting tablets | 2–8, same format rules |
| Wear OS screenshots | If Wear OS app | up to 8 |
| **Feature graphic** | **Yes, to publish** | exactly 1024×500, JPEG/24-bit PNG (no alpha) |
| App icon | Yes | 512×512, 32-bit PNG |

**Metadata fields (per locale):** title (30), short description (80), full
description (4000). Plus app-level: category, content rating, privacy policy,
contact details.

> **Note:** the **feature graphic** is not a screenshot and cannot be produced
> by capturing the app. v1 will *detect that it is required and missing*, and
> generate a simple app-icon-on-gradient placeholder via ImageMagick, falling
> back to prompting the user to supply one if ImageMagick is absent — see §12-D.

---

## 8. Feature Discovery, Curation & State Acquisition (the hard part)

A store screenshot must show a meaningful, populated screen *that the user
actually wants on the store*. So the skill first discovers what the app contains
and lets the user curate it (the **Discover** step), then reaches each chosen
state through a single cross-stack driver — **Maestro** — with a manual fallback
(the **Drive** step).

### 8.1 Discover — build the candidate inventory (static, before building)

Before spending time on dependency install and builds, the skill enumerates the
app's screens/features from **static repo signals**, so it can present a list and
get the user's commitment cheaply:

| Stack | Discovery signals |
|---|---|
| React Native / Expo | React Navigation route configs, screen components, registered deep links |
| Flutter | route tables / `Navigator` destinations, named routes |
| Native iOS | storyboard scenes, SwiftUI view structs, tab-bar items, URL schemes |
| Native Android | nav-graph XML, activity/fragment declarations, intent filters |

This produces a **candidate feature inventory** — runtime confirmation comes
later (§8.4) once the app is actually running.

### 8.2 Curate — the user selection interaction

The skill presents the inventory and the user **curates** it, e.g.:

> "I found these screens/features: Home, Library, Reader, Settings, Onboarding,
> Paywall. Which should appear in the store, and in what order?"

Curation captures four things per chosen screen:

1. **Select** — include in the store set or not.
2. **Order** — sequence on the listing (the first screenshot matters most).
3. **Name** — the marketing caption / intent, which differs from the in-app
   screen name.
4. **Desired state** — *how it should look*: "Library, populated with books, not
   empty"; "Reader, mid-chapter"; "Paywall, annual plan selected". This feeds the
   seed/mock-data needs in §8.4.

### 8.3 Why Maestro is the driver

Maestro is the only UI-automation tool that is **both cross-stack and
cross-platform**: one YAML flow language drives native iOS, native Android,
Flutter, and React Native / Expo, on both simulators and emulators, by
interacting with the live accessibility hierarchy. This is a categorical
difference from Detox / XCUITest / Espresso / Flutter `integration_test`, which
are each locked to one stack and/or one OS. Standardizing on Maestro means:

- The per-stack modules shrink to *build + launch + boot the right device*;
  **drive becomes a shared core capability**, not four separate implementations.
- A Maestro flow file *is* the persisted, rerunnable navigation recipe (see
  §12-F), produced as an *output* of interactive discovery.
- `maestro studio` provides interactive inspection of the view hierarchy to
  build those flows during discovery.

**Flutter caveat:** Maestro drives Flutter through the **semantics tree**, which
must be populated for tap-by-label to work. Apps that render custom-painted /
canvas UIs without semantics expose little for Maestro to target and fall through
to manual-assist (§8.4) — the same limitation called out there for games/canvas
screens.

Maestro is **gated on the Drive step**, not the whole skill: Detect, Plan,
metadata collection, and Validate all run without it. The skill prompts to
install Maestro (and its JDK dependency) only when the pipeline first needs to
drive the app.

### 8.4 Reaching the curated states (the Drive step)

For each screen the user kept in §8.2:

1. **Runtime confirmation** — once the app is running, `maestro studio` / a UI
   snapshot confirms the screen actually exists and reconciles it against the
   static inventory.
2. **Author a Maestro flow per screen**, preferring the most direct route
   available: deep links / URL schemes if the app registers them, otherwise
   tap-by-accessibility-label navigation.
3. **Seed / mock data / Auth** — to hit the *desired state* from §8.2:
   - **Detect Auth/Demo flags:** If the app has a "demo mode" or accepts a mock
     data JSON, the skill asks to enable it.
   - **Bypass Social Login:** Since social logins (Google/Apple) often fail on
     simulators, the skill prioritizes mock-auth or bypass routes where detected.
4. **Pre-emptive Permission Handling** — before driving, the skill uses SDK
   tooling (`simctl privacy grant` / `adb shell pm grant`) to grant as many
   requested permissions as the tooling allows (Location, Photos, Contacts,
   Calendar, Reminders, Microphone) so Maestro flows aren't interrupted by system
   dialogs. **Caveat:** not every permission is grantable this way — **camera and
   App Tracking Transparency are notably unreliable/unsupported via `simctl
   privacy`**, and some grants require the app not to be running. Where a dialog
   can't be pre-granted, the skill falls back to dismissing it inside the Maestro
   flow, then to manual-assist.
5. **Manual-assist fallback** — when Maestro can't reach a state (canvas/game
   UIs, missing semantics, unscriptable auth), the skill instructs the user to
   navigate manually and signals when to capture.
   - **Headless Contexts:** If running via `--non-interactive`, this step is
     skipped, and the screen is marked as "Missing" in the final report.

> **Deferred to a future version:** reusing *existing* Detox / XCUITest /
> Espresso / `integration_test` flows. Adapting to each per-stack framework
> multiplies the hardest part of the build for marginal v1 benefit; Maestro as
> the sole driver keeps v1 tractable.

---

## 9. Metadata Layout (fastlane-compatible)

The skill writes to fastlane's `deliver` (iOS) and `supply` (Android) trees so
existing tooling can publish without translation. (The *root* of this tree —
`fastlane/` vs. a neutral `store/` dir — is still open; see §12-H. The layout
below is the same either way.)

**iOS (`fastlane/metadata/`):**
```
fastlane/metadata/
  copyright.txt
  primary_category.txt
  <locale>/                     # e.g. en-US
    name.txt  subtitle.txt  promotional_text.txt
    description.txt  keywords.txt
    marketing_url.txt  support_url.txt  privacy_url.txt
    release_notes.txt
fastlane/screenshots/<locale>/  # iPhone/iPad/Watch PNGs
```

**Android (`fastlane/metadata/android/`):**
```
fastlane/metadata/android/
  <locale>/                     # e.g. en-US
    title.txt  short_description.txt  full_description.txt
    images/
      icon/             featureGraphic/
      phoneScreenshots/ sevenInchScreenshots/ tenInchScreenshots/  wearScreenshots/
```

Because iOS and Android use *different* trees for the same data, the skill keeps
a single internal notion of "the listing" and writes both layouts from it. (The
community `universal_metadata` fastlane plugin is prior art for this mapping and
a reference, not a dependency.)

**Screenshot ordering:** both `deliver` and `supply` derive on-store display
order from the **filename sort order**, so the skill encodes the curated order
from §8.2 as a numeric filename prefix (e.g. `01_home.png`, `02_library.png`).
This is what makes "the first screenshot matters most" (§8.2) actually hold on
the store.

### 9.1 Secrets boundary (committed tree is the source of truth — for *non-secrets*)

The core premise is "commit the listing to the repo," which directly collides
with the auth/seed credentials the Drive step needs. The boundary is explicit:

- **Committed (`fastlane/`):** copy, keywords, URLs, copyright, screenshots,
  generated graphics — everything that *is* the public listing.
- **Never committed:** login credentials, API tokens, seed-data secrets, mock
  auth tokens. These live in a git-ignored local file (e.g.
  `.listing-kit/secrets.local`, added to `.gitignore` by the skill if absent) or
  environment variables, and are referenced — not inlined — by Maestro flows.
- **Assemble asserts the boundary:** before finishing, the skill scans the
  written `fastlane/` tree for high-entropy strings / known secret patterns and
  fails the run if any credential leaked into a committed file.

---

## 10. Cross-AI Portability

The skill must run under Claude Code, Codex, Copilot CLI, Kiro, and Gemini CLI.
Portability has two layers: the **content** runs the same everywhere (§10.1), and
the **package** installs natively in each tool (§10.2).

### 10.1 Content portability

- **Core logic is plain markdown + shell**, with no Claude-only tool
  assumptions in the instructions.
- A `references/platforms/tool-mapping.md` documents tool-name equivalents
  (e.g. Read/Edit/Bash) per platform, following the superpowers convention.
- Any helper that genuinely needs code lives in `scripts/` as a portable shell
  (or Node/Python if already present) script the agent can invoke, rather than
  relying on a platform-specific tool.
- **Capture** uses **standard SDK tooling** (`xcrun simctl`, `adb`, `flutter`,
  Expo/RN CLI) that any agent can shell out to — not an agent-specific
  browser/MCP capability. `simctl`/`adb` are preferred over Maestro's own
  `takeScreenshot` because they give clean full-resolution output and status-bar
  override (9:41 / full battery & signal) on iOS.
- **Drive** uses **Maestro** (`maestro test <flow>.yaml`), also a plain
  shell-out, so it stays agent-portable. It does raise the install floor — it
  requires Maestro and a JDK — so it is **gated on the Drive step**, prompted for
  only when first needed (see §8.3), never at skill startup.
- The **manual-assist fallback is interactive-only** by design. In headless /
  scheduled agent contexts it cannot run; such contexts depend on persisted
  Maestro flows (§12-F) and degrade gracefully (report the un-capturable screens
  rather than block).

### 10.2 Distribution & packaging (generator-driven)

A single canonical `SKILL.md` + `references/` + `scripts/` is the **source of
truth**. As of research date, markdown `SKILL.md` skills are a near-universal
primitive — Claude Code, Copilot CLI, and Codex all read them directly — so the
remaining work is *thin per-platform manifests*, not separate implementations.

**A generator script (`scripts/package/`) produces every platform manifest from
the canonical skill**, so they never drift:

| Platform | Install mechanism | Generated artifact(s) |
|---|---|---|
| Claude Code | `/plugin install` from git marketplace | `.claude-plugin/marketplace.json` + `plugin.json`; skill at `skills/listing-kit/SKILL.md` |
| Copilot CLI | `/plugin install owner/repo` | same `plugin.json`; also discoverable via `.agents/skills` / `.claude/skills` |
| Codex | clone + `~/.codex/config.toml` | `AGENTS.md` entry pointing at the skill; config.toml only if MCP shipped |
| Gemini CLI | `gemini extensions install <url>` | `gemini-extension.json` with `contextFileName` → skill markdown |
| Kiro | steering/specs (least standardized) | steering-doc wrapper pointing at the skill |
| *(optional)* MCP | any tool that supports MCP | thin server exposing `scripts/` helpers as tools |

**MCP is an optional adapter, not the spine.** The architecture is "agent reads
markdown and shells out to `simctl`/`maestro`/`adb` with its own tools" (§10.1);
an MCP wrapper would invert that (the server becomes the executor). Ship MCP only
for tools that genuinely can't read repo files.

The package is installed **once into the developer's agent environment** (user
scope), then pointed at any mobile app repo — it is not installed per-app-repo.

> **Open sub-decision:** Kiro is the one platform without a confirmed
> plugin/skill installer (it uses steering docs + specs + MCP). Treat its
> wrapper as best-effort, and re-verify at build time. See risk in §14.

---

## 11. Validation & Reporting

After assembly the skill produces a **report** listing, per platform/locale:
- Which assets exist vs. are required vs. are missing.
- Any character-limit overflows in copy fields.
- Any dimension/format/aspect violations in images.
- Next actions (e.g. "Feature graphic missing — required to publish on Play").

Validation rules come from the `references/stores/*.md` docs so they update in
one place. The skill should note at runtime that store specs change and prefer
verifying against current store documentation when uncertain.

---

## 12. Resolved Decisions & Future Considerations

- **A. Name.** ✅ **Resolved: `listing-kit`.**
- **B. Screenshot count strategy.** ✅ **Resolved:** Default to **5 hero screens** per device class, user-customizable.
- **C. Localization in v1.** ✅ **Resolved:** Single locale (`en-US`) only, with multi-locale as a stretch.
- **D. Feature graphic.** ✅ **Resolved:** Auto-generate a simple placeholder (icon on brand gradient) to satisfy Play Store requirements. **Rendered via ImageMagick** (`magick`/`convert`) as the portable, scriptable generator — it composites the app icon onto a gradient and writes a 1024×500, 24-bit, no-alpha PNG. ImageMagick is listed as an **optional** Doctor dependency (§5.1): if absent, the skill degrades to **prompting the user to supply** the feature graphic rather than blocking. (`sips` on macOS can resize but not composite gradients, so it is not a substitute.)
- **E. Device frames / captions.** ✅ **Resolved:** Out of scope for v1.
- **F. Repeatability.** ✅ **Resolved:** Maestro flows are the rerunnable recipes.
- **G. Watch/Wear depth.** ✅ **Resolved:** Detect-and-prompt only in v1.
- **H. Metadata tree location.** ✅ **Resolved:** Default to **`fastlane/`** root.
- **I. Desired state expression.** ✅ **Resolved:** Use **Free Text**; AI reasons about the UI hierarchy to reach the state.
- **J. Kiro support.** ✅ **Resolved:** Best-effort steering wrapper (re-verify installer at build time; see §14).
- **K. Generator scope.** ✅ **Resolved:** Emit-only in v1.

### 12.1 Key Feature Improvements (Added in Review)

- **Listing Doctor:** A pre-flight check to verify toolchains (Java, CocoaPods, SDKs) before any build work starts.
- **Status Bar Sanitization:** Automatic cleaning of status bars (9:41 AM, Full Battery/Signal) for all captures.
- **Visual Diffing:** When rerunning the skill, provide a visual diff report if previous screenshots exist to catch regressions.
- **AI-Suggested Captions:** The skill will propose marketing captions for each screen based on component analysis during Discovery.
- **Permission Pre-granting:** Automatically grant app permissions (Location, etc.) via CLI before launch to prevent dialogs from breaking flows.

---

## 13. Out of Scope (v1)

- Uploading/publishing to App Store Connect or Play Console.
- Generating marketing copy *content* with AI (the skill collects/stores copy
  and enforces limits; it does not write your marketing for you in v1).
- App preview videos.
- A/B testing of store listings.
- Non-mobile targets (web, desktop, TV).

---

## 14. Risks

- **State acquisition & Auth** is the dominant *automation* risk; social logins and complex auth flows can block navigation. Mitigated by detecting demo/mock modes and prioritizing bypass routes.
- **Permission Dialogs** — system dialogs (Location, Camera) can interrupt Maestro flows. Mitigated by pre-granting permissions via CLI before launch, but **`simctl privacy` does not cover every permission (camera, ATT)**; residual dialogs are dismissed in-flow or via manual-assist (§8.4).
- **Secret leakage into the repo** — the "commit the listing" premise risks committing auth/seed credentials. Mitigated by the §9.1 secrets boundary (git-ignored local store) and an Assemble-time leak scan that fails the run.
- **Feature-graphic generator dependency** — auto-generation needs ImageMagick, which isn't universally installed. Mitigated by treating it as optional in Doctor and degrading to a user prompt (§12-D).
- **Environment Drift** — building mobile apps is notoriously fragile. Mitigated by the **Listing Doctor** pre-flight check to fail fast and provide clear fix instructions.
- **Maestro install floor** — Maestro + JDK is a real third-party dependency;
  mitigated by gating it on the Drive step so metadata-only runs need nothing
  extra.
- **Store spec drift** — sizes and limits change; mitigated by centralizing them
  in reference docs and re-verifying at runtime.
- **Stack breadth vs. depth** — "all stacks" risks shallowness; mitigated by the
  module architecture *and* by Maestro collapsing four drive implementations into
  one, so per-stack modules only carry build/launch/capture.
- **Cross-AI tool differences** — mitigated by keeping core logic to markdown +
  standard shell tooling (Maestro and the SDK tools are all plain shell-outs).
- **Packaging drift across fast-moving tools** — five tools' plugin/extension
  formats evolve independently (Kiro has no confirmed installer at all);
  mitigated by generating every manifest from one canonical `SKILL.md` (§10.2) so
  a format change is a one-line generator edit, and by leaning on the shared
  markdown-skill primitive that CC / Copilot / Codex already agree on.
