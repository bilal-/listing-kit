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

## Secrets boundary (§9.1) — READ THIS
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
