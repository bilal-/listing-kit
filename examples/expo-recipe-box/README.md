# Recipe Box

Five recipes, their ingredients and cooking steps, a shopping list and a settings screen. The Expo Router app loads its sample data from `data/recipes.ts` on every clean launch. The four Maestro flows open the app and check the visible recipe, ingredient, shopping item or theme switch.

The en-US listing passes validation. All four screens were captured from Release builds on QA iPhone 17 Pro, QA iPhone 17 Pro Max, QA iPad Pro 13 (iOS 26.5) and QA_Large_Phone. The Play phone frames a 1344 × 2992 capture on a 1080 × 1920 canvas. The Apple frames use each display’s native resolution. The plan also produces a Play feature graphic, Play icon and 16:9 Apple header.

Run the launcher here to see the full file list and inspect the listing.

```sh
listing-kit plan outputs
listing-kit validate
listing-kit review
```

The [plan](.listing-kit/listing.json) defines the captions, sizes and device types. The [walkthrough](../../docs/GUIDE.md) covers installation, device selection, capture and handoff.
