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

The failure category and exit status appear on stderr. Supply and deliver errors select fixed kit messages. A verbose response body can match a signature, so use the message as a troubleshooting hint. For an unrecognised error, run the underlying fastlane command locally to inspect its output.

| Failure | What to do | Source in fastlane 2.242.0 |
| --- | --- | --- |
| Play track missing | Use the Play Console track name with `--track <track>`. | [Supply track lookup][track], [Google track response][google-track] |
| Multiple Play releases on the track | Select the intended release with `--version-code <code>`. | [Supply release selection][releases] |
| Play release missing for the supplied version code | Check the intended release’s version code in Play Console and pass it with `--version-code <code>`. | [Supply release lookup][release] |
| Play changelog needs a version code | Pass the release’s version code with `--version-code <code>`. | [Supply changelog][changelog] |
| Play requires automatic submission for review | If you accept automatic submission, rerun the held publish with `--send-for-review`. | [Supply edit commit][review] |
| Play caller lacks permission, is forbidden or receives HTTP 401 or 403 | Check the service account’s Play Console permissions for the app. | [Supply forbidden fixture][forbidden], [Google error handling][google] |
| Play package missing | Check `--package-name` against the application ID in Play Console. | [Google error handling][google] |
| Play edit expired, deleted or conflicted | Rerun the command to start a fresh edit. | [Google error handling][google] |
| Play draft app requires a draft release | Set the release status to draft in Play Console. | [Google error handling][google] |
| Apple has no editable version | Prepare an editable version in App Store Connect. | [Deliver screenshot download][screenshots], [version lookup][edit-version], [localization update][locales] |
| App Store Connect rejected the API key | Check the key ID, issuer ID and private key. | [Spaceship token refresh][token], [401 handling][unauthorized], [Apple error formatting][apple-error] |

Google supplies the wording for permission, package, edit and draft-app errors at runtime. The Google error-handling link identifies where Supply reads and emits that message or raw response body. The tagged source contains the track and forbidden response examples.

[track]: https://github.com/fastlane/fastlane/blob/2.242.0/supply/lib/supply/uploader.rb#L98
[google-track]: https://github.com/fastlane/fastlane/blob/2.242.0/supply/lib/supply/client.rb#L520
[releases]: https://github.com/fastlane/fastlane/blob/2.242.0/supply/lib/supply/uploader.rb#L126
[release]: https://github.com/fastlane/fastlane/blob/2.242.0/supply/lib/supply/uploader.rb#L99
[changelog]: https://github.com/fastlane/fastlane/blob/2.242.0/supply/lib/supply/uploader.rb#L269
[review]: https://github.com/fastlane/fastlane/blob/2.242.0/supply/lib/supply/client.rb#L231
[forbidden]: https://github.com/fastlane/fastlane/blob/2.242.0/supply/spec/client_spec.rb#L278-L284
[google]: https://github.com/fastlane/fastlane/blob/2.242.0/supply/lib/supply/client.rb#L115-L138
[screenshots]: https://github.com/fastlane/fastlane/blob/2.242.0/deliver/lib/deliver/download_screenshots.rb#L25
[edit-version]: https://github.com/fastlane/fastlane/blob/2.242.0/deliver/lib/deliver/upload_metadata.rb#L445
[locales]: https://github.com/fastlane/fastlane/blob/2.242.0/deliver/lib/deliver/upload_metadata.rb#L559
[token]: https://github.com/fastlane/fastlane/blob/2.242.0/spaceship/lib/spaceship/connect_api/api_client.rb#L180-L188
[unauthorized]: https://github.com/fastlane/fastlane/blob/2.242.0/spaceship/lib/spaceship/connect_api/api_client.rb#L243-L244
[apple-error]: https://github.com/fastlane/fastlane/blob/2.242.0/spaceship/lib/spaceship/connect_api/api_client.rb#L346-L347

## Browser launch flags

Set `LK_BROWSER_ARGS` to pass additional space-separated arguments to the browser. For example, an isolated Linux CI runner that cannot start Chrome with its sandbox can use `LK_BROWSER_ARGS=--no-sandbox`.
