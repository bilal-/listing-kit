# Google Play — requirements reference

> **Snapshot, not gospel** (verified against Play Console help, 2026-10). Play
> Console requirements change. **Re-verify against the current
> [preview assets guide](https://support.google.com/googleplay/android-developer/answer/9866151)
> at runtime** and prefer live docs when they disagree with this table.

## Graphics & screenshots

| Asset | Required? | Spec |
|---|---|---|
| Screenshots (all device types) | **≥2 in total** across device types | Up to 8 per device type. Use JPEG or 24-bit PNG without alpha. Device-specific dimensions appear below. |
| Phone screenshots | If targeting phones | 2–8 images, 320–3840 px per side, up to 8 MB each. The long side can be up to 2.3× the short side. For promotion use at least four 1080 px or larger 9:16 or 16:9 screenshots for apps. |
| 7" / 10" tablet screenshots | If targeting tablets | up to 8 each; for tablet/Chromebook featuring, ≥4 at 1080–7680 px, 16:9 or 9:16 |
| Wear OS screenshots | If Wear OS app | up to 8 |
| Android XR screenshots | If XR app | 4–8, 8:5 aspect, ≥1920×1200 (3840×2400 recommended), ≤8 MB. No fastlane `supply` folder yet: upload in Play Console |
| **Feature graphic** | **Yes — required to publish** | exactly **1024×500**, JPEG or 24-bit PNG (**no alpha**) |
| App icon | Yes | 512×512, 32-bit PNG (alpha allowed), ≤1 MB, no badges or rank/price text |

> The **feature graphic is not a screenshot** and cannot be produced by
> capturing the app. listing-kit generates an icon-on-gradient placeholder via
> `scripts/generate/feature-graphic.sh` (ImageMagick), falling back to prompting
> the user to supply one if ImageMagick is absent.

## File & format rules (the easy-to-miss ones — Validate must check these)

Raw `adb exec-out screencap` output is a **32-bit RGBA** PNG, which Play **rejects**
for screenshots/feature graphic. Every image must be normalized before it is written:

| Rule | Detail | How to enforce |
|---|---|---|
| **No alpha** (screenshots + feature graphic) | Play wants **JPEG or 24-bit PNG**. 32-bit RGBA is non-compliant. | screenshots: `scripts/capture/normalize-screenshot.sh in.png out.png --play`; feature graphic: same **without** `--play` (it would crop 1024×500) |
| **8-bit depth** | "24-bit PNG" = 8 bits × 3 channels. A 16-bit-depth PNG is 48-bit and non-compliant. | include `-depth 8` (and `PNG24:`) |
| **Phone and standard tablet aspect ratio** | Long side ≤2.3× short side. A 1080×2400 capture fits. | The current normalization script crops to 9:16 for promotion. |
| **Phone side length 320–3840 px** | Applies to both dimensions. | Check the slot rules for other devices. |
| **File size** | Phone and XR screenshots allow up to 8 MB each. | Check the encoded file size. |
| **App icon is the exception** | the Play **icon** is a **32-bit PNG (alpha allowed)** — do *not* flatten it. | leave icon as RGBA |

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

## Metadata fields (per locale)

| Field | Limit |
|---|---|
| Title | 30 chars |
| Short description | 80 chars |
| Full description | 4000 chars |

## App-level (not per-locale)

- Category
- Content rating (questionnaire)
- Privacy policy URL
- Contact details (email required)

## fastlane `supply` mapping
See `../metadata/fastlane-layout.md`. Text fields are `.txt` files under
`fastlane/metadata/android/<locale>/`; images live under that locale's
`images/` subtree: screenshot folders (`phoneScreenshots/`, `sevenInchScreenshots/`,
`tenInchScreenshots/`, `tvScreenshots/`, `wearScreenshots/`) plus single files
`featureGraphic.png`, `icon.png`, and optional `tvBanner.png` directly in `images/`
(PNG or JPEG; supply does **not** look inside `featureGraphic/` or `icon/` folders). Release notes go in
`changelogs/<versionCode>.txt` (or `changelogs/default.txt`).
