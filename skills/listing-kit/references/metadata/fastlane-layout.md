# Where the listing lives

Resolve these paths from the app root. In a monorepo, each mobile app can have its own listing. Use UTF-8 text, lower-case image extensions and numbered screenshot filenames to keep gallery order.

| Content | Default source path |
| --- | --- |
| Apple app-wide fields | `fastlane/metadata/copyright.txt`, `primary_category.txt` and `secondary_category.txt` in the same directory |
| Apple localized copy | `fastlane/metadata/<locale>/<field>.txt`, including `name.txt`, `subtitle.txt`, `description.txt`, `keywords.txt` and the URL fields |
| Apple fastlane screenshots | `fastlane/screenshots/<locale>/`, with a slot subfolder where the rules specify one |
| Apple headers | `store-assets/apple/<locale>/` |
| Play localized copy | `fastlane/metadata/android/<locale>/title.txt`, `short_description.txt`, `full_description.txt` |
| Play release notes | `fastlane/metadata/android/<locale>/changelogs/<versionCode>.txt` or `default.txt` |
| Play fastlane screenshots | `fastlane/metadata/android/<locale>/images/<slot folder>/`, for example `phoneScreenshots/` |
| Play graphics | `icon.png`, `featureGraphic.png` and any `tvBanner` file directly under the locale's `images/` |
| Console screenshot targets | `store-assets/<store>/<store code>/screenshots/<slot id>/` |

Use the [Apple](../stores/apple-app-store.md) and [Play](../stores/google-play.md) tables for the full field lists, slot folders and routes. Apple localized fields can inherit from `metadata/default/`.

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

Setup saves paths supplied through its key-path options in private `.listing-kit/local.json`. This file can also hold device pins. Keep store key files outside the whole repository. The agent may help set a path but must never request, open or print the credential contents.

## Apple asset plan

Existing listings can have `.listing-kit/asset-plan.json`. The validator, review and handoff read its Apple locale entries for screenshot counts, headers and `deferredScreenshots` reasons. Use the display labels from the Apple table here. The format-2 listing plan uses slot IDs and drives capture and compose. Keep any existing Apple asset plan consistent with the approved coverage.

## Store management

`listing-kit fastlane setup` uses the selected app's download actions to check access. Identify the store with `--store apple` or `--store play`. With no plan, supply the Apple `--app-identifier` or Play `--package-name`. The environment variables `APP_STORE_CONNECT_API_KEY_PATH` and `SUPPLY_JSON_KEY` can supply the external paths. See [credentials](../../../../docs/CREDENTIALS.md).

`listing-kit pull` updates nonconflicting text, records hashes in `.listing-kit/remote.lock.json` and saves screenshot references under `.listing-kit/remote/<store>/`. When both sides changed a field, the working file stays in place and the downloaded copy goes under that reference directory. Review the two versions before merging.

`listing-kit publish` validates a scratch copy, compares it with the store and prints a summary and proposed command for comparable changes. Fastlane uses deliver for Apple and supply for Play. The preview identifies gallery replacement scope. Apple replacement affects all screenshot sets in an uploaded locale. The adapter leaves console slots and Play listing graphics for hand upload. Both store upload gates are off in this version pending live tests.

`listing-kit handoff --open` builds a copy in `.listing-kit/upload/` with Apple and Play folders, ordered screenshots, text and graphics. Open `INDEX.html` or read `INDEX.md` for destinations, missing items and omissions. Edit the source listing. Handoff refuses to replace a modified or unrecognized upload folder.

Capture, compose and the fastlane adapter use the manifest's split roots. Standalone validate, review, the review hook and handoff expect conventional listing paths. For split projects, stage public files into the conventional layout in a separate app folder before standalone review or handoff. Include platform declarations, any effective rules override and the Apple asset plan for validation. Check the folder against the manifest before delivery.
