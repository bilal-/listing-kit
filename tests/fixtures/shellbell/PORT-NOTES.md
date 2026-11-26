# Shellbell listing port

The localized Apple URLs, copyright and primary category from `listing.json` are in the fixture's `fastlane/metadata` tree. The Play category and privacy URL are in `console`. The two selection approvals are explicit in `approved`. Targets, feature artwork and headers that were marked prepared retain their `status`.

The `shellbell-header-16x9` and `shellbell-header-21x9` templates correspond to the two `render_header` calls in [render-graphics.sh](render-graphics.sh). Each call records its canvas, logo placement, font sizes and baselines. The feature graphic records its own copy and palette. Both the horizontal logo and the original Play icon resolve from the repository root.

The demo entry is in `app.demoEntry`. Capture restrictions, manual console work, release instructions and sources are in `notes`.
