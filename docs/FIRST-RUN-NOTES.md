# Recipe Box capture on November 26, 2026

Expo SDK 57, Xcode 27.2, iOS 26.5 simulators and Maestro 2.11.0. Both Release builds ran the four existing flows against the app’s seeded data.

| Finding | Fix | Commit |
| --- | --- | --- |
| The iPad passed capture and size checks with a gray resize handle in its lower-right corner. | Changed the QA iPad from Windowed Apps to Full Screen Apps, recaptured all four screens, inspected the native corners and restored Windowed Apps. The Maestro reference gives the Settings path. | `bb7cc81` |
| The QA phone AVD produced 1344 × 2992 pixels. The old gallery contained 1080 × 1920 images, which lost part of the native screen. | Kept native captures and fitted the entire display, including the gesture bar, into each Play frame. | `bb7cc81` |
| The walkthrough described a missing iPhone gallery and copied the whole app directory, including local builds after an in-place run. | Used the shipped four-target plan in the guide, exported the committed fixture for the walkthrough and documented direct Release installation by device ID. Tests now validate the shipped gallery and construct missing-display cases in temporary fixtures. | `bb7cc81` |

The two iPhone displays, iPad and Android phone all completed with the kit’s existing device selection, status-bar helpers and timeouts. The run covered portrait and en-US. The final handoff contained 33 files. A clean export reproduced the listing with all 19 outputs unchanged.

On follow-up, the first iPad screen showed “◀ Settings” to the left of the clock after the window-mode change. Capture now terminates and directly launches the installed iOS app before every job. A flow that returns through another app can reintroduce the breadcrumb. The review page shows native-size raw status-bar strips for visual inspection. All four recaptured iPad screens showed “9:41 AM  Thu Nov 26” in both the raw and framed PNGs. Xcode 27.2 offers no date-visibility override.

Tests with filename or gallery changes include `structure/examples.test.sh`, `structure/validate-listing.test.sh`, `unit/build-review.test.sh`, `unit/fastlane.test.sh`, `unit/install-review-hook.test.sh`, `e2e/example.sh` and `unit/e2e-example.test.sh` under `tests/`. The docs, detection, slot and coverage fixtures now set up their own required or missing displays.
