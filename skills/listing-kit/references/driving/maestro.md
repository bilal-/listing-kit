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

On iOS prefer tapping accessible labels when a custom-scheme link opens a system confirmation dialog. Handle any permission dialogs in the flow. If `expo run:ios` leaves an “Open in app?” alert after install, reboot the simulator before capture. On iPadOS 26, select Full Screen Apps in the simulator to hide the window grabber. Inspect the raw PNG for overlays even if capture passes.

After a successful flow, capture sanitizes the status bar and reads the display with simctl or adb. The default Maestro timeout is 600 seconds and other capture tools get 120 seconds. `LK_CAPTURE_TIMEOUT` and `LK_TOOL_TIMEOUT` override those limits in seconds. Inspect the reported log under `.listing-kit/logs/` for a failed flow. [Maestro launchApp](https://docs.maestro.dev/api-reference/commands/launchapp) · [Maestro setOrientation](https://docs.maestro.dev/api-reference/commands/setorientation)

## Manual navigation

Use `listing-kit capture --manual --target ID --screen ID` when a screen cannot be reached through the accessibility tree. Capture still requires the installed app and the selected flow file. Navigate to the populated state, then press Enter at the prompt. Skip manual jobs in unattended runs and report the missing images.
