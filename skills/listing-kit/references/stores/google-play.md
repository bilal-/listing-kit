# Google Play — requirements reference

> **Snapshot, not gospel** (verified against Play Console help, 2026-10). Play
> Console requirements change. **Re-verify against the current
> [preview assets guide](https://support.google.com/googleplay/android-developer/answer/9866151)
> at runtime** and prefer live docs when they disagree with this table.

## Graphics & screenshots

| Asset | Required? | Spec |
|---|---|---|
| Screenshots (all device types) | **≥2 in total**, across device types | up to 8 per device type; JPEG or 24-bit PNG (**no alpha**); 320–3840 px per side; long side ≤ 2× short side |
| Phone screenshots | In practice yes | 1080×1920 recommended. **Promotion eligibility:** ≥4 screenshots at ≥1080 px (9:16 portrait or 16:9 landscape); games need 3 landscape |
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
| **Max aspect ratio 2:1** | A 1080×2400 (20:9 ≈ 2.22:1) phone capture **exceeds** it. | `normalize-screenshot.sh --play` crops top-aligned to ≤2:1, or target a ≤2:1 device |
| **Side length 320–3840 px** | each side | check both dimensions |
| **File size** | Play no longer documents a phone-screenshot cap (8 MB was the old limit; XR still has one). `validate-listing.sh` warns above 8 MB | check `stat`/size |
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
downloading a system image, so prompt before doing it in a non-interactive run.

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
