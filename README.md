# listing-kit

Keep your App Store and Google Play listing in git with the app. Review copy and screenshots in pull requests, see what changed between releases, and roll back a bad edit. An agent can work on the same files as your team.

<a href="CHANGELOG.md"><img alt="Version: 0.5.0" src="https://img.shields.io/badge/version-0.5.0-blue"></a>

Turn a running app into ordered store screenshots, graphics, fastlane text files and a review page you can open in a browser.

## Install

| Agent | Install commands (clean installs unverified) |
| --- | --- |
| Claude Code | `/plugin marketplace add bilal-/listing-kit` then `/plugin install listing-kit@listing-kit` |
| Codex | `codex plugin marketplace add bilal-/listing-kit` then `codex plugin add listing-kit@listing-kit` |
| Copilot CLI | `copilot plugin marketplace add bilal-/listing-kit` then `copilot plugin install listing-kit@listing-kit` |
| Gemini CLI | `gemini extensions install https://github.com/bilal-/listing-kit` |
| Universal skill installer | `npx skills add bilal-/listing-kit` |

Installing the skill does not put the launcher on PATH. Ask the agent to run `bin/listing-kit link` from the installed skill directory. From a checkout, run `skills/listing-kit/bin/listing-kit link`. Follow the printed PATH hint in your shell. [Launcher setup](docs/INSTALL.md)

## Quick start

Open the app's directory with your agent and ask **“Prepare my store listing.”** Run `listing-kit detect` there and use the Apple and Play paths it prints for copy, screenshots and graphics. Pick the screens, order, copy and devices before the build. The agent writes the plan and Maestro flows and helps build and install the app.

These commands are in the [Unreleased changelog](CHANGELOG.md#unreleased). Use a checkout or plugin revision that contains the launcher. Install the app on a matching iOS simulator on a Mac or on a running Android emulator. Automated capture needs Maestro and its JDK. Install ImageMagick and a supported browser for framed shots.

With the plan and app ready, run these commands from the app directory.

```sh
listing-kit doctor
listing-kit capture
listing-kit compose
listing-kit validate
listing-kit review
listing-kit handoff --open
```

Open `listing-review.html` to check the finished listing. Handoff opens `.listing-kit/upload/INDEX.html`. Follow the index to paste the text and upload each image yourself in App Store Connect or Play Console. [First run with Recipe Box](docs/GUIDE.md)

## What runs locally

The kit supports native iOS, native Android, Flutter and React Native (including Expo). Capture needs an installed app and a matching iOS simulator or running Android emulator. Maestro navigates and checks the screen. Compose turns captures into store images. You choose the screens, supply real listing details and approve changes to existing content.

Fastlane setup checks store access. Pull imports listing text and keeps remote screenshot references. **Publishing is preview-only by default.** The publish command prints the summary and proposed command. Upload by hand until the store's live test passes. Build distribution has a separate [release guide](docs/RELEASES.md).

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
