# Drive a capture screen

Save one Maestro YAML flow for each capture screen under `.listing-kit/flows/`. Use its path in the [plan](../plan-file.md). A target-specific or store-specific flow can override the main one. Run `listing-kit plan check --for capture` once the flows exist.

## Build and select the device

Install the app before capture. For Expo and React Native, use a build with bundled JS. Clearing state on a dev client can erase its saved Metro URL. For Flutter on an iOS simulator, use the self-contained debug build described in the [Flutter reference](../stacks/flutter.md).

Automated capture needs Maestro and JDK 17+. The capture command selects the device and passes its UDID or serial to Maestro. To try a flow by itself, pass the same device to `maestro --device DEVICE test FLOW.yaml` and supply any variables the flow uses. Use Maestro Studio to inspect accessible controls. On Flutter, expose semantics for custom controls you need to tap.

## Write a flow

Capture sets four Maestro variables with `-e`. `LK_APP_ID` identifies the installed app. `LK_LOCALE` is the store-specific device locale. `LK_TARGET` and `LK_SCREEN` are plan IDs. A literal appId in the flow must match the job. A variable carries the requested locale to your flow. Your app or flow must actually apply it.

This recipe assumes the app implements the three demo launch arguments and has a populated library. Adapt it to your app. Variable expansion in the appId header, the permission grant after a state clear, launch arguments and orientation still need verification on the target device.

```yaml
appId: ${LK_APP_ID}
---
- launchApp:
    clearState: true
    permissions: {all: allow}
    arguments:
      demoLocale: ${LK_LOCALE}
      demoTarget: ${LK_TARGET}
      demoScreen: ${LK_SCREEN}
- setOrientation: LANDSCAPE_LEFT
- tapOn: "Library"
- assertVisible: "My Books"
```

Choose the orientation for the target and assert on an actual item in the requested language. Use seeded data or the app's demo login if a fresh launch shows an empty list.

If login is needed, have the user export `MAESTRO_DEMO_PASSWORD` in the shell that runs capture. They can keep the export in git-ignored `.listing-kit/secrets.local` and source it themselves. Maestro inherits the exported shell environment. Capture does not load that file. Reference the variable as `${MAESTRO_DEMO_PASSWORD}` in the flow. Never type the value into YAML, read it or print it.

On iOS the kit terminates the app and launches its bundle ID directly before each flow or manual prompt. Navigate within the app after that launch. Following a deep link from Settings or another app can put a “◀ Settings” or similar return link beside the clock. The status-bar override sets the time and leaves that link visible. Tap accessible labels in the app to reach the screen. Handle permission dialogs in the flow. If `expo run:ios` leaves an “Open in app?” alert after install, reboot the simulator before capture.

On iPadOS 26, a curved gray handle in the lower-right corner indicates Windowed Apps mode. If present, record the current mode in Settings → Multitasking & Gestures, select Full Screen Apps, return to the Home Screen and run capture. Restore the original mode afterwards. In the review page, expand **Inspect raw status bars** to check the left edge of each Apple capture. On Xcode 27.2, `simctl status_bar` can fix the clock but has no option to hide the iPad date.

After a successful flow, capture sanitizes the status bar and reads the display with simctl or adb. The default Maestro timeout is 600 seconds and other capture tools get 120 seconds. `LK_CAPTURE_TIMEOUT` and `LK_TOOL_TIMEOUT` override those limits in seconds. Inspect the reported log under `.listing-kit/logs/` for a failed flow. [Maestro launchApp](https://docs.maestro.dev/api-reference/commands/launchapp) · [Maestro setOrientation](https://docs.maestro.dev/api-reference/commands/setorientation)

## Manual navigation

Run `listing-kit capture --manual --target ID --screen ID` in an attended session. The app must be installed and the selected flow file must exist. Capture skips Maestro for the selected jobs. Navigate to each requested state and press Enter to take its screenshot. End of input fails the job.

The plan has no manual flag. An unfiltered capture tries every flow. For unattended runs, select only automated screens with `listing-kit capture --target ID --screen ID`. Repeat the screen option to select more screens on that target. Report the manual images still needed.
