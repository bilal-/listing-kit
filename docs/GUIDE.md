# listing-kit — User Guide

This guide walks through a real run, end to end. For *why* it's built this way,
see the [design spec](superpowers/specs/2026-05-25-listing-kit-design.md). For
the operational instructions the agent follows, see
[`skills/listing-kit/SKILL.md`](../skills/listing-kit/SKILL.md).

---

## 1. Install

Pick your agent (see the [README Install section](../README.md#install)). For
Claude Code:

```sh
/plugin marketplace add bilal-/listing-kit
/plugin install listing-kit@listing-kit
```

The skill installs **once** into your agent environment, then points at any
mobile repo — it is not installed per app-repo.

## 2. Kick it off

From inside your mobile app's repo, ask the agent something like:

> *"Use listing-kit to prepare App Store and Google Play screenshots and metadata for this app."*

The agent runs the pipeline:

```
detect → doctor → discover → plan → configure → run → drive → capture → validate → assemble
```

## 3. What happens at each step

### Detect & Doctor
The agent classifies your stack (iOS / Android / Flutter / RN-Expo) and confirms
targets with you. Then **Doctor** checks your toolchain *before* any build and
reports anything missing with fix instructions. Optional tools (Maestro,
ImageMagick) are noted but not required yet.

### Discover & Curate — *your* main decision point
The agent enumerates your screens from static repo signals (routes, storyboards,
nav graphs, deep links) and shows you a list **before** building anything. You
then decide, per screen:

| | |
|---|---|
| **Select** | Is it on the store? |
| **Order** | Sequence — the first screenshot matters most |
| **Name** | The marketing caption (the agent can propose one) |
| **Desired state** | Free text: *"Library, populated with books, not empty"* |

### Plan
Confirm stores, device classes (the agent pre-selects from repo hints like iPad
support or a Wear module), and locale (`en-US` default). Default is **5 hero
screens** per device class.

### Configure — secrets stay out of the repo
If your app has a **demo mode** or accepts **mock data**, the agent uses it to
populate screens. Any credentials needed go in a git-ignored
`.listing-kit/secrets.local` or environment variables — **never** in committed
files.

### Run
The agent builds and launches on the right simulator/emulator, sanitizes the
status bar to **9:41 / full battery & signal**, and pre-grants permissions so
dialogs don't interrupt automation.

> On iOS, camera and App Tracking Transparency can't be pre-granted — if a screen
> needs them, the agent dismisses the dialog in-flow or asks you to.

### Drive
Now Maestro is installed (prompted here, not earlier). For each curated screen
the agent writes a Maestro flow — preferring deep links, else tapping by
accessibility label — and reaches your desired state. **Each flow is saved** as a
rerunnable recipe under `.listing-kit/flows/`.

If a screen can't be automated (canvas/game UI, missing semantics, unscriptable
auth), the agent asks you to navigate there manually and signals when to capture.

### Capture
Screenshots are taken with clean SDK tooling (`simctl io ... screenshot`,
`adb exec-out screencap`) at every required dimension, with the sanitized status
bar intact.

### Validate & Assemble
Every asset and field is checked against current store rules (character limits,
dimensions, missing required assets like the Play **feature graphic**, which the
agent generates as an icon-on-gradient placeholder). Everything is written into
the fastlane layout, ordered by numeric filename prefix. Finally, a **secret
scan** runs over the committed tree and **fails the run** if anything leaked.

You get a **report**: per store/locale, what exists vs. required vs. missing,
with next actions.

## 4. The output

```
fastlane/
  metadata/                 # iOS copy (name, subtitle, description, keywords, URLs…)
    android/                # Android copy + images/ (screenshots, featureGraphic, icon)
  screenshots/<locale>/     # iOS screenshots, ordered 01_, 02_, …
listing-review.html         # open in a browser: copy buttons, screenshots, validation
.listing-kit/               # git-ignored: flows + secrets (NOT committed)
```

Commit `fastlane/`. Review the copy like code. Re-run any time the app changes —
the saved Maestro flows make it repeatable.

## 5. Re-running & CI

Because flows are persisted, later runs replay them. For CI, run with
`--non-interactive`: it skips manual-assist and prompts, reports missing assets
instead of hanging, and relies on the flows captured in a prior interactive run.

## 6. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Doctor fails on iOS | Run `xcode-select --install`; `pod install` if a Podfile exists |
| Maestro can't find a screen | Add accessibility labels; for Flutter, add `Semantics`/`semanticLabel` |
| Permission dialog blocks a flow | Camera/ATT can't be pre-granted on iOS — handled in-flow or manually |
| Feature graphic step skipped | Install ImageMagick (`brew install imagemagick`) or supply a 1024×500 PNG |
| Secret scan failed the run | A credential reached the listing tree — move it to `.listing-kit/secrets.local` |

## 7. Going further

- **Add a stack or store**: write a module in `skills/listing-kit/references/` —
  see [CONTRIBUTING.md](../CONTRIBUTING.md).
- **Publish**: out of scope for v1, but the fastlane layout means
  `fastlane deliver` / `supply` can publish what listing-kit produced.
