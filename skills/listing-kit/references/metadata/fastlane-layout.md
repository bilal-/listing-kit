# Metadata layout (fastlane-compatible)

listing-kit writes to fastlane's `deliver` (iOS) and `supply` (Android) trees so
existing publishing tooling works without translation. Keep a single internal
notion of "the listing" and write **both** layouts from it.

## Where the tree lives: the APP ROOT, not the repo root

`fastlane/` (and `.listing-kit/`) live at the **mobile app's root directory** — the
directory that holds the app manifest the Detect step found (`app.json`/`package.json`
for RN/Expo, `pubspec.yaml` for Flutter, the `*.xcodeproj`/`*.xcworkspace` for native
iOS, `build.gradle` for native Android). All paths below are **relative to that app
root.**

- **Single-app repo:** the app root *is* the repo root → `./fastlane/`.
- **Monorepo:** the app root is a subdirectory → e.g. `apps/mobile/fastlane/`,
  `packages/app/fastlane/`. Do **not** write to the repo root.
- **Multiple apps** in one repo: each app gets its own `fastlane/` under its own root;
  confirm which app(s) to target during Detect/Plan.

`fastlane`'s own `deliver`/`supply` also expect to be run from the app directory, so
this keeps the output directly usable. (This repo's own example follows the rule:
`examples/expo-recipe-box/fastlane/` is at the *app* root, not the repo root.)

For hand upload, the builder copies listing files to `.listing-kit/upload/`. Open `INDEX.html` there for console instructions.

## iOS — `fastlane/metadata/`
```
fastlane/metadata/
  copyright.txt
  primary_category.txt  secondary_category.txt
  <locale>/                         # e.g. en-US (or default/ = fallback for all locales)
    name.txt  subtitle.txt  promotional_text.txt
    description.txt  keywords.txt
    marketing_url.txt  support_url.txt  privacy_url.txt
    release_notes.txt
fastlane/screenshots/<locale>/      # iPhone / iPad / Watch PNGs
```

## Apple creative assets

`store-assets/apple/<locale>/` contains Header Asset image variants. This is
listing-kit's source layout for manual App Store Connect upload, separate from
Fastlane's screenshot tree. The validator and review page include this folder.

### Apple asset plan

Persist approved Apple coverage in `.listing-kit/asset-plan.json` at the app root:

```json
{
  "apple": {
    "en-US": {
      "screenshots": {
        "iPhone Dynamic Island (medium display)": 5,
        "iPad 13\"": 5
      },
      "headers": ["header-16x9.png", "header-21x9.png"]
    }
  }
}
```

