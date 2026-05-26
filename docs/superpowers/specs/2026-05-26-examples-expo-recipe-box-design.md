# listing-kit examples — Expo Recipe Box (Phase A)

**Status:** Design — approved, ready for implementation plan
**Date:** 2026-05-26
**Author:** Bilal Ahmad
**Depends on:** the `listing-kit` skill (this repo, `skills/listing-kit/`)

> Add an `examples/` folder containing a single, complete, **automation-friendly**
> Expo / React Native app that listing-kit can be run against to produce a full
> store listing. It serves as a **demo** (show what listing-kit produces), a
> **dogfooding** target (a real app to test skill changes against), and is
> structured so **end-to-end eval fixtures** can be added later without rework.

---

## 1. Goals

1. Give prospective users a concrete, in-repo answer to "what does listing-kit
   actually produce?" — by committing the real generated listing.
2. Give contributors a real app to test skill changes against locally.
3. Model the **"make your app listing-kit-ready"** practices (deep links,
   accessibility labels, demo-data mode) in a working app.
4. Be the **first real end-to-end dogfood** of the skill.

**Non-goals (this spec):** native iOS, native Android, and Flutter examples
(added later); an automated eval/CI tier that builds the app and asserts on output
(the folder is *structured* for it, but it is out of scope here); writing app
features beyond the minimum needed to showcase a listing.

## 2. Scope decisions (resolved during brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| How many apps now | **One** | Start small; native iOS/Android/Flutter examples come later. |
| Which stack | **Expo (managed) RN** | Most common modern RN path; easiest to build/run/capture; one app covers both iOS + Android output. |
| App design | **A distinct, purpose-built app** (not a shared cross-stack concept) | Future examples are distinct apps too; gives realistic, varied output. |
| Committed output | **Full generated output** | Most honest showcase — "this is literally what you get." Screenshots are demo artifacts, not pixel-diff goldens. |
| Sequencing | **Phase A now; Phase B documented** | App + structure + flows + docs are committable immediately; real output requires toolchains + simulators and is generated separately. |

## 3. The app: Recipe Box

A small, complete recipe-saver. Deliberately tiny — enough screens to make a
believable 5-screenshot listing, no more.

| Screen | Deep link | Demo state (populated, no login) |
|---|---|---|
| Recipes (list) | `recipebox://recipes` | several sample recipes with images |
| Recipe detail | `recipebox://recipe/:id` | a full recipe, ingredients + steps |
| Shopping list | `recipebox://shopping` | a few checked / unchecked items |
| Settings | `recipebox://settings` | theme + about (lightweight 4th screen) |

### 3.1 "Listing-kit-ready" features (the point of the example)
- **URL scheme** `recipebox://` registered (`expo.scheme` in `app.json`) with
  Expo Router / Linking handling the routes above — so Maestro drives via deep
  links, the most stable path.
- **Accessibility labels** on every interactive element and key view, so
  tap-by-label works without deep links too.
- **Demo-data mode**: the app ships seeded sample data by default (no auth, no
  network) so every screen is populated. No real credentials anywhere — keeps the
  secret-scan gate green.
- **No login wall**, no social auth — avoids the dominant automation risk.

### 3.2 Tech
- Expo SDK (managed), Expo Router (file-based routes under `app/`), TypeScript.
- Local seed data (JSON/in-memory); no backend.
- Pinned Expo SDK + Node version recorded in `examples/README.md` for
  reproducibility.

## 4. Folder structure

```
examples/
  README.md                       # index + "how output was generated" + readiness notes
  expo-recipe-box/
    app/                          # Expo Router screens (recipes, recipe/[id], shopping, settings)
    assets/                       # icon, sample recipe images
    data/                         # seed data
    app.json  package.json  tsconfig.json
    .listing-kit/
      flows/                      # committed Maestro flows (one per screen) — recipe, not secret
    fastlane/                     # FULL committed output (Phase B): deliver + supply trees
```

- `.listing-kit/flows/` is **committed here on purpose** — the flows are the
  rerunnable navigation recipe, not secrets. (Note: the repo-root `.gitignore`
  ignores `.listing-kit/`; this spec adds a negation so `examples/**/.listing-kit/flows/`
  is tracked while real secret files remain ignored.)
- `fastlane/` is populated in **Phase B**, not Phase A.

## 5. Committed output (Phase B)

Exactly what listing-kit produces with its defaults, committed wholesale:
- iOS `fastlane/metadata/` + `fastlane/screenshots/<locale>/` (deliver layout).
- Android `fastlane/metadata/android/<locale>/` incl. `images/` (supply layout).
- **One hero screenshot per curated screen** (this app has 4 screens → 4
  screenshots) per device family, at the **largest required size** per family
  (the skill's default — "full" without exploding into every derived size). The
  skill's 5-screen default is just a default; a 4-screen app yields 4.
- Generated Play **feature graphic** (icon-on-gradient).
- The validation **report**.

Screenshots are **demo artifacts** (they will drift with OS/simulator versions);
they are never used as pixel-diff goldens. A future eval tier asserts only on the
stable text metadata tree.

## 6. Phasing

### Phase A — build + commit (this plan)
1. Scaffold the Expo Recipe Box app (screens, deep links, labels, seed data).
2. Verify it builds and runs (`npx expo` sanity check where toolchain allows).
3. Author the Maestro flows under `.listing-kit/flows/` (one per screen, deep-link first).
4. Write `examples/README.md`; add `.gitignore` negation for the committed flows.
5. Link the example from the main `README.md` ("See it in action").

### Phase B — generate + commit output (documented; run on a tooled machine)
Requires Node + Xcode/Android SDK + a booted simulator/emulator + Maestro.
`examples/README.md` records the exact procedure: run listing-kit against
`examples/expo-recipe-box/`, then commit the produced `fastlane/` tree. This run
is also the first real end-to-end dogfood of the skill; bugs found here feed back
into `skills/listing-kit/`.

## 7. CI & maintenance

- **No new per-push CI** for this. Building the app + running simulators is heavy
  and flaky; it is not gated on every push.
- Phase-B regeneration is **periodic/manual**, not per-PR. `CONTRIBUTING.md` notes
  that example output is regenerated occasionally and may lag the latest OS sizes.
- The existing `tests/` suite is unaffected. (Optional, later: a lightweight
  structure test asserting `examples/expo-recipe-box/app.json` is valid and the
  committed flows are valid YAML — additive, no new deps.)

## 8. Documentation

`examples/README.md` covers:
- What Recipe Box is and which screens map to which store screenshots.
- The exact command + environment used to generate the committed output (Phase B).
- The "make your app listing-kit-ready" checklist, pointing at the app's own deep
  links / labels / demo-data as the worked example.

Main `README.md` gains a short "See it in action" link to `examples/`.

## 9. Future (out of scope here)

- Native iOS (SwiftUI), native Android (Compose), and Flutter example apps —
  distinct apps each, same structure.
- An eval tier: run the skill headless against each example and assert on the
  generated text metadata (character limits, required fields, fastlane layout),
  as a manual/nightly job.
