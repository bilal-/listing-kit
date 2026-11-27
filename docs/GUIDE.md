# First run with Recipe Box

The [bundled Expo app](../examples/expo-recipe-box/README.md) includes the four Maestro flows, native captures and store images from a Release build. You can compose and inspect the listing without a device.

## Inspect the example

[Install the launcher](INSTALL.md). From the kit checkout, export the committed example into a disposable Git repository. Install the review hook only in that copy.

```sh
app=$(mktemp -d /tmp/recipe-box.XXXXXX)
git archive HEAD:examples/expo-recipe-box | tar -x -C "$app"
cd "$app"
git init
listing-kit doctor
listing-kit detect
listing-kit plan check --for capture
listing-kit plan outputs
listing-kit validate
listing-kit review
```

Validation exits 0. Open `listing-review.html` to inspect the saved copy, galleries and validation report. Doctor reports optional tools separately. Store synchronization needs fastlane.

## Build and capture

The [shipped plan](../examples/expo-recipe-box/.listing-kit/listing.json) selects two iPhone display sizes, a 13-inch iPad and a Play phone. Inspect the device types and native sizes before building. Use `xcrun simctl list devices available` and `emulator -list-avds` to identify matching devices. Start the selected AVD and check its name with `adb -s SERIAL emu avd name`. Pin the three simulator UDIDs and emulator serial in the ignored `.listing-kit/local.json`, under `devices` keyed by the plan target IDs.

Install dependencies and build Release with bundled JavaScript. The [Expo reference](../skills/listing-kit/references/stacks/react-native-expo.md) includes native build commands. The simulator build can be installed on all three Apple devices. Use the AVD serial when installing the APK.

```sh
listing-kit capture --dry-run
listing-kit capture
```

For a single installed device, select its target, for example `listing-kit capture --target iphone-medium`. The dry run checks the device and display selection. Capture runs each flow and writes the PNGs under `.listing-kit/raw/TARGET/en-US/`. Inspect the status bar, navigation and seeded content in the raw images before composing. On iPadOS 26, check the lower-right corner for the window handle and follow the [Full Screen Apps instructions](../skills/listing-kit/references/driving/maestro.md#write-a-flow) if it appears. Shut down the devices you started.

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

## Use your own screenshot layout

Run `listing-kit template new acorn` in the app root. Edit `.listing-kit/templates/acorn.html`, add an optional `acorn.css`, and select `user:acorn` in the framed plan's `style.template`. A target or screen can select a different layout with its `template` key. Use `user:band` to select an app layout named `band`. Check the plan, then inspect `listing-kit compose --preview`. The gallery embeds a PNG of each app layout. [Template values and working example](../skills/listing-kit/references/templates.md)

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
