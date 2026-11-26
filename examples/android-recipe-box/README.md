# Recipe Box for Android

Source and plan only. Not yet built or captured on a device.

This Kotlin and Jetpack Compose example exposes its test tags as Android resource IDs. The Maestro flows send the string intent extra `recipeBoxState=demo`. The five recipes open with Lemons and Avocados checked on the shopping list.

## Build, install and capture

Start at the kit checkout root with JDK 17, Gradle 8.9, the Android SDK (platform 35, Build Tools 34.0.0 and platform-tools), Maestro and ImageMagick. Point `ANDROID_HOME` at the SDK and start a Pixel 8 emulator in English (US), portrait, at its native 1080 × 2400. Run these commands in Bash, entering its serial from `adb devices`.

```sh
kit="$PWD/skills/listing-kit/bin/listing-kit"
app=$(mktemp -d)
cp -R examples/android-recipe-box/. "$app/"
cd "$app"
"$kit" plan check --for capture .
gradle wrapper --gradle-version 8.9
./gradlew :app:assembleDebug
adb devices
read -r -p "Pixel 8 emulator serial: " pixel
adb -s "$pixel" install -r app/build/outputs/apk/debug/app-debug.apk
"$kit" capture . --target play-phone --device "$pixel"
```

The wrapper setup creates its scripts and JAR in the working copy.
