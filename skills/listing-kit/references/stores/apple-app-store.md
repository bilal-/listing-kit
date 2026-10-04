# Apple App Store — requirements reference

> **Snapshot, not gospel** (verified against App Store Connect docs, 2026-10).
> Apple changes which sizes are required vs. derived fairly often. **Re-verify
> against the current
> [screenshot specifications](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications)
> at runtime** and prefer live docs over this table when they disagree.

## Screenshots

1–10 screenshots per display class, per locale.

| Display class | Required? | Accepted portrait sizes (landscape = swapped) |
|---|---|---|
| iPhone 6.9" | **One of 6.9" or 6.5" is required** if the app runs on iPhone | 1320×2868, 1290×2796, 1260×2736 |
| iPhone 6.5" | Required only if no 6.9" set (otherwise scaled from 6.9") | 1284×2778, 1242×2688 |
| iPhone 6.3" / 6.1" / 5.5" / 4.7" | Optional (scaled from a larger set) | 6.3": 1206×2622, 1179×2556 · 6.1": 1170×2532, 1125×2436, 1080×2340 · 5.5": 1242×2208 · 4.7": 750×1334 |
| iPad 13" | Required **iff** the app runs on iPad | 2064×2752, 2048×2732 |
| iPad 11" / 10.5" | Optional (scaled from 13") | 11": 1668×2420, 1668×2388, 1640×2360, 1488×2266 · 10.5": 1668×2224 |
| Apple Watch | Required **iff** the app has a watchOS target | per watch series |

The machine-readable copy of this table is `scripts/lib/apple-screenshot-sizes.tsv`
(used by `validate-listing.sh` and `build-review.sh`). Keep the two in sync when
Apple changes sizes. Apple has also announced an "iPhone Duo" class (outer
1398×2034, inner 2007×2853) that is not accepted for upload yet.

**Derivation:** App Store Connect derives some smaller sizes from a larger
uploaded set. Default strategy: capture the **largest required size per family**
and let the store fill the rest, unless the user wants explicit per-size captures.

**Format (Validate must enforce):** PNG or JPEG, **RGB, flattened, no alpha/
transparency**. Raw `xcrun simctl … screenshot` output is **32-bit RGBA** and must
be flattened before upload:
`scripts/capture/normalize-screenshot.sh in.png out.png`.
No rounded corners/device frame needed (raw screen content is preferred for
regeneration). Max ~500 MB/file (not a practical concern).

## Detecting iPad support (whether iPad screenshots are REQUIRED)

If the app runs on iPad, **iPad 13"/12.9" screenshots are required to submit** — a
common, easy-to-miss rejection. Detect it before deciding to capture:
- **Expo / React Native:** `ios.supportsTablet: true` in `app.json`/`app.config`.
- **Native iOS:** `TARGETED_DEVICE_FAMILY` includes `2` (1=iPhone, 2=iPad), or
  `UIDeviceFamily` in `Info.plist` includes `2`. "Designed for iPad" / universal.
- **Flutter:** iOS runner's `TARGETED_DEVICE_FAMILY` (same as native).

When supported, install the same build on the newest **iPad Pro 13-inch** simulator
(names carry a chip suffix, e.g. `iPad Pro 13-inch (M5)`; list them with
`xcrun simctl list devicetypes`) and capture at **2064×2752**. An 11" iPad set does
**not** satisfy the requirement. Place under the same
`fastlane/screenshots/<locale>/` with an iPad-distinct filename prefix; deliver
assigns device by image dimensions.

## Metadata fields (per locale)

| Field | Limit | Notes |
|---|---|---|
| App name | 2–30 chars | |
| Subtitle | 30 chars | |
| Promotional text | 170 chars | updatable without review |
| Description | 4000 chars | |
| Keywords | 100 **bytes** | comma-separated, no spaces needed. Bytes, not characters: CJK text hits the limit sooner |
| Support URL | — | required |
| Marketing URL | — | optional |
| Privacy policy URL | — | required for iOS apps (`privacy_url.txt`) |

## App-level (not per-locale)

- Copyright (`copyright.txt`), e.g. `2026 Your Company`
- Primary + optional secondary category
- Content/age rating

## fastlane `deliver` mapping
See `../metadata/fastlane-layout.md`. Each field maps to a `.txt` file under
`fastlane/metadata/<locale>/`; screenshots go under `fastlane/screenshots/<locale>/`.
