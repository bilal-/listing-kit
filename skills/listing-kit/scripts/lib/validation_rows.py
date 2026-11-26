"""Collect per-locale field checks and image facts in one validator process."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apple_assets
import fields
from imginfo import image_row
import listing


def collect(root, cache):
    fl = root / "fastlane"

    def write(key, rows):
        dest = cache / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w", encoding="utf-8", errors="surrogateescape") as stream:
            for row in rows:
                print(row, file=stream)

    def copy_fields(store, directory, fallback=None):
        checks = fields.rows(store, directory, fallback)
        write(Path(store) / directory.relative_to(root) / "rows",
              ("\t".join(fields.check(row)) for row in checks))

    def screenshots(directory):
        write(Path("shots") / directory.relative_to(root) / "rows",
              (image_row(p) for p in listing.images(directory)))

    apple = list(map(Path, apple_assets.apple_locales(root)))
    play = list(map(Path, listing.play_locales(fl)))
    write("apple-locales", apple)
    write("play-locales", play)
    for directory in apple:
        copy_fields("apple", directory, listing.apple_default(fl))
    copy_fields("apple-app", fl / "metadata")
    for directory in (fl / "screenshots").glob("*"):
        if directory.is_dir():
            screenshots(directory)
    for directory in play:
        copy_fields("play", directory)
        images = directory / "images"
        for device in ("phone", "sevenInch", "tenInch", "tv", "wear"):
            screenshots(images / (device + "Screenshots"))
        for image in listing.images(images):
            path = Path(image)
            if path.stem in ("featureGraphic", "icon"):
                write(Path("graphics") / path.relative_to(root), [image_row(image)])


if __name__ == "__main__":
    collect(Path(sys.argv[1]), Path(sys.argv[2]))
