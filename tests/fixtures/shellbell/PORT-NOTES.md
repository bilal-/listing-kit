# Shellbell listing port

- Fastlane owns the localized Apple URLs in `fastlane/metadata/en-US/{marketing_url,support_url,privacy_url}.txt`. Copyright and Apple category go in `fastlane/metadata/copyright.txt` and `primary_category.txt`. The original values are in `listing.json`. Play category and privacy URL are in `console`.
- Capture restrictions, manual console work, release-note instructions, and source links are in `notes`. The capture demo entry moved to `app.demoEntry`. The two approved selection flags were dropped. The plan uses `draft` to mark unfinished copy.
- The feature graphic and Apple headers carry their own palette, logo, and headline line break. Template geometry comes from `render-graphics.sh`, which records the placements and font sizes for all three canvases.
- The logo resolves from the repository root. For the Play icon, the renderer copies `brand/android/play-store-512.png` into the app. The plan refers to that staged PNG.
