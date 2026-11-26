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
- Use seeded demo data. If a flow needs a login, have the user export a `MAESTRO_` variable from their environment or git-ignored `.listing-kit/secrets.local`. Reference it in the flow as `${MAESTRO_DEMO_PASSWORD}`. Never type the value into YAML, read it or print it.
- Enter the App Review demo username and password in App Store Connect, or keep them outside the repo. Never create or stage `demo_user.txt` or `demo_password.txt`.
- For store credentials, only help the user configure a path to a private file outside the repo. Never ask for, read or print its contents.
- Use the kit's [store rules](specs/stores.json) by default. When a live store page disagrees, record the difference and its source URL in `.listing-kit/specs.override.json` and tell the user.

## First run and reruns

1. Run `listing-kit doctor` to check tools and `listing-kit detect` to find the Apple and Play paths and see the evidence for platform support. Use each store’s printed paths, relative to the selected app, for all listing reads and writes. The plan's `platforms` flags override detection. If a relevant fact is unknown, ask the user.
2. Discover screens from routes, views, storyboards or navigation graphs. Have the user choose the order, caption, detail and populated state for each. Confirm stores, app IDs, locales, devices and scope before building or installing dependencies.
3. Write `.listing-kit/listing.json` in [format 2](references/plan-file.md). Choose target slots, sizes and style together. Default to framed phones. For `framed`, choose background colors, ink and both headline and detail fonts. Use a band template on Play tablets and Chromebook. Set `style.mode` to `raw` where framing is forbidden. An omitted mode also selects raw. Raw captures must match the upload size.
   Set screen IDs, captions, flow paths, graphics and platform overrides. Set `trees` to override a detected path or choose between duplicate listings. Rerun `listing-kit detect` after changing the plan. Give each deferral a reason. Validation counts the screens assigned to each active target in each store locale. List approved Apple headers under `graphics.apple`. Run `listing-kit plan check` before building.
4. If importing an existing store listing, agree on the first pull before drafting text. Configure an external key path as described in [store management](references/metadata/fastlane-layout.md#store-management). For Apple, run `listing-kit fastlane setup --store apple`, then `listing-kit pull --store apple`. For Play, run `listing-kit fastlane setup --store play`, then `listing-kit pull --store play`. These commands use the app ID in the plan. Review conflicts with the user.
5. Build and install the app on the chosen simulator or emulator. Follow the stack instructions for [iOS](references/stacks/ios-native.md), [Android](references/stacks/android-native.md), [Flutter](references/stacks/flutter.md) or [React Native and Expo](references/stacks/react-native-expo.md). Write one [Maestro flow](references/driving/maestro.md) per capture screen. Launch into the planned state and assert on visible content. A panel needs no flow. Run `listing-kit plan check --for capture` once the flows exist.
6. If every screen is automated, run `listing-kit capture`. For mixed runs, select automated jobs with `listing-kit capture --target ID --screen ID`. Report any manual jobs left outstanding. In an attended session, use `listing-kit capture --manual --target ID --screen ID`. The selected flow file must exist. Navigate on the device and press Enter for each prompt. Capture saves checked PNGs under `.listing-kit/raw/`.
7. Compare `listing-kit plan outputs` with existing filenames. Get approval to replace or retire old images. Inspect `listing-kit compose --preview`, then run `listing-kit compose`. Only use `listing-kit compose --adopt` with permission to replace the listed conflicts. A style-only change to existing images needs approval and `listing-kit compose --restyle`.
8. Write approved UTF-8 copy under the `apple.metadata` and `play.metadata` paths from detect. Follow the [per-store file layout](references/metadata/fastlane-layout.md#choosing-the-app-and-fastlane-directories). From the skill directory, run `bash scripts/lib/secret-scan.sh --listing <app-root>` with the selected app’s absolute path. Run `listing-kit validate`. For an Apple submission, supply the actual date and build SDK with `listing-kit validate --as-of YYYY-MM-DD --ios-sdk X.Y`. Fix failures. Report warnings and missing inputs. Run `listing-kit review` and inspect `listing-review.html`. In the app's Git worktree, run `listing-kit hook install` to refresh the page from staged inputs.
9. For hand upload, run `listing-kit handoff --open` from the selected app. For store sync, run `listing-kit publish --store apple` or `listing-kit publish --store play` in the source app. Inspect the proposed changes. Both stores are gated pending live tests. Never pass `--yes` or set `LK_PUBLISH_UNVERIFIED`. That variable is the maintainers' live-test switch and can enable real uploads.

## App-owned screenshot templates

Run `listing-kit template new acorn` in the app root for a commented starter. Set `style.template` to `user:acorn` in a framed plan, or override `template` on a screen or target. Bare names select bundled layouts. Every app layout requires `user:<name>`. Check the plan and inspect the rendered preview before approving a restyle. [Template interface and example](references/templates.md)
