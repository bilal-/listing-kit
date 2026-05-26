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
