# App-owned marketing templates

From the app root, run `listing-kit template new acorn`. Edit the commented starter at `.listing-kit/templates/acorn.html`. Add an optional `acorn.css` beside it for styles that apply after the HTML's stylesheets. The command refuses to overwrite an existing file.

Set `style.mode` to `framed` and `style.template` to `user:acorn` in the plan. A target can override the plan, and a screen can override the target. Both accept `style.template` or a direct `template` key. A direct key takes precedence within the same screen or target. A graphic takes a direct `template` key. Raw screenshots and derived icons keep their own rendering paths.

Use `user:<name>` for every app template. Names match `[a-z0-9-]+`. The kit reserves the bare names `caption-top`, `caption-bottom`, `full-bleed`, `band`, `panel`, `feature` and `header`. To select an app file with one of those names, use the explicit form, for example `user:band` for `.listing-kit/templates/band.html`.

For a framed screenshot, `caption-top` places the caption and detail above the device. `caption-bottom` places them below it. Both support a contained device or a device that bleeds off the opposite edge. With `fit: "cover"`, `caption-bottom` fills the device frame above the caption and crops the capture to fit. `full-bleed` always uses a cover crop to fill the canvas. It overlays the caption and detail on a bottom gradient tinted with the last palette background color. Choose ink and detail colors that contrast with the scrim over your capture. Compose checks both against the rendered background.

## A screenshot template

```html
<!doctype html>
<html lang="{{lang}}" dir="{{dir}}">
<meta charset="utf-8">
<link rel="stylesheet" href="/base.css">
<link rel="stylesheet" href="/fonts.css">
<style>
body { padding: calc(5 * var(--u)); gap: 2vmin }
.headline { font-size: 7vmin }
.detail { font-size: 4vmin }
img { flex: 1; min-height: 0; width: 100%; object-fit: contain }
</style>
<body data-fit="{{fit}}">
<h1 class="headline" data-check="text">{{caption}}</h1>
<p class="detail" data-check="text">{{detail}}</p>
<img data-check="device" src="/raw.png" alt="">
</body>
</html>
```

## Values and measurements

| Input | How to use it |
| --- | --- |
| `{{caption}}`, `{{detail}}`, `{{headline}}` | Localized, HTML-escaped text. Use caption and detail on shots, headline on panels and graphics. An absent value expands to empty text. Place these inside elements marked `data-check="text"`. |
| `{{rows}}`, `{{brand}}` | Kit-generated markup. Put rows inside a panel's `dl` for measured label and text pairs. Brand supplies the plan logo when available, otherwise the listing name. Insert both in element content. |
| `{{lang}}`, `{{dir}}`, `{{fit}}` | Use in the `lang`, `dir` and `data-fit` attributes as shown. The kit supplies the store locale, `ltr` or `rtl`, and `contain`, `cover` or `bleed`. |
| `/raw.png` | The selected screenshot capture. Mark its image or wrapper with `data-check="device"` for the crop check. Omit it for panels and graphics. |
| `/base.css` | Shared layout and typography. The viewport is the exact target width and height in CSS pixels. Use `100vw` and `100vh` for its dimensions. On the body, `--u` is one percent of the shorter side. |
| `/fonts.css` | Plan styles. Use `--bg-a` and `--bg-b` for gradient endpoints, `--ink` and `--detail` for text colors, and `--font-headline` and `--font-detail` for the locale's ordered font stacks. |
| Frame geometry | `--shot-w` and `--shot-h` give the capture's pixel dimensions when present. `--bezel` and `--shadow` are colors. Multiply `--bezel-w` and `--radius` by `--u` for lengths. |

Use the two plan font roles on measured text. Point a role at an app font such as `.listing-kit/templates/brand.ttf` to include it in glyph coverage checks. The kit also checks text overflow, line count, contrast and capture cropping, then verifies the slot dimensions and opaque RGB PNG format.

## Local resources and preview

Use ordinary layout and text elements, `img src`, stylesheet links, inline styles and CSS `url(...)`. Image files can be PNG, JPEG, WebP or standalone SVG shapes. SVG gradients and other definitions can refer to IDs in the same image. Local CSS can reference fonts in TTF, OTF, WOFF or WOFF2 format. Resource paths are relative to the containing file. Use portable filenames and forward slashes for nested folders. Quote CSS URLs containing spaces. Use `bundled:fonts/Inter.ttf` to address a file under the kit's assets directory. The three virtual URLs in the table are supplied by the composer.

The loader checks each reference before rendering. It rejects symlinks, parent traversal, filesystem paths, remote and data URLs, scripts, event attributes, navigation, embedded documents and network hints. Use a stylesheet link for additional CSS. The loader accepts layout, color and transform functions and rejects CSS escapes and indirect resource functions such as `image-set()`.

Each template can use up to 128 assets and 32 MiB total, including its HTML. HTML, CSS and SVG files can each use up to 1 MiB, raster images 16 MiB and fonts 8 MiB. The plan can load up to 128 MiB across its distinct templates. Template loading shares one deadline across the plan, 60 seconds by default. Set `LK_BROWSER_TIMEOUT` in seconds to adjust it.

Run `listing-kit plan check` for file and line diagnostics. Run `listing-kit compose --preview` to inspect the layout. A user template needs the headless renderer for preview. The preview embeds its rendered PNG so opening the gallery never loads app markup. Changes to the HTML, companion CSS or referenced files go through the usual `listing-kit compose --restyle` approval when existing images would change style.
