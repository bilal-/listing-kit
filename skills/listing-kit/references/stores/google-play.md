# Google Play — requirements reference

The tables below are generated from `specs/stores.json`. Record app-specific differences and their source URLs in `.listing-kit/specs.override.json`.

## Screenshots

<!-- rules:begin screenshots -->

| Display class | Requirement | Count per locale | Accepted size or bounds | Format | Delivery and notes |
| --- | --- | --- | --- | --- | --- |
| Phone | Required if the app runs on Android phones | 2–8 | sides 320–3840 px, up to 2.3:1 | PNG/JPEG, 8 bits/channel, no alpha, ≤8,388,608 bytes | Promotion: 4 at ≥1080 px, 9:16 or 16:9. phoneScreenshots |
| 7-inch tablet | Optional | 0–8 | sides 320–7680 px, up to 2.3:1 | PNG/JPEG, 8 bits/channel, no alpha | Promotion: 4 at 1080–7680 px, 16:9 or 9:16. sevenInchScreenshots |
| 10-inch tablet | Optional | 0–8 | sides 320–7680 px, up to 2.3:1 | PNG/JPEG, 8 bits/channel, no alpha | Promotion: 4 at 1080–7680 px, 16:9 or 9:16. tenInchScreenshots |
| Chromebook | Optional | 0–8 | sides 320–7680 px, up to 2.3:1 | PNG/JPEG, 8 bits/channel, no alpha | Promotion: 4 at 1080–7680 px, 16:9 or 9:16. console |
| Android TV | Required if the app is distributed to Android TV | 1–8 | — | PNG/JPEG, 8 bits/channel, no alpha | tvScreenshots |
| Wear OS | Required if the app is distributed to Wear OS | 1–8 | sides 384 px minimum, 1:1 | PNG/JPEG, 8 bits/channel, no alpha | Framing forbidden. wearScreenshots |
| Android XR | Required if the app is distributed to Android XR | 4–8 | minimum 1920×1200, 8:5 | PNG/JPEG, 8 bits/channel, no alpha, ≤8,388,608 bytes | console |
| Android Automotive OS | Optional | 0–8 | 800×1280, 1024×768, at least 2 per size | PNG/JPEG, 8 bits/channel, no alpha | console |

At least 2 screenshots across all device types per locale.

Verified 2026-11-26 · [Store reference 1](https://support.google.com/googleplay/android-developer/answer/9866151)

<!-- rules:end screenshots -->

## Graphics

<!-- rules:begin graphics -->

| Graphic | File stem | Size | Format | Requirement | Upload |
| --- | --- | --- | --- | --- | --- |
| App icon | icon | 512×512 | PNG, 8 bits/channel, alpha allowed, ≤1,048,576 bytes | Required | fastlane |
| Feature graphic | featureGraphic | 1024×500 | PNG/JPEG, 8 bits/channel, no alpha | Required | fastlane |
| TV banner | tvBanner | 1280×720 | PNG/JPEG, 8 bits/channel, no alpha, grayscale JPEG accepted | Required if the app is distributed to Android TV | fastlane |

Verified 2026-11-26 · [Store reference 1](https://support.google.com/googleplay/android-developer/answer/9866151)

<!-- rules:end graphics -->

Generate an icon-on-gradient feature graphic with `scripts/generate/feature-graphic.sh` or supply the finished artwork. Keep feature graphics separate from screenshots.

## Detecting tablet support (decide whether to capture tablet sets)

Tablet screenshots are **optional to publish**, but without them Play may label the
app "not designed for tablets" and exclude it from tablet featuring. Capture 7"/10"
sets when the app targets tablets. Signals that it does:
- **Flutter / React Native / native** apps run on Android tablets by default unless
  the manifest restricts it — treat tablet as supported unless told otherwise.
- Check `AndroidManifest.xml` for `<supports-screens android:largeScreens="false"/>`
  or `<compatible-screens>` that *excludes* large/xlarge → tablets NOT supported.
- A `sw600dp`/`sw720dp` resource bucket (`res/values-sw600dp/…`) signals tablet layouts.

To capture, you need a **tablet AVD** (e.g. `pixel_tablet` / `Nexus 9`); a phone AVD
won't produce tablet-sized images. If none exists, create one
(`avdmanager create avd -d pixel_tablet -k "<system-image>"`) — note this may require
downloading a system image, so ask first; in a non-interactive run, don't create
one: report the tablet set as missing instead.

## Metadata fields

<!-- rules:begin fields -->

| Field | File stem | Scope | Limit or unit | Requirement |
| --- | --- | --- | --- | --- |
| Title | title | locale | 30 chars | Required |
| Short description | short_description | locale | 80 chars | Required |
| Full description | full_description | locale | 4000 chars | Required |
| Promo video URL | video | locale | url | Optional |
| Release notes | changelogs/<name> | locale | 500 chars | Allowed names: `^(default\|[0-9]+)$` |

Verified 2026-11-26 · [Store reference 1](https://support.google.com/googleplay/android-developer/answer/9859152) · [Store reference 2](https://support.google.com/googleplay/android-developer/answer/9859348)

<!-- rules:end fields -->

## App-level (not per-locale)

- Category
- Content rating (questionnaire)
- Privacy policy URL
- Contact details (email required)

## fastlane `supply` mapping
Run `listing-kit detect <app-root>`. Text fields are `.txt` files under
`<play.metadata>/<locale>/`; images live under that locale's
`images/` subtree: screenshot folders (`phoneScreenshots/`, `sevenInchScreenshots/`,
`tenInchScreenshots/`, `tvScreenshots/`, `wearScreenshots/`) plus single files
`featureGraphic.png`, `icon.png`, and optional `tvBanner.png` directly in `images/`
(PNG or JPEG; supply does **not** look inside `featureGraphic/` or `icon/` folders). Release notes go in
`changelogs/<versionCode>.txt` (or `changelogs/default.txt`).
