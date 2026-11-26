# Where the listing lives

Resolve these paths from the app root. In a monorepo, each mobile app can have its own listing. Use UTF-8 text, lower-case image extensions and numbered screenshot filenames to keep gallery order.

## Choosing the app and fastlane directories

Run `listing-kit detect <app-root>` before reading or writing a listing. It prints
app-relative `fastlaneDir`, `metadata`, `screenshots`, and `storeAssets` paths
for each store. If the root has no listing content or explicit `trees` and detect finds child
apps, select one of the reported candidates and run detect there. To keep the
listing at the workspace root, set `trees` in its plan.

The fastlane directories below are relative to the selected app. A dash means
the platform is absent or the app still needs to be selected.

| Layout | App directory | Stores or candidates | Apple fastlane directory | Play fastlane directory |
| --- | --- | --- | --- | --- |
| expo-managed | . | apple play | fastlane | fastlane |
| expo-prebuild | . | apple play | fastlane | fastlane |
| react-native-bare | . | apple play | ios/fastlane | android/fastlane |
| flutter | . | apple play | fastlane | fastlane |
| native-ios | . | apple | fastlane | — |
| native-android | . | play | — | fastlane |
| monorepo-siblings | workspace root | choose apps/android apps/ios | — | — |
| monorepo-siblings | apps/ios | apple | fastlane | — |
| monorepo-siblings | apps/android | play | — | fastlane |
| monorepo-js | workspace root | choose apps/mobile | — | — |
| monorepo-js | apps/mobile | apple play | fastlane | fastlane |
| existing-root-fastlane | . | apple play | fastlane | fastlane |
| root-listing-build-ios | . | apple play | fastlane | fastlane |
| android-lanes-only | . | apple play | fastlane | android/fastlane |
| duplicate-apple | . | choose Apple trees | — | — |

The selected app's `.listing-kit/listing.json` can specify individual paths in
`trees`. Explicit paths take precedence, including at a workspace root. For
each remaining fastlane directory, compare `fastlane` with `ios/fastlane`
for Apple or `android/fastlane` for Play.

| Evidence for this store | Directory selected |
| --- | --- |
| Listing text or screenshots in one candidate | The directory containing the files |
| Listing content in both candidates | Stop and set `trees.apple.fastlaneDir` or `trees.play.fastlaneDir` |
| Neither has content for this store, root has listing content for the other store | `fastlane` |
| Neither has content, root has a Fastfile | `fastlane` |
| Neither has content, only the native candidate has a Fastfile | That store's native fastlane directory |
| Neither has content or a Fastfile | `fastlane` |

Run project fastlane lanes from the directory containing the selected
`fastlane/`, such as `ios/` for a split Apple tree. The kit's setup, pull and
publish commands look for a fastlane Gemfile in the selected fastlane
directory, its parent and the app root, in that order. They invoke deliver and
supply from a clean temporary directory with explicit paths.

| Content | Resolved source path |
| --- | --- |
| Apple app-wide fields | `<apple.metadata>/copyright.txt`, `primary_category.txt` and `secondary_category.txt` in the same directory |
| Apple review contact and notes | Optional `first_name.txt`, `last_name.txt`, `phone_number.txt`, `email_address.txt` and `notes.txt` under `<apple.metadata>/review_information/`. Enter demo credentials in App Store Connect or keep them outside the repo. |
| Apple localized copy | `<apple.metadata>/<locale>/<field>.txt`, including `name.txt`, `subtitle.txt`, `description.txt`, `keywords.txt` and the URL fields |
| Apple fastlane screenshots | `<apple.screenshots>/<locale>/`, with a slot subfolder where the rules specify one |
| Apple headers | `<apple.storeAssets>/<locale>/` |
| Play localized copy | `<play.metadata>/<locale>/title.txt`, `short_description.txt`, `full_description.txt`, and optional `video.txt` |
| Play release notes | `<play.metadata>/<locale>/changelogs/<versionCode>.txt` or `default.txt` |
| Play fastlane screenshots | `<play.metadata>/<locale>/images/<slot folder>/`, for example `phoneScreenshots/` |
| Play graphics | `icon.png`, `featureGraphic.png` and any `tvBanner` file directly under the locale's `images/` |
| Console screenshot targets | `<store.storeAssets>/<store code>/screenshots/<slot id>/` |

