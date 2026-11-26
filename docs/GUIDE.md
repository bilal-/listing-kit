# First run with Recipe Box

The [bundled Expo app](../examples/expo-recipe-box) has seeded recipes, four Maestro flows and a historical listing. You can inspect the listing without a simulator.

## Inspect the example

[Install the launcher](INSTALL.md). From the root of the kit checkout, copy the app outside the checkout. Initialize the copy as its own Git repository. Never install the review hook in the kit repository.

```sh
app=$(mktemp -d /tmp/recipe-box.XXXXXX)
cp -R examples/expo-recipe-box/. "$app/"
cd "$app"
git init
```

```sh
listing-kit doctor
listing-kit detect
```

Doctor exits 0 when Python 3.8+ and the bundled store rules pass their checks. It exits 3 if either check fails. Missing tools, a missing or invalid plan and an inactive hook appear in the report. They do not change the exit status. For this app, detect exits 0 and prints the Apple and Play paths along with the evidence for each platform condition. Use the paths relative to the app directory.

```sh
listing-kit validate
```

On the untouched example, validation exits **1**. The older iPhone screenshots do not cover the required Dynamic Island medium display. Run review as a separate command even when validation fails.

```sh
listing-kit review
```

Review exits **0** and writes `listing-review.html`. Open it to see the saved copy, galleries and validation result.

## Plan a new set

Ask the agent to “prepare my store listing.” Read the routes and the flows together. The recipe list shows seeded recipes and the detail flow checks an ingredient. Start with these two screens for the missing iPhone slot. Agree on the captions and device before building.

Save this plan as `.listing-kit/listing.json` in the copy. It captures two iPhone screens. Standalone review and handoff still show the existing iPad and Play assets. After composing only this target, the Apple publish preview exits 1. It checks planned screenshots, and Recipe Box declares iPad support. Add an active `ipad-13` target and compose its images before previewing an Apple submission.

```json
{
  "format": 2,
  "app": {"ios": "sh.bilal.recipebox"},
  "locales": ["en-US"],
  "style": {
    "mode": "framed",
    "palette": {"background": ["#FFF7EA"], "ink": "#25180D"},
    "fonts": {
      "default": {"headline": ["bundled:Inter"], "detail": ["bundled:Inter"]}
    }
  },
  "targets": [
    {"id": "iphone", "store": "apple", "slot": "iphone-di-medium",
     "size": [1206, 2622], "state": "active"}
  ],
  "screens": [
    {"id": "recipes", "flow": ".listing-kit/flows/recipes.yaml",
     "caption": {"en-US": "Your recipe box"}},
    {"id": "recipe-detail", "flow": ".listing-kit/flows/recipe-detail.yaml",
     "caption": {"en-US": "Ingredients at a glance"}}
  ]
}
```

For Apple, also save the agreed counts, headers and deferrals in the [Apple asset plan](../skills/listing-kit/references/metadata/fastlane-layout.md#apple-asset-plan). For this walkthrough, record two shots for `iPhone Dynamic Island (medium display)` in `en-US`. Preserve any other approved coverage.

Run `listing-kit plan check --for capture` to check the plan and flow paths. Run `listing-kit plan outputs` to see where the two raw and final images will go. For a larger plan, add locales, approved target slots, graphics and split roots as needed. [Plan reference](../skills/listing-kit/references/plan-file.md)

## Build and capture

Use a Mac with Node.js and npm, CocoaPods, and Xcode 26 or later. Select that Xcode as the developer directory. Install a compatible iOS runtime and create an iPhone 17 Pro simulator (1206 × 2622). Automated capture needs Maestro, JDK 17+ and ImageMagick. Framed composition also needs a Chromium browser. See the [Expo build instructions](../skills/listing-kit/references/stacks/react-native-expo.md).

Build and install the Release app. Its JS bundle survives the flows' app-state reset.

```sh
npm ci
npx expo run:ios --configuration Release --device "iPhone 17 Pro"
```

If Expo leaves an “Open in Recipe Box?” alert on screen, shut down that simulator before capture. Capture boots it again.

```sh
listing-kit capture --dry-run
listing-kit capture
```

Dry run checks device selection. Capture runs the saved flows, sanitizes the status bar and writes the PNGs under `.listing-kit/raw/iphone/en-US/`. For an Android plan, install the app on the matching running emulator first.

## Compose, validate and review

```sh
listing-kit compose --preview
listing-kit compose
listing-kit validate
```

Run review even if validation reports a failure.

```sh
listing-kit review
```

Inspect `.listing-kit/preview.html` for the planned appearance and `listing-review.html` for the finished listing.

When extending the plan to existing galleries, compare `listing-kit plan outputs` with the committed files. A Play output such as `01_recipes.png` can collide with an existing file. Use `listing-kit compose --adopt` only with approval to replace the named files. Apple output names include a target suffix. Review the old and new images side by side, then get approval to move superseded images out of the gallery before validation.

Run `listing-kit detect` and put approved copy changes under the printed `apple.metadata` or `play.metadata` directory for that locale. Rebuild the review after edits. For a future submission, supply the intended date and SDK with `listing-kit validate --as-of YYYY-MM-DD --ios-sdk X.Y`.

In the initialized copy, run `listing-kit hook install`, then `listing-kit hook status`. Status exits 1 before installation and 0 when the hook is active. The hook scans staged listing inputs and refreshes the staged review page. Commit the public listing, plan, flows and ownership records together. [File layout and ignore entries](../skills/listing-kit/references/metadata/fastlane-layout.md)

## Hand over

Run `listing-kit handoff --open` to open the upload index. Use its text and ordered assets in the named store destinations.

## Sync an app you own

Skip store sync for the bundled example. For your own app, install fastlane (2.242.0 uses Ruby 3.2+). Apple needs an editable App Store Connect version. Play needs a first build already uploaded in Play Console. Keep the key file outside the repository. [Credentials](CREDENTIALS.md)

Choose the commands for your store. Replace the ID and path with your own. These examples work before a plan exists. Setup checks download access and saves the supplied key path. Pull uses it to import store text. Review conflicts before editing.

```sh
listing-kit fastlane setup --store apple --app-identifier YOUR_BUNDLE_ID --apple-api-key-path /path/to/apple-key.json
listing-kit pull --store apple --app-identifier YOUR_BUNDLE_ID
```

```sh
listing-kit fastlane setup --store play --package-name YOUR_PACKAGE --play-json-key-path /path/to/play-key.json
listing-kit pull --store play --package-name YOUR_PACKAGE
```

With the store ID in your plan and all required targets composed, preview that store's changes with `listing-kit publish --store apple` or `listing-kit publish --store play`. The preview validates the planned listing. It prints the proposed fastlane command when there are comparable changes. Agents must never pass `--yes` or set `LK_PUBLISH_UNVERIFIED`, the maintainers' live-test switch. [Troubleshooting](TROUBLESHOOTING.md)
