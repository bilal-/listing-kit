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

## Build & launch
```sh
# Expo
npx expo run:ios --device "iPhone 16 Pro Max"     # or run:android
# Bare RN
npx react-native run-ios --simulator "iPhone 16 Pro Max"   # or run-android
```

## Sanitize, permissions & capture
Same as the underlying platform — use the **platform** SDK tooling
(`xcrun simctl` / `adb`) for status bar, permissions, and capture. See
`ios-native.md` and `android-native.md`.