Use the [Apple](../stores/apple-app-store.md) and [Play](../stores/google-play.md) tables for the full field lists, slot folders and routes. Apple localized fields can inherit from `<apple.metadata>/default/`.

## Split fastlane roots

In the [plan](../plan-file.md), set `trees.apple.fastlaneDir` to `ios/fastlane` and `trees.play.fastlaneDir` to `android/fastlane` for a split project. Each store can override its `metadata` directory. Apple can also override `screenshots`. Set `trees.storeAssets` to change the shared creative root. All explicit paths are app-relative, including metadata overrides. Inspect the resolved paths with `listing-kit plan manifest`.

## What to commit

Commit the plan, saved flows, public copy, graphics and final screenshots. Keep the source captures and brand inputs available for anyone who needs to reproduce the images. Commit `.listing-kit/compose.lock.json` (input keys, output hashes and renderer details) and `.listing-kit/outputs.json` (the inventory of written paths) with the images. When a planned path disappears, compose moves unchanged owned output into `.listing-kit/held/` under its old relative path. Inspect held files before archiving them. Compose leaves manually changed stale files in place.

Ignore local state in the app's gitignore. Keep the plan and flows trackable.

```gitignore
.listing-kit/local.json
.listing-kit/upload/
.listing-kit/logs/
.listing-kit/compose.flock
.listing-kit/*.local
```

The `*.local` rule above keeps `.listing-kit/secrets.local` out of Git. The user can source it before capture to export a demo login. [Flow variables](../driving/maestro.md#write-a-flow)

Setup saves paths supplied through its key-path options in private `.listing-kit/local.json`. This file can also hold device pins. Keep store key files outside the whole repository. The agent may help set a path but must never request, open or print the credential contents.

If the staged review hook blocks a commit, fix the finding and commit again. Never bypass the scan with `--no-verify`. If the user confirms a flagged key in a device declaration is public, review the staged file. For a reviewed `app.json` at the repository root, record the exception from that directory.

```sh
git config --local --add listingKit.reviewedDeviceBlob "$(git rev-parse :app.json) app.json"
```

For another declaration, use its repository-relative path in both places. The exception covers only that staged blob at that path. Review it again after an edit.

## Listing coverage

New listings commit only [listing.json](../plan-file.md) for asset coverage. Each active target contributes one screenshot per applicable screen in each selected store locale. Apple graphics supply the expected header filenames. To postpone an optional Apple display, mark its target `deferred` and give a single-line reason. Review and handoff show that reason. Validation fails when a required display is deferred.

**Older listings.** When `.listing-kit/asset-plan.json` is the only plan, the kit still reads its Apple counts, header filenames and deferral reasons. When both files exist, validation uses `listing.json` and lists any older declarations missing from the new plan.

## Store management

Before the first pull, configure the external key path and run `listing-kit fastlane setup --store apple` or `listing-kit fastlane setup --store play`. Setup checks download access. Use the same store selection for pull and publish. Without a plan, Apple needs `--app-identifier` and Play needs `--package-name` on each command. The environment variables `APP_STORE_CONNECT_API_KEY_PATH` and `SUPPLY_JSON_KEY` can supply the key paths. [Worked commands](../../../../docs/GUIDE.md#sync-an-app-you-own) · [Credentials](../../../../docs/CREDENTIALS.md)

`listing-kit pull` updates nonconflicting text, records hashes in `.listing-kit/remote.lock.json` and saves screenshot references under `.listing-kit/remote/<store>/`. When both sides changed a field, the working file stays in place and the downloaded copy goes under that reference directory. Review the two versions before merging.

`listing-kit publish` validates a scratch copy, compares it with the store and prints a summary and proposed command for comparable changes. Fastlane uses deliver for Apple and supply for Play. The preview identifies gallery replacement scope. Apple replacement affects all screenshot sets in an uploaded locale. The adapter leaves console slots and Play listing graphics for hand upload. Publishing does not upload by default. Agents must never pass `--yes` or set `LK_PUBLISH_UNVERIFIED`, the maintainers' live-test switch.

`listing-kit handoff --open` builds a copy in `.listing-kit/upload/` with Apple and Play folders, ordered screenshots, text and graphics. Open `INDEX.html` or read `INDEX.md` for destinations, missing items and omissions. Edit the source listing. Handoff refuses to replace a modified or unrecognized upload folder.

## Standalone tools with split roots

Validate, review, handoff and the staged review hook use the resolved paths for each store. Run the commands from the selected app, or pass its directory.
