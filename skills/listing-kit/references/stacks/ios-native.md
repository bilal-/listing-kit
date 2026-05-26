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
- CocoaPods if a `Podfile` is present (`pod --version`); run `pod install`
- Swift Package resolution if `Package.swift` / SPM dependencies

## Discover signals (static, before building)
- SwiftUI: `View` structs, `NavigationStack`/`NavigationLink` destinations, `TabView` items
- UIKit: storyboard scenes + segues, `UITabBarController` items, `UIViewController` subclasses
- URL schemes / universal links: `CFBundleURLTypes` in `Info.plist`, associated-domains entitlement
- iPad support: target families / `UISupportedInterfaceOrientations~ipad`

## Build & launch
```sh
# Pick a simulator matching the required device class (see ../stores/apple-app-store.md)
xcrun simctl boot "iPhone 16 Pro Max"        # 6.9"
xcodebuild -workspace App.xcworkspace -scheme App \
  -destination 'platform=iOS Simulator,name=iPhone 16 Pro Max' \
  -derivedDataPath build build
xcrun simctl install booted "build/Build/Products/Debug-iphonesimulator/App.app"
xcrun simctl launch booted <bundle-id>
```
Resolve `<bundle-id>` from `PRODUCT_BUNDLE_IDENTIFIER` (build settings) or the built `Info.plist`.

## Sanitize & permissions
- Status bar: `scripts/capture/sanitize-status-bar.sh ios booted`
- Permissions: `scripts/capture/grant-permissions.sh ios booted <bundle-id>` (camera/ATT can't be pre-granted — handle in-flow)

## Capture
```sh
xcrun simctl io booted screenshot --type=png "01_home.png"
```
Full-resolution, status-bar override intact. Preferred over Maestro's `takeScreenshot`.
