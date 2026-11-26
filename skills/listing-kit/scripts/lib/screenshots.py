"""Select the screenshots visible in each store and bind them to upload slots."""

import os
from pathlib import Path
from typing import NamedTuple, Optional

import imginfo
import listing
import specs


class Shot(NamedTuple):
    path: Path
    platform: str
    slot: Optional[dict]
    size: tuple
    error: str = ""
    manual: bool = False


def active(root, store, locale, rules, deferred=(), nonempty=os.path.getsize, tree=None):
    root = Path(root)
    tree = tree if tree is not None else listing.paths(root)[store]
    if store == "apple":
        for platform, directory in listing.apple_screenshot_dirs(tree["screenshots"], locale, rules):
            paths = [Path(p) for p in listing.images(directory) if nonempty(p)]
            framed = any(p.stem.lower().endswith("_framed") for p in paths)
            for path in paths:
                size = imginfo.image_info(path)[:2]
                relative = path.relative_to(tree["screenshots"])
                slot = specs.apple_slot_for_file(rules, *size, str(relative))
                if framed and not path.stem.lower().endswith("_framed") and not (slot and slot["id"] == "watch"):
                    continue
                if slot and slot["id"] in deferred:
                    continue
                error = ""
                if not slot or platform == "appleTV" and slot.get("folder") != platform:
                    error = "{}: {}x{} is not an App Store screenshot size for this folder".format(path.name, *size)
                yield Shot(path, "iMessage" if platform == "iMessage" else "", slot, size, error)
    else:
        directory = tree["metadata"] / locale / "images"
        for slot in specs.slots(rules, store):
            if slot.get("folder"):
                for name in listing.images(directory / slot["folder"]):
                    if nonempty(name):
                        yield Shot(Path(name), "", slot, imginfo.image_info(name)[:2])

    directory = tree["storeAssets"] / locale / "screenshots"
    if directory.is_dir():
        for folder in sorted(directory.iterdir()):
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            slot = specs.slot(rules, store, folder.name)
            if not slot:
                yield Shot(folder, "", None, (), f"{folder}: unknown {store} slot {folder.name}", True)
                continue
            for name in listing.images(folder):
                if not nonempty(name):
                    continue
                size = imginfo.image_info(name)[:2]
                fits = (slot in specs.apple_slots_for_size(rules, *size) if store == "apple"
                        else not any(specs.play_size_errors(slot, *size)))
                if not fits:
                    yield Shot(Path(name), "", slot, size,
                               f"{name} does not fit {store.title()} slot {folder.name}", True)
                elif slot["id"] not in deferred:
                    yield Shot(Path(name), "", slot, size, manual=True)
