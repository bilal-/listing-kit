"""Load a declarative app template into a closed map of virtual URLs and bytes."""
import argparse
from dataclasses import dataclass
import hashlib
import html
from html.parser import HTMLParser
import os
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.parse import quote, unquote
from xml.parsers import expat

if __package__:
    from . import specs, template_values
    from .regular_files import directory, read_regular
else:
    import specs
    import template_values
    from regular_files import directory, read_regular

KIT = Path(__file__).resolve().parents[2]
FOLDER = ".listing-kit/templates"
NAME = re.compile(r"[a-z0-9-]+")
IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
FONT = {".otf", ".ttf", ".woff", ".woff2"}
VIRTUAL = {"/base.css", "/fonts.css", "/raw.png"}
VALUES = {"lang", "dir", "fit", "caption", "detail", "headline", "rows", "brand"}
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
TAGS = set(("html head title meta link style body main section article header footer aside div span "
            "h1 h2 h3 h4 h5 h6 p strong em b i small br img figure figcaption dl dt dd ul ol li table thead tbody tr th td").split())
ATTRS = set("id class lang dir title alt width height role data-fit data-check".split())
CSS_TOKEN = re.compile(r"""/\*.*?(?:\*/|$)|"[^"\n\r\f]*"|'[^'\n\r\f]*'|(?P<bad_quote>["'])|
    (?P<url>url\(\s*(?P<argument>"[^"\n\r\f]*"|'[^'\n\r\f]*'|[^'"()\s]+)\s*\))|
    (?P<function>[-\w]+)\(|(?P<rule>@[-\w]+)""", re.S | re.I | re.X)
# Functions that compute values or select elements, without fetching resources.
FUNCTIONS = set(("calc min max clamp var env rgb rgba hsl hsla hwb lab lch oklab oklch color color-mix "
                 "linear-gradient radial-gradient conic-gradient repeating-linear-gradient repeating-radial-gradient "
                 "repeating-conic-gradient repeat minmax fit-content translate translatex translatey scale "
                 "scalex scaley rotate matrix skew blur brightness contrast drop-shadow grayscale hue-rotate "
                 "invert opacity saturate sepia cubic-bezier steps polygon circle ellipse inset path "
                 "has not is where nth-child nth-of-type format tech supports selector").split())


@dataclass
class Template:
    page: str
    assets: dict
    digests: dict


