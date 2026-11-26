"""Read Xcode's OpenStep property list and follow native application target references."""

import json
import plistlib
import re

TOKEN = re.compile(r'\s+|/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|[{}()=;,]|(?:(?!/\*|//)[^\s{}()=;,"])+', re.S)


def openstep(text):
    # Parse containers so quoted shell scripts, comments and unrelated targets
    # cannot accidentally contribute a setting or configuration reference.
    tokens = iter(m[0] for m in TOKEN.finditer(text)
                  if not m[0].isspace() and not m[0].startswith(("/*", "//")))

    def take():
        try:
            return next(tokens)
        except StopIteration:
            raise ValueError("incomplete Xcode project")

    def atom(token):
        if token.startswith('"'):
            return re.sub(r'\\(.)', r'\1', token[1:-1])
        if token in '{}()=;,':
            raise ValueError("expected property list string")
        return token

    def value(token):
        if token == "{":
            result = {}
            key = take()
            while key != "}":
                if take() != "=":
                    raise ValueError("expected assignment")
                result[atom(key)] = value(take())
                if take() != ";":
                    raise ValueError("expected semicolon")
                key = take()
            return result
        if token == "(":
            result = []
            item = take()
            while item != ")":
                result.append(value(item))
                item = take()
                if item == ",":
                    item = take()
                elif item != ")":
                    raise ValueError("expected separator")
            return result
        return atom(token)

    return value(take())


def application_settings(path):
    """Yield one settings dictionary per configuration, or None for unresolved references."""
    data = path.read_bytes()
    if data.lstrip().startswith((b'<?xml', b'<plist', b'bplist')):
        project = plistlib.loads(data)
    else:
        try:
            project = json.loads(data)
        except json.JSONDecodeError:
            project = openstep(data.decode())
    objects = project["objects"]
    for target in objects.values():
        if target.get("isa") != "PBXNativeTarget" or target.get("productType") != "com.apple.product-type.application":
            continue
        configs = objects.get(target.get("buildConfigurationList"), {})
        refs = configs.get("buildConfigurations")
        if configs.get("isa") != "XCConfigurationList" or not isinstance(refs, list) or not refs:
            yield None
            continue
        for ref in refs:
            config = objects.get(ref, {})
            settings = config.get("buildSettings")
            yield settings if config.get("isa") == "XCBuildConfiguration" and isinstance(settings, dict) else None
