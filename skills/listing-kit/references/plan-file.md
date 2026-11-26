# The listing plan

Save UTF-8 JSON at `.listing-kit/listing.json` in the app root. Format 2 requires `format`, `app`, `locales`, `targets` and `screens`. Run `listing-kit plan check` before building. Missing source files can produce warnings during planning. Choose the style before capture. Raw jobs require the exact upload size. Use `listing-kit plan check --for capture` once the active flows exist. Use `listing-kit plan check --for publish` to catch drafts and stale outputs.

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
| `caption`, `detail`, `altText` | These hold headline, supporting copy and alternative text keyed by locale ID. A missing translation falls back to the primary locale or empty text with a warning. |
| `only`, `except` | Choose one list to include or exclude specific target IDs for this screen. |
| `panel` | A panel replaces the flow with a localized `headline` and `rows`, each containing localized `label` and `text`. It needs no raw capture. |
| `draft`, `status` | A draft target, screen or graphic blocks the publish plan check. Targets and graphics may also record a descriptive status string. |
| `graphics` | Under `apple` or `play`, use a graphic ID from the rules. Headers and the feature graphic take localized headline text and can add detail, alt text, palette, logo and template. The Play icon takes its source path in `from`. |
| `console` | Record `playCategory`, `contactEmail` and `playPrivacyUrl` as strings or null for manual entry. |
| `notes`, `approved` | Notes is a free-form object. Optional approval flags `metadata` and `screens` record decisions in the plan. |
| `platforms` | Set a rule condition such as `supportsIpad` to true or false to override detection. Ask about unknown support before setting a flag. |
| `trees` | Set each store's `fastlaneDir` and optional `metadata`, Apple's `screenshots`, and the shared `storeAssets` directory as app-relative paths. See the [split fixture](../../../tests/fixtures/plan-split.json). |

## Inspect the manifest

`listing-kit plan manifest` prints JSON with manifest version 1, resolved app IDs and trees, capture jobs, screenshot and graphic outputs, and stale paths from the output inventory. Multiple localized outputs can share a raw capture. Each output gives its store, slot, locale, size, route and destination. `listing-kit plan outputs` prints four tab-separated columns per output: target (or store), screen (or graphic ID), raw path if present, and output path.
