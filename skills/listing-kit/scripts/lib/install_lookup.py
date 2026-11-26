"""Installation lookup embedded in generated launchers and Git hooks."""
import os
from pathlib import Path
import re


class Blocked(Exception):
    pass


def version(kit):
    if not kit.is_absolute() or not (kit / "scripts/lib/secret_scan.py").is_file():
        return ()
    try:
        value = (kit / "VERSION").read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return ()
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?", value)
    if not match:
        return ()
    major, minor, patch, pre = match.groups()
    parts = [(0, int(p)) if p.isdigit() else (1, p) for p in (pre or "").split(".")]
    return int(major), int(minor), int(patch), pre is None, parts


def channel_for(kit):
    # <market>/listing-kit/<version>/skills/listing-kit
    if (kit.name == "listing-kit" and kit.parent.name == "skills"
            and kit.parent.parent.parent.name == "listing-kit"):
        return kit.parents[2]
    return None


def newest(recorded, channel, available=version):
    candidates = [recorded]
    if channel and channel == channel_for(recorded) and channel.is_dir():
        candidates.extend(p for p in channel.glob("*/skills/listing-kit")
                          if p.resolve() == p)
    return max((p for p in candidates if available(p)), key=version, default=recorded)


def find_kit(recorded, channel, available=version):
    override = os.environ.get("LISTING_KIT_HOME")
    if override:
        path = Path(override)
        if available(path):
            return path
        raise Blocked("LISTING_KIT_HOME must name an absolute installed kit")
    path = recorded if available(recorded) else newest(recorded, channel, available)
    if available(path):
        return path
    raise Blocked("listing-kit installation not found; set LISTING_KIT_HOME or reinstall")
