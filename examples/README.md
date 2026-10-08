# Examples

Real apps you can run listing-kit against — to see what it produces, and to test
changes against. Each example is a deliberately minimal but **automation-friendly**
app: it has a URL scheme, accessibility labels on every interactive element, and a
demo-data mode (populated screens, no login wall).

| Example | Stack | Status |
|---|---|---|
| [`expo-recipe-box`](expo-recipe-box) | Expo / React Native | app and historical listing output ([report](expo-recipe-box/LISTING-REPORT.md)); iOS medium set needs recapture |
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
npm ci
npx expo start            # press i (iOS sim) or a (Android emulator)
```

### Generate the store listing (Phase B)
The committed iPhone captures predate Apple's Dynamic Island medium requirement.
They remain examples of real UI, but the current validator correctly reports the
missing medium set. Recapture it on a matching simulator; do not resize the old
large images. Tests use temporary synthetic image headers for size-rule coverage.

This is what produces the committed `expo-recipe-box/fastlane/` output, and is the
first real end-to-end run of the skill. Requires Node, Xcode and/or Android SDK, a
booted simulator/emulator, and Maestro.

1. Boot a simulator/emulator. The skill builds a **Release** app itself: the flows
   start with `clearState`, which a dev build (`expo start`) can't survive.
2. From an agent with the listing-kit skill, point it at this folder:
   > "Use listing-kit to generate App Store and Google Play assets for examples/expo-recipe-box."
3. The skill detects Expo, reuses the committed `.listing-kit/flows/`, captures and
   normalizes screenshots, writes the `fastlane/` tree, then validates it.
4. Commit the generated `fastlane/` tree.

### What makes it "listing-kit-ready"
The three things the skill relies on, all visible in the source:
- **URL scheme** — `expo.scheme: "recipebox"` in `app.json`; routes under `app/`.
- **Accessibility labels** — every screen and control has an `accessibilityLabel`.
- **Demo data** — `data/recipes.ts` seeds populated screens; no auth, no network.
