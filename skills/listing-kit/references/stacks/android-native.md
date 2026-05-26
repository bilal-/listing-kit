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
emulator -avd Pixel_8_API_34 -no-snapshot -no-boot-anim &
adb wait-for-device
./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell monkey -p <applicationId> -c android.intent.category.LAUNCHER 1
```
Resolve `<applicationId>` from `applicationId` in `build.gradle(.kts)`.

## Sanitize & permissions
- Status bar (demo mode): `scripts/capture/sanitize-status-bar.sh android`
- Permissions: `scripts/capture/grant-permissions.sh android <applicationId>` (uses `adb shell pm grant`)

## Capture
```sh
adb exec-out screencap -p > "01_home.png"
```
For specific densities/sizes, launch an AVD whose resolution matches the target
device class (phone / 7" / 10" tablet / Wear) — see `../stores/google-play.md`.
