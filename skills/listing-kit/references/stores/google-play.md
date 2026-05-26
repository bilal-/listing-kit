# Google Play — requirements reference

> **Snapshot, not gospel.** Play Console requirements change. **Re-verify against
> current Play Console docs at runtime** and prefer live docs when they disagree
> with this table.

## Graphics & screenshots

| Asset | Required? | Spec |
|---|---|---|
| Phone screenshots | Yes (min 2) | 2–8 images; JPEG or 24-bit PNG (**no alpha**); 320–3840px per side; max aspect 2:1; 1080×1920 recommended |
| 7" tablet screenshots | If targeting tablets | 2–8, same format rules |
| 10" tablet screenshots | If targeting tablets | 2–8, same format rules |
| Wear OS screenshots | If Wear OS app | up to 8 |
| **Feature graphic** | **Yes — required to publish** | exactly **1024×500**, JPEG or 24-bit PNG (**no alpha**) |
| App icon | Yes | 512×512, 32-bit PNG |

> The **feature graphic is not a screenshot** and cannot be produced by
> capturing the app. listing-kit generates an icon-on-gradient placeholder via
> `scripts/generate/feature-graphic.sh` (ImageMagick), falling back to prompting
> the user to supply one if ImageMagick is absent.

## File & format rules (the easy-to-miss ones — Validate must check these)

Raw `adb exec-out screencap` output is a **32-bit RGBA** PNG, which Play **rejects**
for screenshots/feature graphic. Every image must be normalized before it is written:

| Rule | Detail | How to enforce |
|---|---|---|
| **No alpha** (screenshots + feature graphic) | Play wants **JPEG or 24-bit PNG**. 32-bit RGBA is non-compliant. | `magick in.png -background white -alpha remove -alpha off -depth 8 PNG24:out.png` |
| **8-bit depth** | "24-bit PNG" = 8 bits × 3 channels. A 16-bit-depth PNG is 48-bit and non-compliant. | include `-depth 8` (and `PNG24:`) |
| **Max aspect ratio 2:1** | A 1080×2400 (20:9 ≈ 2.22:1) phone capture **exceeds** it. | crop to ≤2:1 (e.g. top-aligned `-crop 1080x1920+0+0`) or target a ≤2:1 device |
| **Side length 320–3840 px** | each side | check both dimensions |
| **Max file size 8 MB** per image | screenshots + feature graphic | check `stat`/size |
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
`images/` subtree (`phoneScreenshots/`, `sevenInchScreenshots/`,
`tenInchScreenshots/`, `wearScreenshots/`, `featureGraphic/`, `icon/`).
