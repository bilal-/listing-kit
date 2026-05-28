# Examples

Real apps you can run listing-kit against — to see what it produces, and to test
changes against. Each example is a deliberately minimal but **automation-friendly**
app: it has a URL scheme, accessibility labels on every interactive element, and a
demo-data mode (populated screens, no login wall).

| Example | Stack | Status |
|---|---|---|
| [`expo-recipe-box`](expo-recipe-box) | Expo / React Native | app ✅ · iOS listing ✅ · Android listing ✅ ([report](expo-recipe-box/LISTING-REPORT.md)) |
| _native iOS (SwiftUI)_ | — | planned |
| _native Android (Compose)_ | — | planned |
| _Flutter_ | — | planned |

## expo-recipe-box

A tiny recipe saver with four deep-linkable screens:

| Screen | Deep link |
|---|---|
| Recipes (list) | `recipebox://` |
| Recipe detail | `recipebox://recipe/1` |
| Shopping list | `recipebox://shopping` |
| Settings | `recipebox://settings` |

### Run the app
```sh
cd examples/expo-recipe-box
npm install
npx expo start            # press i (iOS sim) or a (Android emulator)
```

### Generate the store listing (Phase B)
This is what produces the committed `expo-recipe-box/fastlane/` output, and is the
first real end-to-end run of the skill. Requires Node, Xcode and/or Android SDK, a
booted simulator/emulator, and Maestro.

1. Boot a simulator/emulator and run the app (above).
2. From an agent with the listing-kit skill, point it at this folder:
   > "Use listing-kit to generate App Store and Google Play assets for examples/expo-recipe-box."
3. The skill detects Expo, reuses the committed `.listing-kit/flows/`, captures
   screenshots, writes the `fastlane/` tree, and runs the secret scan.
4. Commit the generated `fastlane/` tree.

### What makes it "listing-kit-ready"
The three things the skill relies on, all visible in the source:
- **URL scheme** — `expo.scheme: "recipebox"` in `app.json`; routes under `app/`.
- **Accessibility labels** — every screen and control has an `accessibilityLabel`.
- **Demo data** — `data/recipes.ts` seeds populated screens; no auth, no network.
