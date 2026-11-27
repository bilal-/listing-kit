# Stack module: Native Android

Answers: how do I **detect, build, launch the right emulator, discover screens,
and capture** for a native Android app? Driving is shared (see `../driving/maestro.md`).

## Detection signatures
- `build.gradle` / `build.gradle.kts` **and** `AndroidManifest.xml`
- No JS/Dart bridge (no `react-native` in `package.json`, no `flutter:` in `pubspec.yaml`)

## Doctor checks
- `java -version` (JDK present; matches Gradle/AGP requirements)
- `adb version`, and `sdkmanager`/`avdmanager` available
- At least one AVD: `emulator -list-avds`
- `./gradlew tasks` resolves (wrapper present)

## Discover signals (static, before building)
- Navigation graph XML (`res/navigation/*.xml`) destinations
- `<activity>` / `<fragment>` declarations and labels in `AndroidManifest.xml`
- `<intent-filter>` deep links (`android:scheme`, `android:host`, App Links)
- Wear OS: `wear` module / `com.google.android.wearable` features

## Build & launch
```sh
emulator -list-avds                     # pick one; names vary per machine
emulator -avd <avd-name> -no-snapshot -no-boot-anim &
adb wait-for-device
./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell monkey -p <applicationId> -c android.intent.category.LAUNCHER 1
```
Resolve `<applicationId>` from `applicationId` in `build.gradle(.kts)`. A native debug
APK is self-contained, so it's fine for capture; build release instead if the app
shows debug-only UI.

## Capture

Start the planned AVD, install the app and run `listing-kit capture` with the [saved flows](../driving/maestro.md). Capture matches the emulator profile, sanitizes the status bar and uses adb to capture the display. Choose a matching tablet AVD for a tablet target. A physical device requires explicit selection and permission to run a flow that can clear app data.
