# Recipe Box for Flutter

Source and plan only. Not yet built or captured on a device.

The four Maestro flows use the same Flutter semantics identifiers on iOS and Android. The small host files pass the `recipeBoxState=demo` launch argument or string intent extra to Dart. This opens the five recipes with Lemons and Avocados checked on the shopping list.

## Set up the working copy

Use Flutter **3.29.3** for the platform templates. The iOS host uses that version's storyboard-based app delegate. From the kit checkout root, run these commands in Bash. The configure step sets the display names and application IDs and installs the two host files.

```sh
kit="$PWD/skills/listing-kit/bin/listing-kit"
app=$(mktemp -d)
cp -R examples/flutter-recipe-box/. "$app/"
cd "$app"
flutter create --no-pub --platforms=ios,android --project-name recipebox --org com.example .
python3 host/configure.py
flutter pub get
"$kit" plan check --for capture .
```

## Build, install and capture on iOS

Use macOS, Xcode 16 with an iOS 18 runtime, CocoaPods, Maestro, JDK 17+ and ImageMagick. Boot an iPhone 16 Pro and a 13-inch iPad Pro (M4) simulator, both in English (US) and portrait. Use their UDIDs from the device list. The simulator build runs in debug mode with Flutter's debug banner hidden.

```sh
flutter build ios --simulator --debug
xcrun simctl list devices booted
read -r -p "iPhone 16 Pro UDID: " iphone
read -r -p "13-inch iPad Pro (M4) UDID: " ipad
xcrun simctl install "$iphone" build/ios/iphonesimulator/Runner.app
xcrun simctl install "$ipad" build/ios/iphonesimulator/Runner.app
"$kit" capture . --target iphone --device "$iphone"
"$kit" capture . --target ipad --device "$ipad"
```

## Build, install and capture on Android

Use the Android SDK, JDK 17, Maestro and ImageMagick. Start a Pixel 8 emulator in English (US), portrait at 1080 × 2400, and use its serial from the device list.

```sh
flutter build apk --release
adb devices
read -r -p "Pixel 8 emulator serial: " pixel
adb -s "$pixel" install -r build/app/outputs/flutter-apk/app-release.apk
"$kit" capture . --target play-phone --device "$pixel"
```
