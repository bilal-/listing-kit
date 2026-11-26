---
name: listing-kit
description: Use when the user wants App Store or Google Play listing assets for a mobile app, including screenshots, store copy, fastlane metadata or a feature graphic. Triggers on "store screenshots", "app store listing", "play store assets", "prepare my app submission", "fastlane metadata", or a request to prepare a listing from an iOS, Android, Flutter or React Native repo. Keep the listing in git with the app.
---

# Prepare a store listing

Identify the stack from the app manifest and work from the mobile app root. In a monorepo, confirm which app the user wants. Run the skill's `bin/listing-kit` launcher there. Commands below assume it is on PATH.

## Before editing

- Keep public listing content in git with the code. Read existing copy, plans, flows and assets first. Ask before rewriting committed content, including screenshots. Keep the user's wording and make the smallest approved change. Preserve the release version.
- Never fabricate metadata. Ask for missing URLs, copyright, category and other facts. If the user is unavailable, leave missing files unwritten and report the gaps.
- Use the user's voice. Write short captions and concrete sentences about what the screen shows. Avoid promotional filler and dash clauses.
- Keep secrets out of the repo and flows. Use demo data. For store credentials, only help the user configure the PATH to a private file outside the repo. Never ask for, read or print its contents.
- Use the kit's [store rules](specs/stores.json) by default. When a live store page disagrees, record the difference and its source URL in `.listing-kit/specs.override.json` and tell the user.

## First run and reruns

1. Run `listing-kit doctor` to check tools and `listing-kit detect` to see platform support and its evidence. Detection decides defaults. The plan's `platforms` flags override detection. If a relevant fact is unknown, ask the user.
2. Discover screens from routes, views, storyboards or navigation graphs. Have the user choose the order, caption, detail and populated state for each. Confirm stores, app IDs, locales, devices and scope before building or installing dependencies.
3. Write `.listing-kit/listing.json` in [format 2](references/plan-file.md). Select targets by slot ID and size from the rules. Record deferrals with a reason. Set screen IDs, localized copy, flow paths, style, graphics and any platform overrides. Set `trees` for split fastlane folders. Run `listing-kit plan check` and resolve errors. For an existing store listing and an empty local tree, agree on a first pull before drafting text.
4. Build and install the app on the chosen simulator or emulator. Follow the stack instructions for [iOS](references/stacks/ios-native.md), [Android](references/stacks/android-native.md), [Flutter](references/stacks/flutter.md) or [React Native and Expo](references/stacks/react-native-expo.md). Write one [Maestro flow](references/driving/maestro.md) per capture screen. Launch into the planned state and assert on visible content. A panel needs no flow.
5. Run `listing-kit capture`. It drives the installed app, cleans the status bar and saves checked PNGs under `.listing-kit/raw/`. For a screen that needs manual navigation, select it with `listing-kit capture --manual --target ID --screen ID`. Skip manual jobs in unattended runs and report them.
6. Choose framed phone shots by default when writing the plan. Set `style.mode` to `framed` with background colors, ink, and fonts for both headline and detail. Use the band template on Play tablets and Chromebook, and override the mode to `raw` where framing is forbidden. An omitted mode means raw. Inspect `listing-kit compose --preview`, then run `listing-kit compose`. It refuses to overwrite files it did not write or that someone edited. Only use `listing-kit compose --adopt` with permission to replace the listed conflicts. A style-only change to existing images needs approval and `listing-kit compose --restyle`.
7. Write approved UTF-8 copy in the [fastlane text files](references/metadata/fastlane-layout.md). Run `listing-kit validate` on the listing. For a planned Apple submission, use `listing-kit validate --as-of YYYY-MM-DD --ios-sdk X.Y` with the actual date and build SDK. Fix failures and report warnings and missing inputs. Run `listing-kit review` and inspect `listing-review.html`. In a Git worktree run `listing-kit hook install` to refresh the page from staged listing inputs at commit time.
8. For upload by hand, run `listing-kit handoff --open`. For store sync, use `listing-kit fastlane setup` to check access by path, then `listing-kit pull` to compare and import store text. Review conflicts with the user. Run `listing-kit publish` to see the change summary and proposed fastlane command. In this version it does not upload. Each store stays gated until its live test passes. See the [handoff and split-tree limits](references/metadata/fastlane-layout.md#store-management).
