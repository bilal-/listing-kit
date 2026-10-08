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

## Discover signals (static, before building)
- SwiftUI: `View` structs, `NavigationStack`/`NavigationLink` destinations, `TabView` items
- UIKit: storyboard scenes + segues, `UITabBarController` items, `UIViewController` subclasses
- URL schemes / universal links: `CFBundleURLTypes` in `Info.plist`, associated-domains entitlement
- iPad support: target families / `UISupportedInterfaceOrientations~ipad`

## Build & launch
```sh
# Pick a simulator matching the required device class (see ../stores/apple-app-store.md).
# Dynamic Island medium is currently required; list installed types with `xcrun simctl list devicetypes`.
xcrun simctl boot "iPhone 17 Pro"        # 1206×2622
xcodebuild -workspace App.xcworkspace -scheme App -configuration Release \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  -derivedDataPath build build
xcrun simctl install booted "build/Build/Products/Release-iphonesimulator/App.app"
xcrun simctl launch booted <bundle-id>
```
Resolve `<bundle-id>` from `PRODUCT_BUNDLE_IDENTIFIER` (build settings) or the built `Info.plist`.

## Sanitize & permissions
- Status bar: `scripts/capture/sanitize-status-bar.sh ios booted`
- Permissions: `scripts/capture/grant-permissions.sh ios <bundle-id> booted` (camera/ATT can't be pre-granted — handle in-flow)

## Capture
```sh
xcrun simctl io booted screenshot --type=png "01_home.png"
```
Full-resolution, status-bar override intact. Preferred over Maestro's `takeScreenshot`.
For delivery, prefer `scripts/capture/capture-ios.sh` with the explicit device,
display and planned native dimensions. It normalizes to RGB, strips metadata and
replaces the destination only after rejecting wrong-size and solid/blank frames.
This does not replace visual review or assertions that the intended screen loaded.

For devices with multiple displays, enumerate them first:

```sh
xcrun simctl io "$DEVICE_UDID" enumerate
bash scripts/capture/capture-ios.sh "$DEVICE_UDID" "$DISPLAY_NAME" 1398x2034 output.png
```

Select the screen showing the app, using the enumerated screen ID/name. Do not
assume screen 2 is the inner display; it may be TV output. On Duo, change the pose
in Device Hub, then check the active display's dimensions and app content. Reject
black captures, system screens or clipped controls. If the runtime/automation
cannot reach a state, report that limitation instead of fabricating or resizing
another device's UI. A capture does not qualify display transitions or hardware.
