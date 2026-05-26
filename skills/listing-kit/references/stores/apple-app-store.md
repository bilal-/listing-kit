# Apple App Store — requirements reference

> **Snapshot, not gospel.** Apple changes which sizes are required vs. derived
> fairly often. The trend is toward *fewer* mandatory sizes (App Store Connect
> has been moving to requiring only the largest **6.9" iPhone** and **13" iPad**
> and deriving the rest). **Re-verify against current App Store Connect docs at
> runtime** — prefer live docs over this table when they disagree.

## Screenshots

| Device class | Required? | Accepted pixel sizes (portrait / landscape) | Max count |
|---|---|---|---|
| iPhone 6.9" / 6.7" | Yes — at least one iPhone size required | 1290×2796 / 2796×1290, 1284×2778 / 2778×1284 | 10 |
| iPhone 6.5" | Acceptable alternative | 1242×2688 / 2688×1242 | 10 |
| iPad 13" / 12.9" | Required **iff** the app supports iPad | 2064×2752 / 2752×2064, 2048×2732 / 2732×2048 | 10 |
| Apple Watch | Required **iff** the app has a watchOS target | per watch series | 10 |

**Derivation:** App Store Connect derives some smaller sizes from a larger
uploaded set. Default strategy: capture the **largest required size per family**
and let the store fill the rest, unless the user wants explicit per-size captures.

**Format:** PNG or JPEG, RGB, no transparency, no rounded corners/device frame
required (raw screen content is fine and preferred for regeneration).

## Metadata fields (per locale)

| Field | Limit | Notes |
|---|---|---|
| App name | 30 chars | |
| Subtitle | 30 chars | |
| Promotional text | 170 chars | updatable without review |
| Description | 4000 chars | |
| Keywords | 100 chars | comma-separated, no spaces needed |
| Support URL | — | required |
| Marketing URL | — | optional |
| Copyright | — | e.g. `2026 Your Company` |

## App-level (not per-locale)

- Primary + optional secondary category
- Content/age rating
- Privacy policy URL (required)

## fastlane `deliver` mapping
See `../metadata/fastlane-layout.md`. Each field maps to a `.txt` file under
`fastlane/metadata/<locale>/`; screenshots go under `fastlane/screenshots/<locale>/`.
