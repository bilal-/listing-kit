"""Read JSON files and check in-memory inputs with the same numeric and nesting limits."""
import json
import math


def _members(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object member %r" % key)
        result[key] = value
    return result


def _integer(value):
    if len(value.lstrip("-")) > 78:
        raise ValueError("integer too large")
    return int(value)


def validate(value, path="$", depth=0):
    if depth > 128:
        raise ValueError("%s: JSON nesting too deep" % path)
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("%s: expected string object key" % path)
            validate(key, path, depth + 1)
            validate(item, "%s.%s" % (path, key), depth + 1)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            validate(item, "%s[%d]" % (path, i), depth + 1)
    elif isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("%s: invalid Unicode string" % path)
    elif isinstance(value, int):
        if value.bit_length() > 256:
            raise ValueError("%s: integer too large" % path)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("%s: expected finite JSON number" % path)
    elif value is not None:
        raise ValueError("%s: expected JSON value" % path)


def _constant(value):
    raise ValueError("%s is not a JSON number" % value)


def read(stream):
    try:
        value = json.load(stream, object_pairs_hook=_members, parse_int=_integer, parse_constant=_constant)
    except RecursionError:
        raise ValueError("JSON nesting too deep")
    validate(value)
    return value
