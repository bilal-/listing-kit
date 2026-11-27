"""The plan values accepted by the bundled marketing templates."""
import re

TEMPLATES = ("caption-top", "caption-bottom", "full-bleed", "band", "panel", "feature", "header")


def template_name(name):
    if name not in TEMPLATES:
        raise ValueError("unknown template %r (expected one of %s)" % (name, ", ".join(TEMPLATES)))
    return name


def colour(value):
    return isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?", value) is not None


def measurement(value, limit):
    return type(value) in (int, float) and 0 <= value <= limit
