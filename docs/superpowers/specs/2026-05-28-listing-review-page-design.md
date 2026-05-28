# Listing Review Page — Requirements & Design

**Status:** Finalized — ready for an implementation plan
**Date:** 2026-05-28
**Author:** Bilal Ahmad

> A single, static HTML page that gathers everything listing-kit produced — store
> copy (with copy buttons), screenshots per device class, generated graphics, and
> the validator's results — into one reviewable view, so a human can check the
> output and copy fields into the store consoles without digging through the
> `fastlane/` tree.

---

## 1. Problem & Motivation

listing-kit writes a fastlane tree: many `.txt` files across two layouts plus
screenshots in several directories. Reviewing that output today means opening
files one by one and reading `validate-listing.sh` separately. There is no single
place to (a) read each copy field against its limit, (b) copy a field to paste
into App Store Connect / Play Console, (c) see the screenshots grouped by device,
and (d) see what still fails validation.

**Goal:** an Assemble-time artifact, `listing-review.html`, that presents the
whole listing for review, with copy buttons and an iOS/Android toggle, generated
from the fastlane tree with no new runtime dependency.

---

## 2. Resolved Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Core nature | **Static, read-only preview** | No server; open in any browser. Edits still happen in the `.txt` files / by re-running the skill. Portable, simplest. |
| Screenshots | **Linked by relative path** | Tiny HTML, always in sync with the tree. Lives at the app root beside `fastlane/`. |
| Content | **Full review incl. validation** | Per-field char count vs limit (✓/✗); embedded validator banner + result lines; screenshot galleries; generated graphics. |
| Validation source | **Embed `validate-listing.sh` output verbatim** | The validator (just hardened) stays untouched. `build-review.sh` runs it once and embeds its banner + lines. The per-field count badge is a render-time convenience computed by the generator. |
| Layout | **Two-column (copy ↔ screenshots), platform toggle on top** | Review words next to visuals. Collapses to single column on narrow screens. |
| Implementation | **`bash` wrapper + embedded `python3`** | Matches `validate-listing.sh`'s style and the repo's existing `python3` use; no new dependency. |

---

## 3. Architecture

### 3.1 Script — `skills/listing-kit/scripts/package/build-review.sh`

```
build-review.sh [<app-root>]      # default: current directory
```

- Same arg/exit convention as `validate-listing.sh`: exit 2 on usage / no
  `fastlane/`, exit 0 otherwise. **Read-only — never writes into `fastlane/`.**
- A `bash` wrapper that delegates the scan + HTML emission to an embedded
  `python3` heredoc (mirrors `validate-listing.sh`). If `python3` is absent, fail
  with a clear message (consistent with the other scripts).
- The script:
  1. Detects which stores are present under `<root>/fastlane/`:
     - **iOS** = a `metadata/<locale>/` (locale ≠ `android`) with `name.txt`/`description.txt`, or a `screenshots/` dir.
     - **Android** = `metadata/android/<locale>/`.
  2. For each present platform + locale, collects:
     - **Copy fields** — label, value, char count (computed after `rstrip`, mirroring the validator), limit, and ok/over. Limits match `references/stores/` (iOS: name 30, subtitle 30, promotional_text 170, keywords 100, description 4000; Android: title 30, short_description 80, full_description 4000).
     - **Screenshots** — grouped by device class, recognized by pixel dimensions using the same families as the validator (iPhone 6.9/6.7/6.5, iPad 12.9/13, iPad 11; Android phone vs tablet). Each rendered as a relative `<img src>` thumbnail.
     - **Graphics** — Play feature graphic and icon, with dimensions.
  3. Runs `validate-listing.sh <root>` once, strips ANSI, and embeds the banner
     and per-line results verbatim.
  4. Emits one `listing-review.html` at the app root.

### 3.2 The page (layout B)

- **Self-contained markup:** inline CSS + a small inline `<script>` only — no
  external assets, no framework. Screenshots are the only external references
  (relative paths).
- **JS scope:** platform tab toggle; copy-to-clipboard (`navigator.clipboard`
  with a hidden-textarea + `execCommand` fallback for `file://`).
- **Header:** app name + an `[ iOS | Android ]` toggle showing only the platforms
  actually present.
- **Per platform:** a validation banner (pass/fail + counts) on top, then two
  columns:
  - **Left:** copy rows (`label · value box · count/limit badge with ✓/✗ · Copy`),
    followed by the embedded validator result lines.
  - **Right:** screenshot galleries grouped/labelled by device class, then the
    generated graphics.
- **Responsive:** columns collapse to a single stacked column below ~720px.
- **Missing/empty required fields** render with a ⚠ marker and no value (see §4).

### 3.3 Integration

- **SKILL.md Assemble (step 11):** after the secret scan, run `build-review.sh`
  to emit the review page. Add a row to the Scripts table and the Reference map.
- **README / GUIDE:** one line noting `listing-review.html` as the reviewable
  output. **CONTRIBUTING:** mention the new script + its test.
- **repo-consistency test:** add `package/build-review` to the expected-scripts
  list; the SKILL.md reference appears as a backticked `scripts/...` path so the
  existing link-checker covers it.

---

## 4. Related skill fix — never fabricate metadata

Bundled because it determines what the review page shows for un-provided fields.

- The **Configure** step (SKILL.md step 6) and any copy drafting **must never
  fabricate** values that can only come from the user: **support / marketing /
  privacy-policy URLs, copyright, category.**
- When such a value is unknown (including under `--non-interactive`), **leave the
  field unwritten — omit the file.** **Do not invent a plausible value, and do not
  record a TODO.** Omitting (rather than writing an empty file) matters: the
  validator flags an absent required field as missing, whereas an empty file would
  "pass" at 0 chars and hide that it was never filled. The review page shows any
  absent required field with a ⚠ marker.
- SKILL.md wording updated to state this rule explicitly.

---

## 5. Testing

`tests/unit/build-review.test.sh`, run against `examples/expo-recipe-box` (a full
both-stores tree):

- Exits 0 and writes `listing-review.html`.
- Contains both platform toggles (iOS and Android).
- Contains at least one `Copy` button and the copy JS.
- References a screenshot by relative path (`fastlane/screenshots/...`).
- Embeds the validation banner (e.g. `LISTING VALID` / the checks line).
- Shows char-count badges (e.g. `23/30`).
- Negative: a directory with no `fastlane/` → exit 2.

Add the script to the `repo-consistency` expected-scripts loop so its presence +
executability is covered.

---

## 6. Out of Scope (v1)

- Editing fields in the page / writing back to disk (would need a server).
- Embedding screenshots as base64 (chose relative links).
- Multi-locale UI beyond rendering each locale present (v1 listings are en-US).
- Device frames / captions, visual diff embedding (separate features).
- Any change to `validate-listing.sh`'s logic (we only consume its output).

---

## 7. Risks

- **Validator output parsing:** we embed text verbatim rather than parse it, so a
  wording change in the validator can't break the page — it just shows the new
  text. Low risk.
- **`file://` clipboard:** `navigator.clipboard` may be blocked on `file://` in
  some browsers; the textarea + `execCommand` fallback covers that.
- **Large screenshots:** linked, not embedded, so page weight stays trivial.
