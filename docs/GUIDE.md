# First run with Recipe Box

The [bundled Expo app](../examples/expo-recipe-box) has sample recipes, four saved Maestro flows and a historical listing. You can inspect that listing before installing a simulator. Work in a disposable copy of the app for this walkthrough.

## Inspect what is there

[Install the launcher](INSTALL.md), change into your copy of `examples/expo-recipe-box`, and run:

```sh
listing-kit doctor
listing-kit detect
listing-kit validate
listing-kit review
```

Doctor reports tools, the plan and the hook. On this first run the plan and hook can be missing. Detect prints each platform condition and its evidence. Open `listing-review.html` to read the existing copy and see the galleries. The example's older iPhone shots leave the Dynamic Island medium set missing. The validator reports that failure.

## Plan a new set

Ask the agent to “prepare my store listing.” Read the routes and the flows together. The recipe list shows seeded recipes and the detail flow checks an ingredient. Start with these two screens for the missing iPhone slot. Agree on the captions and device before building.

Save the following as `.listing-kit/listing.json` in your copy. It adds one target to exercise the pipeline. The existing iPad and Play assets remain part of the listing you review.

```json
{
  "format": 2,
  "app": {"ios": "sh.bilal.recipebox"},
  "locales": ["en-US"],
  "style": {"mode": "framed"},
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

Run `listing-kit plan check --for capture` to check the plan and flow paths. Run `listing-kit plan outputs` to see where the two raw and final images will go. For a larger plan, add locales, approved target slots, graphics and split roots as needed. [Plan reference](../skills/listing-kit/references/plan-file.md)

## Build and capture

On a Mac with the matching simulator installed, use the [Expo stack instructions](../skills/listing-kit/references/stacks/react-native-expo.md) to build and install the app. The rule for this target selects an iPhone 17 Pro. The example's flows clear app state on launch, so embed the JS bundle in a Release build.

```sh
npm ci
npx expo run:ios --configuration Release --device "iPhone 17 Pro"
listing-kit capture --dry-run
listing-kit capture
```

Dry run checks device selection. Capture runs the saved flows, sanitizes the status bar and writes the PNGs under `.listing-kit/raw/iphone/en-US/`. For an Android plan, install the app on the matching running emulator first.

## Compose, validate and review

```sh
listing-kit compose --preview
listing-kit compose
listing-kit validate
listing-kit review
```

Inspect `.listing-kit/preview.html` for the planned appearance and `listing-review.html` for the finished listing. If compose reports an ownership conflict, inspect the named file before deciding which version to keep. Put any approved copy changes into the locale's fastlane text files. Rebuild the review after edits. For a future submission, supply the intended date and SDK with `listing-kit validate --as-of YYYY-MM-DD --ios-sdk X.Y`.

In your app's Git worktree, run `listing-kit hook install` and check `listing-kit hook status`. The hook scans staged listing inputs and refreshes the staged review page. Commit the public listing, plan, flows and ownership records together. [File layout and ignore entries](../skills/listing-kit/references/metadata/fastlane-layout.md)

## Hand over

Run `listing-kit handoff --open` to open the upload index. Use its text and ordered assets in the named store destinations.

For an app you own on the store, `listing-kit fastlane setup` checks download access using a credential path. Use `listing-kit pull` to import existing text and review conflicts. Run `listing-kit publish` for a change summary and the proposed fastlane command. This version does not upload until the store adapter passes its live test. [Credentials](CREDENTIALS.md) · [Troubleshooting](TROUBLESHOOTING.md)
