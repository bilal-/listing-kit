# Example apps

| Example | Stack | Status |
| --- | --- | --- |
| [`expo-recipe-box`](expo-recipe-box) | Expo / React Native | Historical listing output. The iPhone medium set needs recapture. [Capture report](expo-recipe-box/LISTING-REPORT.md) |

Recipe Box is a small recipe saver with seeded data and accessible controls. Its four saved Maestro flows visit the recipe list, a recipe detail, the shopping list and settings. The app config declares the recipebox URL scheme and the routes live under `app/`.

Start with the [first-run walkthrough](../docs/GUIDE.md). It uses a copy of this app, the committed fastlane listing and two existing flows. You can validate the historical listing and build a review page without a simulator. Capture needs a matching simulator or emulator and an installed build.

For a quick look at the app itself:

```sh
cd examples/expo-recipe-box
npm ci
npx expo start
```

For repeatable store captures use the [Expo build instructions](../skills/listing-kit/references/stacks/react-native-expo.md). The example's flows clear app state and expect a bundled JS application.
