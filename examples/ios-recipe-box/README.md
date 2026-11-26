# Recipe Box for iOS

Source and plan only. Not yet built or captured on a device.

This SwiftUI example has a hand-written Xcode project with one iPhone application target and a Release configuration. The four Maestro flows launch with `-recipeBoxState demo` to open the five recipes with Lemons and Avocados checked on the shopping list.

## Build, install and capture

Start at the kit checkout root on a Mac with Xcode 16 or later, an iPhone 16 Pro simulator (1206 × 2622), Maestro, JDK 17+ and ImageMagick. Boot that simulator, select portrait orientation and English (US), then run the following in Bash. Use its UDID from the device list.

```sh
kit="$PWD/skills/listing-kit/bin/listing-kit"
app=$(mktemp -d)
cp -R examples/ios-recipe-box/. "$app/"
cd "$app"
"$kit" plan check --for capture .
xcrun simctl list devices booted
read -r -p "iPhone 16 Pro UDID: " iphone
xcodebuild -project RecipeBox.xcodeproj -target RecipeBox -configuration Release \
  -sdk iphonesimulator CONFIGURATION_BUILD_DIR="$PWD/build" build
xcrun simctl install "$iphone" build/RecipeBox.app
"$kit" capture . --target iphone --device "$iphone"
```
