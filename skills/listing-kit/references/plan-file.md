# The listing plan

Save UTF-8 JSON at `.listing-kit/listing.json` in the app root. Format 2 requires `format`, `app`, `locales`, `targets` and `screens`. Run `listing-kit plan check` before building. Missing source files can produce warnings during planning. Choose the style before capture. Raw jobs require the exact upload size. Use `listing-kit plan check --for capture` once the active flows exist. Use `listing-kit plan check --for publish` to catch drafts and stale outputs.

Use this single plan for new listings. Validation fails if a screenshot or graphic is missing at its planned output path. The last column of `listing-kit plan outputs` gives the exact path. Validation counts the outputs for each store locale after applying target `locales` and screen `only` or `except` filters. Apple checks exact counts per display and filenames for planned headers. Play reports a warning when a type has a different count. Review and the hand-upload index show why an optional Apple display was deferred. The publish preview checks coverage for its selected store and upload route.

## Format compatibility

Format 2 is stable. Each kit reads its own plan format and every older format it documents. Format 2 is the first documented kit plan format. When a plan uses a newer format, the kit refuses it, reports both the plan's format and the format it supports, and asks you to update listing-kit.

Adding an optional key keeps the same format number. Removing a key or changing its meaning requires a new format number. Unknown top-level keys are validation errors. Update the kit before using an optional key introduced by a later release.

## Port an existing listing

1. Run `listing-kit detect` and `listing-kit validate` at the app root. With an unversioned JSON object at the plan path, these commands use project files and the existing store directories. Use `listing-kit review` to inspect the finished images already on disk.
2. Search the repository for consumers of `listing.json` and `asset-plan.json`, including capture scripts, CI and packaging jobs. Preserve the original plan as `.listing-kit/listing.legacy.json`. Check that the backup path is unused before copying, and compare the bytes before editing the original. Update existing consumers to read their intended file.
3. Map the app IDs, store locale codes, ordered screens and target sizes to format 2. Match each size to its store slot, preserve filename suffixes and put localized image descriptions in `altText`. Review route and flow choices, panels, deferrals and store-specific console values with the maintainer. Hand-written plans have no common schema.
4. Compare `listing-kit plan outputs` with existing filenames. To reuse archived unframed captures, set a target's optional `rawPattern`, for example `"archive/tablet/{locale}/{index}_{screen}.png"`. The pattern is app-relative. It accepts `{target}`, `{screen}`, the capture locale ID `{locale}`, and the two-digit gallery position `{index}`. Compose reads those PNGs. Capture continues to write to `.listing-kit/raw/`.
5. Use `listing-kit compose --preview` to inspect proposed artwork in `.listing-kit/preview.html`. Both preview and dry run accept repeated `--target` and `--screen` IDs. A job must match both filters when both are supplied. For example, `listing-kit compose --preview --screen legend` previews that screen across targets. Panels and graphics use their declared inputs. Missing raw captures produce labeled gaps and a failing exit status while available jobs still appear. Finished store artwork belongs in the review gallery.

## Example

This is the [test fixture](../../../tests/fixtures/plan-example.json). The annotations below the block keep the JSON directly usable. The paths and copy belong to the example app. Replace them for a real capture.