class Loader:
    def __init__(self, root):
        self.root = root
        self.assets = {}
        self.digests = {}
        self.errors = []

    def error(self, source, line, message):
        self.errors.append(f"{FOLDER}/{source}:{line}: {message}")

    def asset(self, ref, source, line, types):
        # These three kit-supplied resources are the bundled template interface.
        if ref in VIRTUAL and PurePosixPath(ref).suffix in types:
            return ref
        bundled = ref.startswith("bundled:")
        relative = ref[len("bundled:"):] if bundled else ref
        relative = unquote(relative)
        parts = [part for part in relative.split("/") if part != "."]
        if (not parts or not all(specs.component(part) for part in parts)
                or PurePosixPath(relative).suffix.lower() not in types):
            self.error(source, line, f"disallowed resource {ref!r}")
            return ""
        relative = "/".join(parts)
        name = relative if bundled else str(PurePosixPath(source).parent / relative)
        return self.load(name, source, line, bundled=bundled)

    def load(self, name, source, line, bundled=False, optional=False):
        url = ("/bundled/" if bundled else "/user/") + quote(name)
        if url not in self.assets:
            try:
                data = read_regular(KIT / "assets" if bundled else self.root,
                                    name if bundled else FOLDER + "/" + name)
                key = "bundled:" + name if bundled else FOLDER + "/" + name
                self.digests[key] = hashlib.sha256(data).hexdigest()
                self.assets[url] = data
                if name.lower().endswith(".svg"):
                    self.svg(data, name)
                if name.lower().endswith(".css"):
                    self.assets[url] = self.css(data.decode("utf-8"), name, 1).encode()
            except (ValueError, OSError) as exc:
                if optional and isinstance(exc, FileNotFoundError):
                    return None
                self.error(source, line, f"cannot load {name!r}: {exc}")
        return url

    def css(self, css, source, line, svg=False):
        def fail(pos, reason):
            self.error(source, line + css.count("\n", 0, pos), reason)
        # No escaped identifiers or substitutions into CSS syntax. This keeps URL
        # discovery unambiguous even for conditional rules the browser never uses.
        bad = re.search(r"[\\\x00<]|\{\{", css)
        if bad:
            fail(bad.start(), "CSS escapes, markup and placeholders are unsupported")

        def token(match):
            value = match[0]
            if match["bad_quote"]:
                fail(match.start(), "unterminated CSS string")
            if match["url"]:
                arg = match["argument"]
                ref = arg[1:-1] if arg[0] in ('"', "'") else arg
                if svg:
                    if not re.fullmatch(r"#[A-Za-z_][\w.:-]*", ref):
                        fail(match.start(), f"SVG resource must be an internal fragment: {ref!r}")
                    return value
                url = self.asset(ref, source, line + css.count("\n", 0, match.start()), IMAGE | FONT)
                return f'url("{url}")'
            if match["function"] and match["function"].lower() not in FUNCTIONS:
                fail(match.start(), f"unsupported CSS function {value}")
            if match["rule"] and value.lower() not in {"@media", "@supports", "@font-face", "@layer", "@container",
                                                        "@keyframes", "@property"}:
                fail(match.start(), f"unsupported CSS rule {value}")
            return value
        return CSS_TOKEN.sub(token, css)

    def svg(self, data, source):
        """Standalone SVG images may draw shapes and refer to definitions in the same image."""
        tags = set(("svg g defs symbol use title desc path rect circle ellipse line polyline polygon "
                    "text tspan clipPath mask marker pattern linearGradient radialGradient stop").split())
        parser = expat.ParserCreate(namespace_separator=" ")
        namespace = "http://www.w3.org/2000/svg "

        def reject(message):
            self.error(source, parser.CurrentLineNumber, message)

        def element(tag, attrs):
            if not tag.startswith(namespace) or tag[len(namespace):] not in tags:
                reject(f"disallowed SVG element {tag}")
            for key, value in attrs.items():
                if key in ("href", "http://www.w3.org/1999/xlink href"):
                    if not re.fullmatch(r"#[A-Za-z_][\w.:-]*", value):
                        reject(f"SVG reference must be an internal fragment: {value!r}")
                elif " " in key or key.lower().startswith("on"):
                    reject(f"disallowed SVG attribute {key}")
                else:
                    self.css(value, source, parser.CurrentLineNumber, svg=True)

        def forbidden(*_args):
            raise ValueError("SVG declarations and processing instructions are unsupported")

        parser.StartElementHandler = element
        parser.StartDoctypeDeclHandler = forbidden
        parser.ProcessingInstructionHandler = forbidden
        try:
            parser.Parse(data, True)
        except (ValueError, expat.ExpatError) as exc:
            reject(str(exc))


