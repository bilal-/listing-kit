# Troubleshooting

Match the message or excerpt to the command that printed it. Paths, IDs and dimensions in the full message come from your app.

| Command and message excerpt | Fix |
| --- | --- |
| `listing-kit doctor`: `MISSING .listing-kit/listing.json` | Work from the app root. Create the [format-2 plan](../skills/listing-kit/references/plan-file.md), then run `listing-kit plan check` for field-level errors. |
| `listing-kit plan check`: `deferred targets need a non-empty, single-line reason` | Add a reason to the deferred target explaining why it cannot be captured. |
| `listing-kit plan check`: `missing input file:` | Correct the path or create the flow or asset. Capture requires the selected jobs' flow files even in manual mode. |
| `listing-kit capture`: `No available simulator matches` | Compare the requested device type and runtime with the available types in the message. Install or select the matching simulator. |
| `listing-kit capture`: `Expected one emulator matching` | Start the matching Android emulator. Pin a serial with `listing-kit capture --device SERIAL` if several are running. |
| `listing-kit capture`: `Please build and install it first` | Install the app with the planned bundle ID or package name on the selected device, then rerun capture. |
| `listing-kit capture`: `A raw upload requires the exact target size` | Select a device profile with the planned dimensions and set the planned orientation in the flow. |
| `listing-kit compose`: `no raw capture at` | Run capture for the named target and screen. Check the output mapping with `listing-kit plan outputs`. |
| `listing-kit compose`: `no font given for headline` | Add headline and detail font lists in `style.fonts.default`. Use `bundled:Inter` or readable local font files. |
| `listing-kit compose`: `framed screenshots need Chrome, Chromium, Edge or Brave` | Install a supported browser or set `LK_BROWSER` to its executable. When set, only that executable is used. |
| `listing-kit compose`: `was not written by listing-kit` | Inspect the destination. Move it aside to preserve it. Use `listing-kit compose --adopt` only after approving its replacement. |
| `listing-kit compose`: `existing file(s) would be restyled` | Review the affected paths and design. Use `listing-kit compose --restyle` to accept the redraw. |
| `listing-kit validate`: `ImageMagick not available: images were checked structurally only` | Install ImageMagick and rerun validation for full image checks. |
| `listing-kit review`: `No listing directories under:` | Run `listing-kit detect` in the intended app. Place listing files in the Apple and Play paths it prints. See [directory selection](../skills/listing-kit/references/metadata/fastlane-layout.md#choosing-the-app-and-fastlane-directories). |
| `listing-kit handoff`: `contains unexpected or modified entries` | Save your changes outside the generated upload directory. Apply intended edits to the source listing, move the modified directory aside and rebuild. |
| `listing-kit fastlane setup`: `Credential is inside the repository` | Move the key outside the whole repository and supply only its new path. [Credential storage](CREDENTIALS.md) |
| `listing-kit publish`: `Missing planned screenshot:` | Restore or compose the named active output and rerun validation. |
| `listing-kit publish`: `until it has passed a live test` | Use `listing-kit handoff --open` for delivery. The default publish run writes no upload receipt. Read the preview in the job log. |

If the review hook flags a public key in a device declaration, follow the [staged blob review procedure](../skills/listing-kit/references/metadata/fastlane-layout.md#what-to-commit).

### Fastlane failures

After the failure category, `listing-kit: fastlane said: [!] …` shows fastlane’s final marked error on stderr. The kit strips terminal formatting, redacts credentials, email addresses and long token-like strings, and limits the detail to 300 characters. A hit from the kit’s secret detector replaces the whole message with `[redacted]`. If there is no usable marked error or the final safety check flags the result, only the category appears. Captured API requests and responses stay private. The Apple text writer keeps its own diagnostics.

If supply cannot find the requested track, rerun with `--track <track>` using the track’s Play Console name. If several releases share the track, or supply cannot find the release for a changelog, rerun with `--version-code <code>` using the intended release’s version code. [Fastlane 2.242.0 track and release lookup](https://github.com/fastlane/fastlane/blob/2.242.0/supply/lib/supply/uploader.rb#L97-L99), [multiple-release error](https://github.com/fastlane/fastlane/blob/2.242.0/supply/lib/supply/uploader.rb#L125-L127), [missing changelog version code](https://github.com/fastlane/fastlane/blob/2.242.0/supply/lib/supply/uploader.rb#L269)

## Browser launch flags

Set `LK_BROWSER_ARGS` to pass additional space-separated arguments to the browser. For example, an isolated Linux CI runner that cannot start Chrome with its sandbox can use `LK_BROWSER_ARGS=--no-sandbox`.
