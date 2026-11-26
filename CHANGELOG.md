# Changelog

Notable changes to listing-kit. Versions follow the plugin manifest
(`.claude-plugin/plugin.json`).

## Unreleased

- README shows the real version, and a test keeps it in step with the manifest.
- The bundled example is validated as committed, and `examples/README.md` must
  agree with the validator's result. It currently fails one check: the iPhone
  Dynamic Island (medium display) set has not been recaptured.
- The guide's output tree lists `store-assets/` and the asset plan.

## 0.5.0 (2026-10-07)

- Apple upload slots are validated by exact size: a large-display iPhone
  screenshot no longer fills the required medium-display slot.
- Apple header assets under `store-assets/apple/<locale>/`, validated and shown
  on the review page.
- `.listing-kit/asset-plan.json` records the approved Apple screenshot sets and
  headers, with deferrals; store-required sets cannot be deferred.
- iPhone Duo sizes, with a preflight that defers Duo capture when the tooling is
  missing.
- `capture-ios.sh` rejects wrong-size and blank captures before replacing a file.
- The commit hook refreshes `listing-review.html` when any staged listing input
  changes, including creative asset folders, flows and app configuration.
- Malformed URLs and non-UTF-8 copy are reported without breaking the review page.
- The asset plan and creative asset folders are scanned for credentials.

## 0.4.0 (2026-10-04)

- Brand kit and logo set; project site at listing-kit.bilal.sh.
- Codex install instructions.
- `docs/ARCHITECTURE.md` replaces the earlier plans and specs.

## 0.3.1 and earlier

See the [release list](https://github.com/bilal-/listing-kit/releases).