class Markup(HTMLParser):
    """Rebuild accepted markup so browser error recovery cannot introduce attributes."""
    def __init__(self, loader, source):
        super().__init__()
        self.loader, self.source = loader, source
        self.output = []
        self.stack = []

    def error(self, message, line=None):
        self.loader.error(self.source, line or self.getpos()[0], message)

    def handle_decl(self, decl):
        if decl.lower() != "doctype html":
            self.error("expected HTML doctype")
        self.output.append("<!doctype html>")

    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0]
        if tag not in TAGS:
            self.error(f"disallowed element <{tag}>")
            return
        fields = dict(attrs)
        if len(fields) != len(attrs):
            self.error("duplicate HTML attribute")
        if tag == "link" and ((fields.get("rel") or "").lower() != "stylesheet" or not fields.get("href")):
            self.error("only stylesheet links are supported")
        if tag == "meta" and fields != {"charset": "utf-8"}:
            self.error("only UTF-8 charset metadata is supported")
        output = []
        cursor = len(tag) + 1
        for key, value in attrs:
            # HTMLParser provides the opening tag's line. Locate each attribute
            # within that token, including quoted values spanning several lines.
            match = re.match(r"""\s*([^\s=/>]+)(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?""",
                             self.get_starttag_text()[cursor:])
            attr_line = line
            if match:
                attr_line += self.get_starttag_text().count("\n", 0, cursor + match.start(1))
                cursor += match.end()
            value = value or ""
            if "{{" in value and (key, value) not in {("lang", "{{lang}}"), ("dir", "{{dir}}"), ("data-fit", "{{fit}}")}:
                self.error(f"unsupported substitution in {key}", attr_line)
            if (tag, key) in {("img", "src"), ("link", "href")}:
                value = self.loader.asset(value, self.source, attr_line, IMAGE if tag == "img" else {".css"})
            elif key == "style":
                value = self.loader.css(value, self.source, attr_line)
            elif key not in ATTRS and (tag, key) not in {("link", "rel"), ("meta", "charset")}:
                self.error(f"disallowed attribute {key}", attr_line)
            output.append(f' {key}="{html.escape(value)}"')
        self.output.append("<" + tag + "".join(output) + ">")
        if tag not in {"meta", "link", "img", "br"}:
            self.stack.append((tag, fields.get("data-check")))

    def handle_endtag(self, tag):
        if tag in TAGS:
            self.output.append(f"</{tag}>")
            while self.stack:
                if self.stack.pop()[0] == tag:
                    break

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in {"meta", "link", "img", "br"}:
            self.handle_endtag(tag)

    def handle_data(self, data):
        line = self.getpos()[0]
        if self.stack and self.stack[-1][0] == "style":
            self.output.append(self.loader.css(data, self.source, line))
            return
        for match in PLACEHOLDER.finditer(data):
            key = match[1]
            where = line + data.count("\n", 0, match.start())
            if key not in VALUES:
                self.error(f"unknown template value {key}", where)
            if key in {"caption", "detail", "headline"} and not any(check == "text" for _, check in self.stack):
                self.error(f'{key} requires data-check="text"', where)
        self.output.append(html.escape(data, quote=False))


def resolve(root, selection):
    """Return None for built-ins, or the checked bytes used for both hashing and rendering."""
    if selection in template_values.TEMPLATES:
        return None
    name = selection if isinstance(selection, str) else ""
    if name.startswith("user:"):
        name = name[5:]
    if not NAME.fullmatch(name):
        raise ValueError(f"invalid template name {selection!r} (expected [a-z0-9-]+)")
    source = name + ".html"
    try:
        data = read_regular(root, FOLDER + "/" + source)
    except FileNotFoundError as exc:
        raise ValueError(f"unknown template {selection!r}: missing {FOLDER}/{source}") from exc
    except (OSError, ValueError) as exc:
        raise ValueError(f"{FOLDER}/{source}:1: {exc}") from exc
    loader = Loader(root)
    markup = Markup(loader, source)
    try:
        markup.feed(data.decode("utf-8"))
        markup.close()
    except (ValueError, AssertionError) as exc:
        loader.error(source, markup.getpos()[0], f"invalid HTML: {exc}")
    loader.digests[FOLDER + "/" + source] = hashlib.sha256(data).hexdigest()
    url = loader.load(name + ".css", source, 1, optional=True)
    if url:
        markup.output.append(f'<link rel="stylesheet" href="{url}">')
    if loader.errors:
        raise ValueError("\n".join(loader.errors))
    return Template("".join(markup.output), loader.assets, loader.digests)


def main():
    parser = argparse.ArgumentParser(prog="listing-kit template new")
    parser.add_argument("name")
    args = parser.parse_args()
    try:
        if not NAME.fullmatch(args.name):
            raise ValueError("template name must match [a-z0-9-]+")
        starter = (KIT / "templates/starter/screenshot.html").read_bytes()
        with directory(".", FOLDER, create=True) as parent:
            name = args.name + ".html"
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=parent)
            with os.fdopen(fd, "wb") as stream:
                stream.write(starter)
        print(f"{FOLDER}/{name}")
    except (ValueError, OSError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