Use the exact display-class labels in the [Apple screenshot table](../stores/apple-app-store.md#screenshots).
Counts are the approved number within the slot’s limits in that class and locale; the validator
requires a match. Header entries are lower-case PNG/JPEG basenames within that
locale's creative-assets folder. Either `screenshots` or `headers` may be omitted
when only the other is planned.

Optional `deferredScreenshots` maps display-class labels to a nonempty, single-line
reason (up to 500 characters), for example:

```json
{
  "apple": {
    "en-US": {
      "screenshots": {
        "iPhone Dynamic Island (medium display)": 5
      },
      "headers": [
        "header-16x9.png"
      ],
      "deferredScreenshots": {
        "iPhone Duo": "Xcode 27.1 and a compatible Duo runtime are unavailable."
      }
    }
  }
}
```

Keep a deferred class out of `screenshots`; an active/deferred conflict fails
validation. Deferrals produce warnings and a visible review notice, and hide any
retained screenshots of that class from the active gallery without deleting them.
They never waive store-required screenshot classes. Capture and archive only
active targets; do not recursively include retained deferred screenshots in a
delivery ZIP. Keep credentials out of the plan. Update the plan when the user changes scope. Without a plan, validation checks
store minimums and present images but cannot prove that every requested set exists.

Keep numeric screenshot prefixes and a distinct device suffix, e.g.
`01_home_iphone-medium.png` and `01_home_ipad.png`. Label the exact console slot
in the review/handoff. If creating a ZIP, include headers and the plan, and check
its file inventory and contents against the validated source tree.
Exclude incidental hidden files and folders such as `.DS_Store`, editor backups
and temporary capture directories. Include the approved plan explicitly rather
than recursively archiving all hidden files. Reopen the final ZIP and verify the
actual inventory and bytes after filtering; image validation alone does not
audit archive metadata.

## Android — `fastlane/metadata/android/`
```
fastlane/metadata/android/
  <locale>/                         # e.g. en-US
    title.txt  short_description.txt  full_description.txt
    changelogs/<versionCode>.txt    # or changelogs/default.txt
    images/
      icon.png          featureGraphic.png   # files, not folders (supply ignores folders)
      phoneScreenshots/ sevenInchScreenshots/ tenInchScreenshots/
      tvScreenshots/    wearScreenshots/
```

The community `universal_metadata` fastlane plugin is **prior art** for this
mapping — a reference, not a dependency.

## File names
Use **lower-case** extensions (`.png`, `.jpg`, `.jpeg`): fastlane globs for those, so on
a case-sensitive filesystem (Linux CI) `01_home.PNG` is silently never uploaded. The
validator fails upper-case extensions. Copy files must be UTF-8. Locale values can
fall back to `metadata/default/` (deliver) for fields a locale doesn't override.

## Screenshot ordering (important)
Both `deliver` and `supply` derive on-store display order from the **filename
sort order**. Encode the curated order (Curate step) as a numeric prefix:
`01_home.png`, `02_library.png`, `03_reader.png`, … This is what makes "the first
screenshot matters most" actually hold on the store.

## Secrets boundary — READ THIS
The committed tree is the source of truth **for non-secrets only**.

- **Committed:** copy, keywords, URLs, copyright, screenshots, generated graphics
  — everything that *is* the public listing.
- **NEVER committed:** login credentials, API tokens, seed-data secrets, mock
  auth tokens. These live in a git-ignored `.listing-kit/secrets.local` or
  environment variables, and are **referenced — not inlined** — by Maestro flows.
  Add `.listing-kit/secrets.local` (or `*.local`) to the *target* repo's `.gitignore`.
  Do **not** ignore all of `.listing-kit/`: the flows in `.listing-kit/flows/` are
  committed so reruns and CI can replay them, and the secret scan checks them.
- **Assemble asserts the boundary:** before finishing, run
  `scripts/lib/secret-scan.sh` over the written `fastlane/` tree and **fail the
  run** if any credential/high-entropy token leaked into a committed file.

## Store management

An editable App Store Connect version is required. On Play, upload the first build in Play Console. Run the skill's `scripts/listing-kit` executable from the app root, or pass `--app-root DIR`. Adding the skill's `scripts` directory to PATH makes the following commands available.

```sh
listing-kit fastlane setup --store apple --apple-api-key-path /private/keys/asc.json
listing-kit fastlane setup --store play --play-json-key-path /private/keys/play.json
listing-kit pull --store apple
listing-kit publish --store play --track production --version-code 42
listing-kit handoff .
```

With a plan, app IDs and paths come from its manifest. Without a plan, supply `--app-identifier ID` or `--package-name ID`. Omitting `--store` selects active stores in the plan, or existing store trees on disk. Use an explicit store and ID to bootstrap an empty app. For first-time initialization, confirm the IDs before choosing targets or flows. After the initial download, run the skill's Init, Detect and Plan steps using the downloaded text. Subsequent pulls preserve that plan.

**Setup.** Keep the App Store Connect API key JSON and Play service-account JSON outside the Git repository, including its ignored directories. Setup stores their paths in the ignored, mode-600 `.listing-kit/local.json`. The environment variables `APP_STORE_CONNECT_API_KEY_PATH` and `SUPPLY_JSON_KEY` override saved paths. Each check exercises the selected app's download actions. A Gemfile mentioning fastlane in the store's fastlane directory or app root selects Bundler. Use `scripts/lib/secret-scan.sh --store-credentials REPO_ROOT` to run the same repository-wide credential-file check separately.

**Pull.** Apple reads the editable version selected by deliver. Play reads listing text and gallery files using supply, with release notes from the selected track. On tracks with multiple releases, supply 2.242.0 can return notes for the first release. Inspect the downloaded version codes before editing notes. Pull records SHA-256 hashes in `.listing-kit/remote.lock.json` and keeps screenshot references in `.listing-kit/remote/<store>/`. When both sides edit a field, pull exits 1 and saves the store's version under that reference directory. Copy it into the working field to accept the store value, or keep the local field for the publish comparison. An omitted download leaves the local file in place.

**Publish and hand-upload checklist**

1. Run `listing-kit publish`. Check the credential filename, app, editable-version selector or Play track, locale, field changes and replacement counts. With a plan, the validation copy uses active target outputs and locales. Resolve any validation failure first.
2. Review the proposed command. Publish compares local screenshots with their last pull or publish baseline. A group without a local baseline is listed as “never published from this repo.” To include it, pass `--screenshots <store>:<locale>[:<group>]` using the group name in the preview. Matching galleries are skipped. Review the ordered filenames, content digests, and change markers before approving. Later store-only differences are reported for review with `pull`. Publish skips the `default/` metadata and screenshot directories. A changed Play slot replaces its images in filename order. Apple replaces **every set for each uploaded locale**, including hand uploads. The preview includes the sets it must restore. Uncomparable slots and protected console galleries are identified for hand upload.
3. For an enabled store, type `yes` or pass `--yes` for noninteractive approval. Review `.listing-kit/publish.approved.json` for the approved hashes and `.listing-kit/publish.receipt.json` for pending and completed operations. If another editor changes the baseline, rerun for a fresh comparison. Downloads time out after 300 seconds and uploads after 900 seconds. Set `LK_FASTLANE_TIMEOUT` in seconds to override either limit. Before fastlane starts an upload, the receipt records its approved manifest. After an interruption or timeout, publish reads the store again. A match completes the receipt and advances the baseline. An ambiguous result holds screenshot uploads for the affected locale. Inspect the store, run `listing-kit publish --resolve <store>` with the same app and track, and confirm interactively to close the pending operation. Run publish again to approve any remaining changes. Supply sends release notes only when the download establishes the full locale set for the requested `--version-code`. Each version-specific file takes precedence over the locale's `default.txt`, including an empty version-specific file.
4. After the automatic operation, run `listing-kit handoff .`. Open `.listing-kit/upload/INDEX.html` for the remaining console entries, Apple hand-upload slots, Play icon and feature graphic. For a disabled store the folder covers the whole manual transfer.

**Maintainer live gate.** Both stores ship with writes disabled. On disposable app records, record the current version or track, builds, review state, listing text, all gallery slots and their image order, icon and feature graphic. Seed a hand-uploaded slot. Select a single store. Set `LK_PUBLISH_UNVERIFIED=apple:<app id>` or `LK_PUBLISH_UNVERIFIED=play:<package name>` for that command and publish one changed title. Read the listing back and compare all recorded values. Next change one screenshot, confirm the previewed replacement scope, publish and read back. Exercise the Apple console-slot refusal and verify the hand-uploaded slot survives. On Play run both tests on a draft app and a published app. Enable a store in `PUBLISH_ENABLED` only after its maintainer has recorded the successful checks. The credential-free gem contract runs separately in CI.