```json
{
  "format": 2,
  "app": {
    "ios": "sh.bilal.shellbell",
    "android": "sh.bilal.shellbell",
    "demoEntry": ".listing-kit/entry.ts"
  },
  "locales": [
    "en-US"
  ],
  "style": {
    "mode": "framed",
    "template": "caption-top",
    "palette": {
      "background": [
        "#F6BC4A",
        "#E79B19"
      ],
      "ink": "#17191D",
      "detail": "#493416"
    },
    "bezel": {
      "color": "#17191D",
      "bleed": false
    },
    "fonts": {
      "default": {
        "headline": [
          "assets/fonts/Brand-Bold.ttf",
          "bundled:Inter"
        ],
        "detail": [
          "assets/fonts/Brand-Regular.ttf",
          "bundled:Inter"
        ]
      }
    },
    "logo": "brand/logo.png"
  },
  "targets": [
    {
      "id": "iphone-medium",
      "store": "apple",
      "slot": "iphone-di-medium",
      "size": [
        1206,
        2622
      ],
      "suffix": "iphone-medium",
      "state": "active",
      "upload": "fastlane",
      "capture": {
        "deviceType": "iPhone 17",
        "display": "internal"
      }
    },
    {
      "id": "duo-outer",
      "store": "apple",
      "slot": "iphone-duo-outer",
      "size": [
        1398,
        2034
      ],
      "state": "deferred",
      "reason": "No Duo runtime installed."
    },
    {
      "id": "play-phone",
      "store": "play",
      "slot": "phone",
      "size": [
        1080,
        1920
      ],
      "state": "active",
      "capture": {
        "deviceType": "pixel_9"
      }
    },
    {
      "id": "play-tablet",
      "store": "play",
      "slot": "ten-inch",
      "size": [
        1920,
        1080
      ],
      "state": "active",
      "style": {
        "template": "band",
        "fit": "contain"
      },
      "capture": {
        "deviceType": "pixel_tablet",
        "orientation": "landscape"
      }
    }
  ],
  "screens": [
    {
      "id": "agents",
      "flow": ".listing-kit/flows/01_agents.yaml",
      "flows": {
        "play-tablet": ".listing-kit/flows/01_agents_tablet.yaml"
      },
      "route": "/c/[fp]",
      "state": "Agents view, one agent waiting, two working.",
      "caption": {
        "en-US": "Every agent, one list"
      },
      "draft": false,
      "detail": {
        "en-US": "Claude Code, Codex, Antigravity, Gemini"
      },
      "altText": {
        "en-US": "..."
      }
    },
    {
      "id": "duo-layout",
      "flow": ".listing-kit/flows/duo-layout.yaml",
      "caption": {
        "en-US": "..."
      },
      "only": [
        "duo-outer"
      ]
    },
    {
      "id": "terminal",
      "flow": ".listing-kit/flows/terminal.yaml",
      "caption": {
        "en-US": "The real terminal, live"
      }
    },
    {
      "id": "closing",
      "except": [
        "play-tablet"
      ],
      "panel": {
        "headline": {
          "en-US": "..."
        },
        "rows": [
          {
            "label": {
              "en-US": "Agents"
            },
            "text": {
              "en-US": "..."
            }
          }
        ]
      }
    }
  ],
  "graphics": {
    "apple": {
      "header-16x9": {
        "headline": {
          "en-US": "..."
        },
        "detail": {
          "en-US": "..."
        },
        "altText": {
          "en-US": "..."
        },
        "template": "header"
      },
      "header-21x9": {
        "headline": {
          "en-US": "..."
        },
        "template": "header"
      }
    },
    "play": {
      "featureGraphic": {
        "template": "feature",
        "headline": {
          "en-US": "..."
        },
        "detail": {
          "en-US": "..."
        },
        "altText": {
          "en-US": "..."
        }
      },
      "icon": {
        "from": "assets/icon.png"
      }
    }
  },
  "console": {
    "playCategory": "Tools",
    "contactEmail": null,
    "playPrivacyUrl": null
  },
  "notes": {}
}
```

## Reading the example

