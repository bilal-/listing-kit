<h1 align="center">listing-kit</h1>

<p align="center">
  <strong>App-store presence, in your repo.</strong><br>
  A free, open-source, cross-AI skill that walks any mobile-app repository,
  learns how to run it, captures store-compliant screenshots, and assembles the
  full App&nbsp;Store&nbsp;+&nbsp;Google&nbsp;Play listing — copy, metadata, and
  graphics — stored <em>in the repo</em> as the source of truth.
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-blue.svg"></a>
  <a href="https://github.com/bilal-/listing-kit/actions/workflows/tests.yml"><img alt="Tests" src="https://github.com/bilal-/listing-kit/actions/workflows/tests.yml/badge.svg"></a>
  <img alt="Status: v0.1 (in development)" src="https://img.shields.io/badge/status-v0.1%20(in%20dev)-orange">
  <img alt="Stacks: iOS · Android · Flutter · RN/Expo" src="https://img.shields.io/badge/stacks-iOS%20%C2%B7%20Android%20%C2%B7%20Flutter%20%C2%B7%20RN%2FExpo-success">
</p>

---

## Why

Shipping a mobile app means hand-producing a pile of store assets: correctly
sized screenshots for several device classes, marketing copy under strict
character limits, URLs, copyright, platform graphics. It's tedious, error-prone,
and repeated on every release — and it's scattered across simulators, cropping
tools, spreadsheets, and the store consoles. There's **no single source of truth
that lives with the code.**

listing-kit makes the repo that source of truth. Store copy gets reviewed like
code (PRs, diffs, history). Screenshots become **regenerable**, not hand-curated
one-offs. And because everything is written in the **fastlane** convention,
existing publishing tooling can pick it up with zero translation.

> **This is not "a screenshot tool."** Screenshots are one artifact among
> several. The unit of value is a complete, version-controlled listing that
> stays in sync with the running app.

## What it does

Point your agent at a mobile repo and listing-kit will:

1. **Detect** the stack — native iOS, native Android, Flutter, or React Native / Expo.
2. **Doctor** the environment — verify SDKs/toolchains before any build, fail fast with fixes.
3. **Discover & curate** — enumerate your screens from static signals, then *you* pick, order, name, and describe the desired state of each.
4. **Run** the app on the right simulator/emulator, with **sanitized status bars** (9:41, full battery/signal) and **pre-granted permissions**.
5. **Drive** to each curated state via **Maestro** (one driver for every stack/platform), with a manual-assist fallback.
6. **Capture** screenshots at every store-required dimension using clean SDK tooling (`simctl`/`adb`).
7. **Assemble** copy, keywords, URLs, copyright, and a generated Play **feature graphic** into the fastlane layout — then **scan to guarantee no secret was committed**.
8. **Validate & report** every asset/field against current store rules.

**Out of scope (v1):** actually publishing to the stores, writing your marketing
copy *content* for you, app preview videos, A/B testing, non-mobile targets.

## Supported

| Stacks | Stores | AI platforms |
|---|---|---|
| Native iOS, Native Android, Flutter, React Native / Expo | Apple App Store, Google Play | Claude Code, Codex, Copilot CLI, Gemini CLI, Kiro* |

<sub>*Kiro support is best-effort (steering-doc wrapper).</sub>

## Install

### Claude Code
```sh
/plugin marketplace add bilal-/listing-kit
/plugin install listing-kit@listing-kit
```
Then just ask: *"Use listing-kit to prepare App Store and Play screenshots for this app."*

### Other AI platforms
A single canonical `SKILL.md` is the source of truth; per-platform manifests are
generated from it so they never drift (`gemini-extension.json`, `AGENTS.md`).

| Platform | How |
|---|---|
| **Codex / Copilot CLI** | Clone the repo; the agent reads [`AGENTS.md`](AGENTS.md) → `skills/listing-kit/SKILL.md`. |
| **Gemini CLI** | `gemini extensions install https://github.com/bilal-/listing-kit` (uses [`gemini-extension.json`](gemini-extension.json)). |
| **Any** | Load `skills/listing-kit/SKILL.md` as context. All work is plain shell-outs — see [`tool-mapping.md`](skills/listing-kit/references/platforms/tool-mapping.md). |

Regenerate the non-Claude manifests after editing the skill:
```sh
bash skills/listing-kit/scripts/package/generate-manifests.sh
```

## Requirements

listing-kit gates heavy dependencies so you only install what a given run needs:

| Tool | When needed | If missing |
|---|---|---|
| Stack SDK (Xcode+CocoaPods / JDK+Android SDK / Flutter / Node) | Build & run | Doctor fails fast with fix instructions |
| `xcrun simctl` / `adb` | Run, sanitize, capture | required for that platform |
| **Maestro + JDK** | Drive step only | falls back to manual-assist |
| **ImageMagick** | Feature-graphic generation only | falls back to prompting you for one |

## How it works

```
detect → doctor → discover → plan → configure → run → drive → capture → validate → assemble
```

The skill is a **shared orchestration core** plus **pluggable modules**: the core
never holds stack- or store-specific commands; those live in
[`references/`](skills/listing-kit/references) modules the core dispatches to.
**Driving is shared** — Maestro is the only UI driver that's both cross-stack and
cross-platform, which collapses four per-stack automation implementations into
one. New stacks or stores are added by writing a module, not editing the core.

Full walkthrough: **[docs/GUIDE.md](docs/GUIDE.md)**. Design rationale:
**[docs/superpowers/specs/2026-05-25-listing-kit-design.md](docs/superpowers/specs/2026-05-25-listing-kit-design.md)**.

## Your repo stays clean

The committed tree is the source of truth **for non-secrets only**. Listing copy,
screenshots, and graphics get committed; **credentials and seed secrets never
do** — they live in a git-ignored `.listing-kit/` or environment variables, and
the Assemble step runs a secret scan that **fails the run** if anything leaked.

## Contributing

Contributions are very welcome — especially deepening a stack module or keeping a
store's specs current. See **[CONTRIBUTING.md](CONTRIBUTING.md)** and our
**[Code of Conduct](CODE_OF_CONDUCT.md)**. Good first issues: add detection
signals for a framework, fix a drifted store size, or improve a Maestro flow
recipe.

## Support

listing-kit is free and MIT-licensed. If it saved you a tedious afternoon, you
can say thanks: **[buymeacoffee.com/bilaldev](https://buymeacoffee.com/bilaldev)** ☕

## License

[MIT](LICENSE) © Bilal Ahmad and listing-kit contributors.
