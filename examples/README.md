# Example apps

| Example | Stack | Status |
| --- | --- | --- |
| [`expo-recipe-box`](expo-recipe-box) | Expo / React Native | Historical listing output. The iPhone medium set needs recapture. [Capture report](expo-recipe-box/LISTING-REPORT.md) |
| [`ios-recipe-box`](ios-recipe-box) | Native iOS / SwiftUI | Source and plan only. Not yet built or captured on a device. |
| [`android-recipe-box`](android-recipe-box) | Native Android / Jetpack Compose | Source and plan only. Not yet built or captured on a device. |
| [`flutter-recipe-box`](flutter-recipe-box) | Flutter / iOS and Android | Source and plan only. Not yet built or captured on a device. |

All four apps show the same five recipes, ingredients, cooking steps and shopping list. Each example includes Maestro flows for the recipe list, recipe detail, shopping list and settings. The three source examples have capture plans and build instructions in their READMEs.

The [first-run walkthrough](../docs/GUIDE.md) uses a copy of the Expo app, its committed fastlane listing and two of its flows. You can validate the historical listing and build a review page without a simulator. Capture needs a matching simulator or emulator and an installed build.

For a quick look at the app itself:

```sh
cd examples/expo-recipe-box
npm ci
npx expo start
```

For repeatable store captures use the [Expo build instructions](../skills/listing-kit/references/stacks/react-native-expo.md). The example's flows clear app state and expect a bundled JS application.
