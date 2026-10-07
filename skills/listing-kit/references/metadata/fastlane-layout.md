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

Use the exact display-class labels in `scripts/lib/apple-screenshot-sizes.tsv`.
Counts are the approved number (1–10) in that class and locale; the validator
requires a match. Header entries are lower-case PNG/JPEG basenames within that
locale's creative-assets folder. Either `screenshots` or `headers` may be omitted
when only the other is planned. Do not put deferred targets or credentials here.
Update the plan when the user changes scope. Without a plan, validation checks
store minimums and present images but cannot prove that every requested set exists.

Keep numeric screenshot prefixes and a distinct device suffix, e.g.
`01_home_iphone-medium.png` and `01_home_ipad.png`. Label the exact console slot
in the review/handoff. If creating a ZIP, include headers and the plan, and check
its file inventory and contents against the validated source tree.

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
