# Metadata layout (fastlane-compatible)

listing-kit writes to fastlane's `deliver` (iOS) and `supply` (Android) trees so
existing publishing tooling works without translation. Keep a single internal
notion of "the listing" and write **both** layouts from it.

## iOS — `fastlane/metadata/`
```
fastlane/metadata/
  copyright.txt
  primary_category.txt
  <locale>/                         # e.g. en-US
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
    images/
      icon/             featureGraphic/
      phoneScreenshots/ sevenInchScreenshots/ tenInchScreenshots/ wearScreenshots/
```

The community `universal_metadata` fastlane plugin is **prior art** for this
mapping — a reference, not a dependency.

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
  Ensure `.listing-kit/` is git-ignored (it is in this repo's `.gitignore`; add
  it to the *target* repo's `.gitignore` too).
- **Assemble asserts the boundary:** before finishing, run
  `scripts/lib/secret-scan.sh` over the written `fastlane/` tree and **fail the
  run** if any credential/high-entropy token leaked into a committed file.