| Key | Meaning |
| --- | --- |
| `format` | Set the format number to 2. |
| `app` | Use `ios` for the bundle ID and `android` for the package name, or use a shared `id` or string when they match. |
| `app.demoEntry` | This optional path identifies an app-owned demo entry in the manifest. The flow must activate demo mode itself. |
| `locales` | A string uses the same code for both stores. An object maps a local `id` to an `apple` or `play` code or both. The first locale supplies fallback copy. |
| `style` | The plan sets the common style. Target settings override it and screen settings apply last. |
| `mode`, `template` | Choose raw or framed screenshots with `mode`. The example selects the caption-top template and overrides it with band for the tablet. An omitted mode is raw. |
| `palette` | `background` lists gradient colors, `ink` sets headline ink and `detail` sets secondary ink. |
| `bezel`, `fit` | The bezel accepts `color`, `shadow`, `width`, `radius` and `bleed`. An explicit `fit` selects contain, cover or bleed for the capture. |
| `fonts` | The `default` profile and optional locale profiles give ordered font paths for the `headline` and `detail` roles. Template rendering needs both font roles, a nonempty background color list and an ink color. The kit includes `bundled:Inter`. |
| `logo` | Supply a local logo for templates that use one. Input paths are app-relative unless prefixed with `repo:` for a path under the repository root. |
| `targets` | Each target has a unique `id`, a `store` (apple or play), a rules-file `slot`, an accepted pixel `size` in width-height order and a `state`. |
| `state`, `reason` | Only active targets produce jobs. A deferred target needs a single-line reason. Use retired for a target no longer in the listing. |
| `suffix`, `upload` | The suffix distinguishes output filenames. The route defaults to the slot's rule and can be fastlane or console. A Play fastlane route needs a slot folder. |
| Target `locales`, `captureLocales` | Limit a target to selected locale IDs, and choose whether captures use the first applicable locale (primary) or each locale (all). |
| `capture` | `deviceType` selects the simulator type or emulator profile. `display` selects the Apple display. `orientation` is portrait or landscape. Optional `runtime`, `nativeSize` and `appId` refine the device, expected capture dimensions and installed app. |
| `screens` | Order the screens as they should appear in the gallery and give each a unique `id`. Filenames get numeric prefixes. |
| `flow`, `flows` | Give a capture screen one Maestro file. An entry in `flows` keyed by target ID takes precedence over a store override and then the base flow. The selected file must exist even for [manual capture](driving/maestro.md#manual-navigation). |
| `route`, screen `state` | These record where the screen lives and what should be visible. Put navigation and assertions in the flow. |
| `caption`, `detail`, `altText` | These hold headline, supporting copy and alternative text keyed by locale ID. Review uses resolved screen and graphic `altText` on images, and the manual upload index prints it beside each file. A missing translation falls back to the primary locale or empty text with a warning. |
| `only`, `except` | Choose one list to include or exclude specific target IDs for this screen. |
| `panel` | A panel replaces the flow with a localized `headline` and `rows`, each containing localized `label` and `text`. It needs no raw capture. |
| `draft`, `status` | A draft target, screen or graphic blocks the publish plan check. Targets and graphics may also record a descriptive status string. |
| `graphics` | Under `apple` or `play`, use a graphic ID from the rules. Headers and the feature graphic take localized headline text and can add detail, alt text, palette, logo and template. Bundled feature and header graphics accept `align` set to `center` (default) or `start` (left in LTR, right in RTL). Set `gap` to the space between the brand, headline and detail, as a percentage of the shorter canvas side (0–100). The Play icon takes its source path in `from`. |
| `console` | Record `playCategory`, `playPrivacyUrl`, `contactEmail` and `contactWebsite` as strings. Set a field to null to request private console entry. For omitted keys, handoff reads `category.txt`, `privacy_url.txt`, `contact_email.txt` and `contact_website.txt` under the Play metadata root or its locale directories. |
| `notes`, `approved` | Notes is a free-form object. Optional approval flags `metadata` and `screens` record decisions in the plan. |
| `platforms` | Set a rule condition such as `supportsIpad` to true or false to override detection. Ask about unknown support before setting a flag. |
| `trees` | Set each store's `fastlaneDir` and optional `metadata`, Apple's `screenshots`, and the shared `storeAssets` directory as app-relative paths. See the [split fixture](../../../tests/fixtures/plan-split.json). |

For an app-owned layout, set `style.template` to its name. Targets and screens also accept a direct `template` key. Screen settings take precedence over target settings. [Template names, files and values](templates.md)

## Inspect the manifest

`listing-kit plan manifest` prints JSON with manifest version 1, resolved app IDs and trees, capture jobs, screenshot and graphic outputs, and stale paths from the output inventory. Multiple localized outputs can share a raw capture. Each output gives its store, slot, locale, size, route and destination. `listing-kit plan outputs` prints four tab-separated columns per output: target (or store), screen (or graphic ID), raw path if present, and output path.
