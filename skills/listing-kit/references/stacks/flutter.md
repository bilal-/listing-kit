# Stack module: Flutter

Answers: how do I **detect, build, launch, discover screens, and capture** for a
Flutter app on iOS **and** Android? Driving is shared (see `../driving/maestro.md`).

## Detection signatures
- `pubspec.yaml` with a `flutter:` section
- `lib/main.dart`

Flutter produces **both** iOS and Android — confirm which store(s) to target.

## Doctor checks
- `flutter --version` and `flutter doctor` (resolves Android toolchain + Xcode)
- `flutter pub get`
- Per-target sub-checks: see `ios-native.md` (simulator) and `android-native.md` (emulator)

## Discover signals (static, before building)
- Route tables: `Navigator` named routes, `routes:`/`onGenerateRoute` in `MaterialApp`
- Router packages: `go_router` / `auto_route` route definitions
- Tab/scaffold destinations: `BottomNavigationBar`, `NavigationRail` items
- Deep links: `uni_links` / platform intent filters + URL types

## Build & launch
```sh
flutter devices                         # list booted simulators/emulators
flutter run -d <device-id> --release    # release avoids debug banner; or --profile
```
For store-clean output prefer `--release` (no debug banner). Boot the simulator/
emulator first (see the native docs) so it appears in `flutter devices`.

## Sanitize & permissions
Same as the underlying platform:
- iOS: `scripts/capture/*.sh ios booted ...`
- Android: `scripts/capture/*.sh android ...`

## Capture
Use the **platform** SDK tooling, not `flutter screenshot` (which lacks the
status-bar override): `xcrun simctl io booted screenshot` on iOS,
`adb exec-out screencap -p` on Android.

## Driving caveat
Maestro drives Flutter through the **semantics tree**. It must be populated for
tap-by-label to work. Custom-painted/canvas screens without semantics expose
little to target and fall through to manual-assist (see `../driving/maestro.md`).
Adding `Semantics`/`semanticLabel` in the app improves automatability.
