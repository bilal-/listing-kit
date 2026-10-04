# Driving: Maestro (shared cross-stack layer)

Maestro is the **one** UI-automation tool that is both cross-stack and
cross-platform: a single YAML flow language drives native iOS, native Android,
Flutter, and React Native/Expo, on simulators and emulators, via the live
accessibility hierarchy. So driving is a **shared core capability**, not four
per-stack implementations.

## Gating
Maestro (and its **JDK 17+** dependency, with `JAVA_HOME` set) are **only** needed at the Drive step.
Detect, Doctor, Discover, Plan, metadata collection, Validate, and Assemble all
run without it. **Prompt to install Maestro when the pipeline first needs to
drive the app — never at startup.**

```sh
# install (prompt the user first)
curl -fsSL "https://get.maestro.mobile.dev" | bash
maestro --version
```

## Selecting the device (multi-device machines)
Maestro auto-picks the first available device. On a machine running **both** an
Android emulator and iOS simulators it will likely pick the wrong one (and fail to
launch the app, which isn't installed there). **Always pass the target explicitly:**
```sh
maestro --device <udid-or-serial> test flow.yaml
```
- iOS: the simulator UDID from `xcrun simctl list devices`.
- Android: the emulator serial from `adb devices` (e.g. `emulator-5554`).

The same applies to capture: `xcrun simctl ... <udid>` / `adb -s <serial> ...`.

## Capture from a RELEASE build, not a debug/dev build
Build the app in **release/standalone** configuration for the Run + Drive + Capture
steps — not a debug or Expo dev-client build. (Exception: Flutter on iOS simulators
only runs debug builds; see `../stacks/flutter.md`. A *built* Flutter debug app is
self-contained, so the dev-client problem below doesn't apply.)
- `launchApp: clearState: true` **wipes a dev client's saved Metro URL**, so a debug
  build can no longer load its JS and every flow fails at the first `assertVisible`.
  A release build embeds the JS bundle, so `clearState` works and gives each flow a
  clean starting state.
- Release builds also drop the dev menu / debug banner from screenshots.
- Expo: `npx expo run:ios --configuration Release` / `npx expo run:android --variant release`.
  Native: build the Release configuration.
- `npx expo run:ios` finishes by opening an `expo-development-client` URL, which
  leaves the same "Open in app?" alert on the simulator even for a Release build.
  Reboot the simulator before capturing (`xcrun simctl shutdown <udid> && xcrun simctl boot <udid>`),
  or build with `xcodebuild … -configuration Release` and `simctl install` the `.app`.
- If you must drive a debug/dev build, **omit `clearState`** and reach screens by
  deep-linking the already-running app (back-stack labels may be imperfect).

## Authoring a flow per screen
Prefer the most direct route that doesn't trigger system UI:
1. **Deep link / URL scheme** if the app registers one, **on Android**. On iOS,
   opening a custom-scheme link from outside the app (`openLink`, `simctl openurl`)
   shows a system **"Open in "App"?"** alert that Maestro can't dismiss reliably
   (the tap reports success and the alert stays). On iOS, or for flows shared by
   both platforms, prefer option 2:
   ```yaml
   appId: com.example.app
   ---
   - openLink: "example://library"
   ```
2. **Tap by accessibility label** (works the same on iOS and Android, and gives
   a natural back stack, e.g. a "‹ Library" back button):
   ```yaml
   appId: com.example.app
   ---
   - launchApp:
       clearState: true
   - tapOn: "Library"
   - assertVisible: "My Books"
   ```
   Assert on real content (an item's label), not just a container id, so an empty
   or wrong screen fails the flow instead of being captured.

Use `maestro studio` to inspect the live hierarchy and discover labels/ids while authoring.

## Reaching the desired state
- **Demo / mock mode:** if the app supports it (`--demo`, a mock-data JSON), enable it so screens are populated, not empty.
- **Mock auth / bypass:** social logins (Google/Apple) often fail on simulators — prioritize a mock-auth or bypass route where one exists. Reference secrets from `.listing-kit/secrets.local` or env; **never inline credentials into a committed flow.**
- **iPad (iPadOS 26+):** in the default *Windowed Apps* mode every app shows a
  resize grabber in its bottom-right corner, which ends up in the screenshot. Switch
  the simulator to **Settings → Multitasking & Gestures → Full Screen Apps** before
  capturing (a three-step Maestro flow against `com.apple.Preferences` does it), and
  relaunch your app afterwards so the status bar doesn't show a "◂ Settings" link.
- **Permissions:** pre-grant before driving (`scripts/capture/grant-permissions.sh`); dismiss any residual dialog inside the flow.
- **Reject empty states before capturing.** A deep link or fresh launch lands on *whatever state the app currently has* — which is often empty ("No notes yet", an empty list/cart, a zero-results search). An empty/zero screen is the single most common weak store screenshot. After driving to a screen and **before capturing it**, confirm it is actually populated (assert a content element is visible, e.g. `assertVisible` on a real item, not the empty-state text). If it's empty: seed/mock data to fill it, navigate to a populated instance instead, or drop/replace the screen during Curate. Don't ship the empty state just because the route resolved.

## Persisted flows = rerunnable recipes
Save each flow (e.g. `.listing-kit/flows/<screen>.yaml`). This is what makes
reruns and `--non-interactive`/CI possible: the navigation recipe is captured
once and replayed.

## Flutter caveat
Maestro targets Flutter via the **semantics tree**. Canvas/custom-painted
screens without semantics expose nothing to tap — fall through to manual-assist.

## Manual-assist fallback
When Maestro can't reach a state (canvas/game UIs, missing semantics,
unscriptable auth): instruct the user to navigate manually and signal when to
capture. **Under `--non-interactive`, skip and mark the screen "Missing"** in the
report rather than hanging.

## Why not Detox / XCUITest / Espresso / integration_test?
Each is locked to one stack and/or one OS, so they'd multiply the hardest part
of the build by four. Reusing a repo's *existing* flows from those frameworks is
**deferred to a future version**; Maestro as the sole driver keeps v1 tractable.

## Capture note
Drive with Maestro, but **capture with SDK tooling** (`simctl`/`adb`), not
Maestro's `takeScreenshot` — the SDK tools give clean full-resolution output with
the status-bar override intact.
