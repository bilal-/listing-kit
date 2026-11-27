"""Check the pixel-affecting sources against the reviewed renderer version."""
import argparse
import hashlib
import inspect
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "skills/listing-kit"
COMPOSE = KIT / "scripts/compose"
sys.path.insert(0, str(COMPOSE))

import compose
import imginfo

RECORD = ROOT / "tests/fixtures/renderer-version.json"
RECORD_COMMAND = "python3 tests/unit/renderer_version.py --record"


def snapshot():
    sources = [COMPOSE / name for name in ("render.py", "cdp.py", "pixels.py", "fontcheck.py")]
    sources.append(KIT / "scripts/lib/template_values.py")
    sources.append(KIT / "scripts/lib/user_templates.py")
    templates = KIT / "templates"
    sources.extend(sorted(templates.glob("*.html")))
    sources.append(templates / "base.css")
    hashes = {p.relative_to(KIT).as_posix(): compose.sha_file(p) for p in sources}
    for module, names in (
        (compose, ("text_of", "flatten_rgb", "Job", "build", "verify_rgb")),
        (imginfo, ("_png_passes", "_png", "_inspect", "image_info")),
    ):
        path = Path(module.__file__).relative_to(KIT).as_posix()
        for name in names:
            source = inspect.getsource(getattr(module, name))
            hashes[f"{path}:{name}"] = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return {
        "RENDERER_VERSION": list(compose.RENDERER_VERSION),
        "sha256": hashes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true", help="record the reviewed sources and version")
    args = parser.parse_args()
    current = snapshot()
    if args.record:
        RECORD.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return
    recorded = json.loads(RECORD.read_text(encoding="utf-8"))
    if current == recorded:
        return
    before, after = recorded["sha256"], current["sha256"]
    changed = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
    if changed:
        print("Renderer sources changed: " + ", ".join(changed), file=sys.stderr)
    if current["RENDERER_VERSION"] != recorded["RENDERER_VERSION"]:
        print("RENDERER_VERSION changed. Record the new version and hashes.", file=sys.stderr)
    elif any(p.startswith("scripts/") for p in changed):
        print("Bump RENDERER_VERSION in compose.py if renderer code changed pixels, then re-record. "
              "If pixels are unchanged, just re-record.", file=sys.stderr)
    if any(p.startswith("templates/") for p in changed):
        print("Template and base.css edits are fingerprinted by content and only need a re-record.",
              file=sys.stderr)
    sys.exit("Re-record with: " + RECORD_COMMAND)


if __name__ == "__main__":
    main()
