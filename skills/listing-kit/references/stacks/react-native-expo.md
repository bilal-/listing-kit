# Stack module: React Native / Expo

Answers: how do I **detect, build, launch, discover screens, and capture** for a
RN/Expo app on iOS **and** Android? Driving is shared (see `../driving/maestro.md`).

## Detection signatures
- `react-native` in `package.json` dependencies
- Expo: `app.json` / `app.config.{js,ts}` with an `expo` key; `expo` dependency
- `metro.config.js`

## Expo vs. bare RN — branch on this
The build/run path differs materially; detect which you're in:

| | Signal | Run path |
|---|---|---|
| **Expo (managed / prebuild)** | `expo` dependency, `app.json` with `expo` | `npx expo run:ios` / `npx expo run:android`, or `npx expo prebuild` then native build. EAS for cloud builds. |
| **Bare RN** | `react-native` without Expo managed config | `npx react-native run-ios` / `run-android` (Metro bundler) |

Install JS deps first (`npm ci` / `yarn` / `pnpm i` — match the lockfile present).

## Doctor checks
- Node + package manager (match lockfile: `package-lock.json` / `yarn.lock` / `pnpm-lock.yaml`)
- `npx expo-doctor` (Expo) or RN `npx react-native doctor`
- Per-target: see `ios-native.md` / `android-native.md`

## Discover signals (static, before building)
- React Navigation: `Stack`/`Tab`/`Drawer` `Navigator` + `Screen` route configs
- Expo Router: file-based routes under `app/`
- Registered deep links / URL scheme: `expo.scheme` in `app.json`, `Linking` config

For iOS 27 targets, verify the app adopts UIKit's scene lifecycle before capture.
Expo SDK 57.0.23+ supports the `expo-build-properties` option
`ios.enableSceneSupport`; newer SDKs may provide it by default. Follow the
[Expo scene-lifecycle guidance](https://github.com/expo/fyi/blob/main/ios-scene-lifecycle.md)
for the installed SDK, regenerate native projects and cold-launch on the actual
runtime. Keep any needed application compatibility work explicit in scope.

If a new Xcode cannot import Expo's precompiled Swift modules, first verify the
compiler and framework versions. Expo's `ios.usePrecompiledModules: false` (or
`EXPO_USE_PRECOMPILED_MODULES=0` during Pod installation) is a supported source-build
path. It may also require invalidating stale generated framework caches. Do not
patch compiled interfaces, upgrade major SDK versions or bump the app version
just to get a listing capture. Preserve the app's normal entry point: inject
capture/demo content only into a disposable capture build.

## Build & launch
```sh
# Expo (Release embeds the JS bundle; see ../driving/maestro.md)
npx expo run:ios --configuration Release --device "iPhone 17 Pro"
npx expo run:android --variant release
# Bare RN
npx react-native run-ios --mode Release --simulator "iPhone 17 Pro"
npx react-native run-android --mode release
```

## Status bar style (Android)
Recent Expo/RN Android templates draw edge-to-edge with **light** status-bar icons
by default. On a light-themed screen they're invisible, so the sanitized 9:41 bar
comes out blank. If the app doesn't set a style, ask before adding
`<StatusBar style="dark" />` (from `expo-status-bar`) to the root layout.

## Sanitize, permissions & capture

For a dark app, check the navigation theme as well as individual screen colors.
An Expo Router stack using its default light theme can expose white margins or
light native controls on an adaptive display even when every screen is black.
Use the installed Router version's `ThemeProvider` and `DarkTheme` API, rebuild
the bundle and inspect a fresh native capture. See
[Expo's navigation theme guidance](https://docs.expo.dev/router/advanced/stack-toolbar/#common-problems).

If a native margin stays white despite a configured dark `backgroundColor`,
check that `expo-system-ui` and its config plugin are installed, then regenerate
and rebuild. Expo applies the iOS root background through that plugin; React
screen styling alone does not cover views outside the React tree. Verify the
actual raw capture before attributing a margin to the app or editing its pixels.
See [Expo SystemUI](https://docs.expo.dev/versions/latest/sdk/system-ui/).

Same as the underlying platform — use the **platform** SDK tooling
(`xcrun simctl` / `adb`) for status bar, permissions, and capture. See
`ios-native.md` and `android-native.md`.
