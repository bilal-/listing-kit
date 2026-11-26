# Apple App Store — requirements reference

The tables below are generated from `specs/stores.json`. Record app-specific differences and their source URLs in `.listing-kit/specs.override.json`.

## Screenshots

Use the console upload slot to choose a capture device. Capture at an accepted native resolution for that class.

<!-- rules:begin screenshots -->

| Display class | Requirement | Count per locale | Accepted size or bounds | Format | Delivery and notes |
| --- | --- | --- | --- | --- | --- |
| iPhone Dynamic Island (medium display) | Required if the app runs on iPhone (not iPad-only) | 1–10 | 1206×2622, 1179×2556 | PNG/JPEG, no alpha | fastlane |
| iPhone Dynamic Island (large display) | Optional | 1–10 | 1320×2868, 1290×2796, 1260×2736 | PNG/JPEG, no alpha | fastlane |
| iPhone Face ID (large display) | Optional | 1–10 | 1284×2778, 1242×2688 | PNG/JPEG, no alpha | fastlane |
| iPhone Face ID (medium display) | Optional | 1–10 | 1170×2532, 1125×2436, 1080×2340 | PNG/JPEG, no alpha | fastlane |
| iPhone Home Button (large display) | Optional | 1–10 | 1242×2208 | PNG/JPEG, no alpha | fastlane |
| iPhone Home Button (medium display) | Optional | 1–10 | 750×1334 | PNG/JPEG, no alpha | fastlane |
| iPhone Home Button (4" display) | Optional | 1–10 | 640×1136, 1136×640, 640×1096, 1136×600, fixed orientation | PNG/JPEG, no alpha | fastlane |
| iPhone Home Button (3.5" display) | Optional | 1–10 | 640×960, 960×640, 640×920, 960×600, fixed orientation | PNG/JPEG, no alpha | fastlane |
| iPhone Duo (outer display) | Required if the app runs on iPhone (not iPad-only) from 2027-04-01 unless the app is built with an iOS SDK older than 27.1 | 1–10 | 1398×2034 | PNG/JPEG, no alpha | fastlane |
| iPhone Duo (inner display) | Required if the app runs on iPhone (not iPad-only) from 2027-04-01 unless the app is built with an iOS SDK older than 27.1 | 1–10 | 2007×2853 | PNG/JPEG, no alpha | fastlane |
| iPad 13" | Required if the app runs on iPad | 1–10 | 2064×2752, 2048×2732 | PNG/JPEG, no alpha | fastlane |
| iPad 12.9" | Optional | 1–10 | 2048×2732 | PNG/JPEG, no alpha | fastlane |
| iPad 11" | Optional | 1–10 | 1668×2420, 1668×2388, 1640×2360, 1512×2316, 1488×2266 | PNG/JPEG, no alpha | fastlane |
| iPad 10.5" | Optional | 1–10 | 1668×2224 | PNG/JPEG, no alpha | fastlane |
| iPad 9.7" | Optional | 1–10 | 1536×2048, 2048×1536, 1536×2008, 2048×1496, 768×1024, 1024×768, 768×1004, 1024×748, fixed orientation | PNG/JPEG, no alpha | fastlane |
| Apple Watch | Required if the app has a watchOS app | 1–10 | 422×514, 410×502, 416×496, 396×484, 368×448, 312×390, fixed orientation | PNG/JPEG, no alpha | Framing forbidden. fastlane |
| Apple TV | Required if the app has a tvOS app | 1–10 | 1920×1080, 3840×2160, fixed orientation | PNG/JPEG, no alpha | appleTV |
| Apple Vision Pro | Required if the app has a visionOS app | 1–10 | 3840×2160, fixed orientation | PNG/JPEG, no alpha | console |
| Mac | Required if the app has a macOS app | 1–10 | 1280×800, 1440×900, 2560×1600, 2880×1800, fixed orientation | PNG/JPEG, no alpha | fastlane |

Verified 2026-11-26 · [Store reference 1](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications/)

<!-- rules:end screenshots -->

Record the selected sets and counts in the [asset plan](../metadata/fastlane-layout.md#apple-asset-plan). For Duo, use the [native capture preflight](../stacks/ios-native.md#optional-duo-capture) to check the installed devices and runtimes. Record a deferred target with its reason in `deferredScreenshots`. Check the dated requirements above for the intended submission date and build SDK.

Run `scripts/capture/normalize-screenshot.sh in.png out.png` on raw captures before validation.

## Detecting iPad support

The validator reads the native target device family, Info.plist and static Expo configuration. Use the iPad slot above to select a simulator. Place captures in the locale screenshot directory with an iPad-specific filename prefix.

## Metadata fields

<!-- rules:begin fields -->

| Field | File stem | Scope | Limit or unit | Requirement |
| --- | --- | --- | --- | --- |
| Name | name | locale | 2–30 chars | Required |
| Subtitle | subtitle | locale | 30 chars | Optional |
| Promotional text | promotional_text | locale | 170 chars | Optional |
| Description | description | locale | 4000 chars | Required |
| Keywords | keywords | locale | 100 bytes | Required |
| Support URL | support_url | locale | url | Required |
| Marketing URL | marketing_url | locale | url | Optional |
| Privacy policy URL | privacy_url | locale | url | Required |
| What's new | release_notes | locale | 4000 chars | Required if this listing is for an update, not the first version |
| Copyright | copyright | app | chars | Required |
| Primary category | primary_category | app | enum | Required |
| Secondary category | secondary_category | app | enum | Optional |

Verified 2026-11-26 · [Store reference 1](https://developer.apple.com/help/app-store-connect/reference/app-information/app-information/) · [Store reference 2](https://developer.apple.com/help/app-store-connect/reference/app-information/platform-version-information/)

<!-- rules:end fields -->

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
<!-- rules:begin graphics -->

| Graphic | File stem | Size | Format | Requirement | Upload |
| --- | --- | --- | --- | --- | --- |
| Header Asset 16:9 | header-16x9 | 5244×2950 | PNG, 8 bits/channel, no alpha | Optional | console |
| Header Asset 21:9 | header-21x9 | 3840×1646 | PNG/JPEG, 8 bits/channel, no alpha | Optional | console |

Verified 2026-11-26 · [Store reference 1](https://developer.apple.com/help/app-store-connect/reference/app-information/creative-assets-specifications)

<!-- rules:end graphics -->

Compose the artwork on the canvas for the selected header. Follow [Apple's header templates and best practices](https://developer.apple.com/app-store/asset-best-practices/):
one clear idea, a centered focal point, short readable text, and enough room for
placement crops. Use the app's approved brand assets and verified claims. Avoid
URLs, copyright symbols, pricing and other platforms' logos. Review each finished
size visually; a dimension check cannot catch clipping or an unreadable headline.

Store headers under `store-assets/apple/<locale>/` at the app root. Record expected
filenames in the asset plan so a missing header fails validation. The review page
shows these separately as **Header Asset (manual console upload)**. Do not place
them in `fastlane/screenshots/` or imply `deliver` uploads them. Include this
folder in the handoff alongside screenshots, with upload slots clearly labeled.
