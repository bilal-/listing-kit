# Example apps

| Example | Stack | Status |
| --- | --- | --- |
| [`expo-recipe-box`](expo-recipe-box) | Expo / React Native | Release capture on two iPhones, iPad and Android phone. The listing passes validation. [Capture details](expo-recipe-box/README.md) |
| [`ios-recipe-box`](ios-recipe-box) | Native iOS / SwiftUI | Compiles for the iOS simulator. Not yet installed or captured on a device. |
| [`android-recipe-box`](android-recipe-box) | Native Android / Jetpack Compose | Source and plan only. Not yet built or captured on a device. |
| [`flutter-recipe-box`](flutter-recipe-box) | Flutter / iOS and Android | Source and plan only. Not yet built or captured on a device. |

All four apps show the same five recipes, ingredients, cooking steps and shopping list. Each example includes Maestro flows for the recipe list, recipe detail, shopping list and settings. Each example has a capture plan.

The [first-run walkthrough](../docs/GUIDE.md) uses a copy of the Expo app, its committed fastlane listing and its four flows. You can validate the listing and build a review page without a simulator. Capture needs a matching simulator or emulator and an installed build.

For a quick look at the app itself:

```sh
cd examples/expo-recipe-box
npm ci
npx expo start
```

For repeatable store captures use the [Expo build instructions](../skills/listing-kit/references/stacks/react-native-expo.md). The example's flows clear app state and expect a bundled JS application.
