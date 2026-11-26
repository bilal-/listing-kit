# Build distribution and the listing

These are examples for an app's own fastlane configuration. The kit does not test TestFlight or Play testing-track releases. Confirm the current prerequisites and options in the linked vendor docs.

## TestFlight example

Your build pipeline signs and exports an IPA. A fastlane lane can pass that IPA to pilot with the action below. TestFlight handles beta distribution. Check build processing and tester access in App Store Connect. [Fastlane pilot](https://docs.fastlane.tools/actions/pilot/) · [Apple TestFlight overview](https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview/)

```ruby
upload_to_testflight(ipa: "build/MyApp.ipa")
```

Prepare the product page separately. Review the Apple text and screenshot sets in git, then use the kit's hand-upload index for the listing. [Fastlane deliver](https://docs.fastlane.tools/actions/deliver/)

## Google Play internal testing example

Your Android build pipeline produces a signed app bundle. A release lane can send the AAB to the internal track with supply. This example skips listing text, release notes and images. Use the track and release status appropriate to your app, then follow Play's testing guidance for tester access. [Fastlane supply](https://docs.fastlane.tools/actions/supply/) · [Google Play testing tracks](https://support.google.com/googleplay/android-developer/answer/9845334)

```ruby
upload_to_play_store(
  aab: "build/app-release.aab",
  track: "internal",
  skip_upload_metadata: true,
  skip_upload_changelogs: true,
  skip_upload_images: true,
  skip_upload_screenshots: true
)
```

Keep the Play listing under version control alongside the release. Use `listing-kit validate` and `listing-kit review` on the public assets. In this version `listing-kit publish` previews listing changes. Use `listing-kit handoff --open` to upload those assets by hand.
