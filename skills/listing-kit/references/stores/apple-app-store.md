# Apple App Store — requirements reference

> **Snapshot, not gospel** (verified against App Store Connect docs, 2026-10).
> Apple changes which sizes are required vs. derived fairly often. **Re-verify
> against the current
> [screenshot specifications](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications)
> at runtime** and prefer live docs over this table when they disagree.

## Screenshots

1–10 screenshots per display class, per locale.

| App Store Connect upload slot | Coverage | Accepted portrait sizes (landscape = swapped) |
|---|---|---|
| iPhone Dynamic Island (medium display) | **Required** by the current Required device sizes section | 1206×2622, 1179×2556 |
| iPhone Dynamic Island (large display) | Additional slot; does not fill medium | 1320×2868, 1290×2796, 1260×2736 |
| iPhone Face ID (large display) | Check the console's requirements for this slot | 1284×2778, 1242×2688 |
| iPhone Face ID (medium display) | Additional slot | 1170×2532, 1125×2436, 1080×2340 |
| iPhone Home Button (large / medium display) | Additional slots | large: 1242×2208 · medium: 750×1334 |
| iPhone Duo | Capture when selected; do not silently add it to launch scope | outer: 1398×2034 · inner: 2007×2853 |
| iPad 13" | **Required iff** app runs on iPad | 2064×2752, 2048×2732 |
| iPad 11" / 10.5" | Additional slots | 11": 1668×2420, 1668×2388, 1640×2360, 1488×2266 · 10.5": 1668×2224 |
| Apple Watch | Only if watchOS app | See live specs |

Use the console's **upload slot**, not just a device's marketing diagonal.
A 1320×2868 capture is valid for Dynamic Island large but is rejected in the
medium slot. Capture medium at native resolution; do not stretch a large capture.
Persist the selected sets/counts in the [asset plan](../metadata/fastlane-layout.md#apple-asset-plan).
The validator checks current minimums plus that plan; a valid unrelated set cannot
satisfy a missing planned class. Its size table is
`scripts/lib/apple-screenshot-sizes.tsv`, shared with the review page.

For Duo, check that Xcode and the installed runtime actually provide its device
type before building (Xcode 27.1 / iOS 27.1 at this snapshot). See the
[native capture guidance](../stacks/ios-native.md#capture) for multiple displays.
Keep deferred targets out of active screenshot counts and record them in
`deferredScreenshots` with a reason. The [Duo preflight](../stacks/ios-native.md#optional-duo-capture)
lets other targets and creative assets proceed when compatible tooling is absent.
Deferral does not waive store requirements: Apple has announced Duo screenshots
will become required starting April 2027; recheck the linked specifications for
the intended submission date.

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

## Product page Header Asset

Header artwork is a separate creative asset, not an app screenshot or the Play
feature graphic. Confirm whether it is part of the requested listing.
[Apple's creative asset specifications](https://developer.apple.com/help/app-store-connect/reference/app-information/creative-assets-specifications)
accept 5244×2950 **PNG** (16:9), or 3840×1646 PNG/JPEG (21:9), without alpha.
Generate 8-bit RGB assets. Do not swap width/height or enlarge the 1024×500 Play
feature graphic; compose the artwork for the selected canvas.

Follow [Apple's header templates and best practices](https://developer.apple.com/app-store/asset-best-practices/):
one clear idea, a centered focal point, short readable text, and enough room for
placement crops. Use the app's approved brand assets and verified claims. Avoid
URLs, copyright symbols, pricing and other platforms' logos. Review each finished
size visually; a dimension check cannot catch clipping or an unreadable headline.

Store headers under `store-assets/apple/<locale>/` at the app root. Record expected
filenames in the asset plan so a missing header fails validation. The review page
shows these separately as **Header Asset (manual console upload)**. Do not place
them in `fastlane/screenshots/` or imply `deliver` uploads them. Include this
folder in the handoff alongside screenshots, with upload slots clearly labeled.
