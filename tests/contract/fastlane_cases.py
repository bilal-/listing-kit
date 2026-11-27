"""Describe actual listing-kit argv and the example's expected deliver assignments for CI."""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/listing-kit/scripts/fastlane"))
import lk_fastlane as lk


def cases(root):
    options = {}
    commands = {}
    rules = lk.specs.load()
    example = ROOT / "examples/expo-recipe-box/fastlane"
    apple = {}
    # S3's fastlane 2.242.0 display types for the slots present in the example.
    display_types = {"iphone-di-large": "APP_IPHONE_67", "iphone-di-medium": "APP_IPHONE_61",
                     "ipad-13": "APP_IPAD_PRO_3GEN_129"}
    for path in (example / "screenshots").rglob("*"):
        if path.suffix.lower() in lk.IMAGE:
            rel = path.relative_to(example / "screenshots").as_posix()
            slot = lk.specs.apple_slot_for_file(rules, *lk.imginfo.image_info(path)[:2], rel)
            apple[rel] = display_types[slot["id"]]
    for store, action in (("apple", "deliver"), ("play", "supply")):
        target = lk.Store(store, "test.example", root, {}, rules, {}, {}, "production", "7", root / "key")
        calls = []

        def download(args, cwd):
            calls.append(args)
            if "--metadata_path" in args:
                Path(args[args.index("--metadata_path") + 1]).mkdir()

        with patch.object(target, "run", download):
            lk.download(target, root / store)
        for key in ("metadata/en-US/name.txt", "screenshots/en-US/01.png", "metadata/en-US/changelogs/7.txt"):
            if store == "play" or key.startswith("screenshots/"):
                calls.append(lk.upload_args(target, {key: Path(key)}, root))
        if store == "play":
            target.validate_only = True
            calls.append(lk.upload_args(target, {"metadata/en-US/title.txt": Path("title.txt")}, root))
        commands[action] = sorted({args[1] for args in calls})
        options[action] = sorted({arg[2:] for args in calls for arg in args if arg.startswith("--")})
    return dict(options=options, apple=apple, commands=commands)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        print(json.dumps(cases(Path(tmp))))
