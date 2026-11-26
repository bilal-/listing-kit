# listing-kit

Keep your App Store and Google Play listing in git with the app. Review copy and screenshots in pull requests, see what changed between releases, and roll back a bad edit. An agent can work on the same files as your team.

<a href="CHANGELOG.md"><img alt="Version: 0.5.0" src="https://img.shields.io/badge/version-0.5.0-blue"></a>

Turn a running app into ordered store screenshots, graphics, fastlane text files and a review page you can open in a browser.

## Install

| Agent | Commands |
| --- | --- |
| Claude Code[^install] | `/plugin marketplace add bilal-/listing-kit` then `/plugin install listing-kit@listing-kit` |
| Codex[^install] | `codex plugin marketplace add bilal-/listing-kit` then `codex plugin add listing-kit@listing-kit` |
| Copilot CLI[^install] | `copilot plugin marketplace add bilal-/listing-kit` then `copilot plugin install listing-kit@listing-kit` |
| Gemini CLI[^install] | `gemini extensions install https://github.com/bilal-/listing-kit` |
| Universal skill installer[^install] | `npx skills add bilal-/listing-kit` |

[^install]: not yet verified from a clean install

For shell access from a checkout, run `skills/listing-kit/bin/listing-kit link` and follow its PATH hint. See [install and launcher setup](docs/INSTALL.md).

## Quick start

Open the app's directory with your agent and ask **“Prepare my store listing.”** Pick the screens, order, copy and devices before the build. The agent writes the plan and Maestro flows and helps build and install the app.

Once the plan and app are ready, these six commands take you from preflight to hand upload:

```sh
listing-kit doctor
listing-kit capture
listing-kit compose
listing-kit validate
listing-kit review
listing-kit handoff --open
```

The review page is `listing-review.html`. The hand-upload instructions are in `.listing-kit/upload/INDEX.html`. Try the [first run with Recipe Box](docs/GUIDE.md).

## What runs locally

The kit supports native iOS, native Android, Flutter and React Native (including Expo). Capture needs an installed app and a matching iOS simulator or running Android emulator. Maestro navigates and checks the screen. Compose turns captures into store images. You choose the screens, supply real listing details and approve changes to existing content.

Fastlane setup checks store access. Pull imports listing text and keeps remote screenshot references. **Publishing is preview-only in this version.** The publish command prints the summary and proposed command. Upload by hand until the store's live test passes. Build distribution has a separate [release guide](docs/RELEASES.md).

| Requirement | When you need it |
| --- | --- |
| Bash and Python 3.8+ | Run the kit commands. |
| App build tools | Use Xcode for iOS or the Android SDK and a JDK for Android. Flutter and React Native also need the app's own toolchain. |
| Simulator or emulator tools | Capture uses xcrun simctl on macOS or adb on Android. |
| Maestro and its JDK | Replay the saved navigation flows. Manual capture waits for you to navigate. |
| ImageMagick | Normalize captures and write store images. Validation can do structural image checks without it. |
| Chrome, Chromium, Edge or Brave | Render framed shots, panels and template graphics. |
| Git | Review history and install the staged review hook. |
| Ruby and fastlane | Check store access, pull and preview a publish. |

## Documentation

- [First run](docs/GUIDE.md) and [troubleshooting](docs/TROUBLESHOOTING.md)
- [Plan format](skills/listing-kit/references/plan-file.md) and [listing layout](skills/listing-kit/references/metadata/fastlane-layout.md)
- [Architecture](docs/ARCHITECTURE.md), [CI](docs/CI.md) and [store credentials](docs/CREDENTIALS.md)
- [Examples](examples/README.md), [contributing](CONTRIBUTING.md), [changelog](CHANGELOG.md) and [MIT license](LICENSE)
