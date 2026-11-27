# Stack module: Native iOS

Answers: how do I **detect, build, launch the right simulator, discover screens,
and capture** for a native iOS app? Driving is shared (see `../driving/maestro.md`).

## Detection signatures
- `*.xcodeproj` / `*.xcworkspace`, or `Package.swift`
- No JS/Dart bridge (no `package.json` with `react-native`, no `pubspec.yaml` with `flutter:`)

If both `.xcworkspace` and `.xcodeproj` exist, prefer the workspace (CocoaPods/SPM).

## Doctor checks
- `xcode-select -p` and `xcodebuild -version`
- `xcrun simctl list devices` (a usable simulator runtime exists)
- CocoaPods if a `Podfile` is present (`pod --version`); run `pod install` from the directory containing that Podfile
- Swift Package resolution if `Package.swift` / SPM dependencies

Verify the selected device type **and runtime** (`xcrun simctl list devicetypes`
and `xcrun simctl list runtimes`) before a long build. A newer device may need a
side-by-side Xcode and a separate runtime download. Check disk space for the
archive, extracted app, runtime, simulator data and build products. Use
`DEVELOPER_DIR` consistently for build/install/capture without changing the
machine's default Xcode. Preserve signed artifacts and personal simulator data.
A successful build is not a successful launch: cold-launch and assert visible
app content on the target runtime before driving every planned state.

### Optional Duo capture

Run the read-only preflight using the selected Xcode (it honors `DEVELOPER_DIR`):

```sh
# Handle exit 3 explicitly; do not let set -e abort the whole listing run.
if python3 scripts/doctor/iphone-duo.py; then
  echo "Duo tooling ready; propose it only if the user wants this target."
else
  status=$?
  if [ "$status" -ne 3 ]; then exit "$status"; fi
  echo "Duo unavailable; continue other targets and record the reported reason."
fi
```

The helper checks iOS simulator SDK 27.1+, the Duo device type and an available
compatible iOS runtime. A newer Xcode version alone is not enough. Exit 0 means
those capabilities exist, not that the app launches or adapts correctly.

If Duo is unavailable, propose a deferred target and record the reason in the [listing plan](../plan-file.md). Ask before changing an approved active target. Continue with devices that are available. When the tooling is ready, confirm the target and mark it active. A deferral does not waive a store requirement.

## Discover signals (static, before building)
- SwiftUI: `View` structs, `NavigationStack`/`NavigationLink` destinations, `TabView` items
- UIKit: storyboard scenes + segues, `UITabBarController` items, `UIViewController` subclasses
- URL schemes / universal links: `CFBundleURLTypes` in `Info.plist`, associated-domains entitlement
- iPad support: target families / `UISupportedInterfaceOrientations~ipad`

## Build & launch
```sh
# Pick a simulator matching the required device class (see ../stores/apple-app-store.md).
# Dynamic Island medium is currently required; list installed types with `xcrun simctl list devicetypes`.
xcrun simctl boot "iPhone 17 Pro"        # verify the native size against the Apple screenshot table
xcodebuild -workspace App.xcworkspace -scheme App -configuration Release \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  -derivedDataPath build build
xcrun simctl install booted "build/Build/Products/Release-iphonesimulator/App.app"
xcrun simctl launch booted <bundle-id>
```
Resolve `<bundle-id>` from `PRODUCT_BUNDLE_IDENTIFIER` (build settings) or the built `Info.plist`.

## Capture

Run `listing-kit capture` after installing the app and saving the [Maestro flows](../driving/maestro.md). Set permissions on launch or handle the dialog in the flow. Capture sets the status bar and checks the dimensions and pixel variation before writing a raw image.

For a device with multiple displays, run `xcrun simctl io "$DEVICE_UDID" enumerate`. Set the target's `capture.display` and `capture.nativeSize` for the intended orientation.

Select the screen showing the app, using the enumerated screen ID/name. Do not
assume screen 2 is the inner display; it may be TV output. On Duo, change the pose
in Device Hub, then check the active display's dimensions and app content. Reject
black captures, system screens or clipped controls. If the runtime/automation
cannot reach a state, report that limitation instead of fabricating or resizing
another device's UI. A capture does not qualify display transitions or hardware.

Check the effect of rotation and Home/background automation on the active
display: a command reporting success does not prove that the display rotated or
the app left the foreground. Use Device Hub's pose controls for folding; screen
power controls are not a substitute for a fold transition.
