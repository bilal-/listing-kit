"""Load a declarative app template into a closed map of virtual URLs and bytes."""
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import html
from html.parser import HTMLParser
from itertools import groupby
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import sys
import threading
import time
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
MAX_TEXT_BYTES = 1 << 20
MAX_IMAGE_BYTES = 16 << 20
MAX_FONT_BYTES = 8 << 20
MAX_TEMPLATE_BYTES = 32 << 20
MAX_ASSETS = 128
MAX_PLAN_TEMPLATE_BYTES = 128 << 20
ATTRIBUTE = re.compile(r"""\s*([^\s=/>]+)(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?""")
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
    (?P<function>[-\w]+)(?P<call>\()?|(?P<rule>@[-\w]+)""", re.S | re.I | re.X)
# Functions that compute values or select elements, without fetching resources.
FUNCTIONS = set(("calc min max clamp var env rgb rgba hsl hsla hwb lab lch oklab oklch color color-mix "
                 "linear-gradient radial-gradient conic-gradient repeating-linear-gradient repeating-radial-gradient "
                 "repeating-conic-gradient repeat minmax fit-content translate translatex translatey scale "
                 "scalex scaley rotate matrix skew blur brightness contrast drop-shadow grayscale hue-rotate "
                 "invert opacity saturate sepia cubic-bezier steps polygon circle ellipse inset path "
                 "has not is where nth-child nth-of-type format tech supports selector").split())


def new_deadline():
    seconds = float(os.environ.get("LK_BROWSER_TIMEOUT", "60"))
    if not 0 < seconds <= 86400:
        raise ValueError("LK_BROWSER_TIMEOUT must be a positive number of seconds (up to 86400)")
    return time.monotonic() + seconds


class _LoadingAlarm(BaseException):
    """Interrupt a synchronous parser without being caught as malformed input."""


class TemplateTimeout(ValueError):
    pass


def remaining(deadline):
    left = deadline - time.monotonic()
    if left <= 0:
        raise TemplateTimeout("template loading timed out")
    return left


@contextmanager
def loading(deadline):
    # Interrupt synchronous parsers in the CLI, including work inside HTMLParser.
    # Library callers on other threads still check the same deadline between tokens.
    def expired(*_):
        raise _LoadingAlarm

    left = remaining(deadline)
    if threading.current_thread() is threading.main_thread() and not signal.getitimer(signal.ITIMER_REAL)[0]:
        previous = signal.signal(signal.SIGALRM, expired)
        try:
            signal.setitimer(signal.ITIMER_REAL, left)
            yield
        except _LoadingAlarm:
            raise TemplateTimeout("template loading timed out") from None
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
    else:
        yield
    remaining(deadline)


@dataclass(frozen=True)
class Placeholder:
    name: str


@dataclass
class Template:
    tokens: list
    assets: dict
    digests: dict
    virtual: set
    size: int

    def fill(self, values):
        return "".join(values[token.name] if isinstance(token, Placeholder) else token for token in self.tokens)


class Loader:
    def __init__(self, root, deadline, byte_limit):
        self.root = root
        self.deadline = deadline
        self.byte_limit = min(byte_limit, MAX_TEMPLATE_BYTES)
        self.total = 0
        self.virtual = set()
        self.assets = {}
        self.digests = {}
        self.errors = []

    def error(self, source, line, message):
        if len(self.errors) >= 32:
            raise ValueError("\n".join(self.errors))
        self.errors.append(f"{FOLDER}/{source}:{line}: {message}")

    def asset(self, ref, source, line, types):
        # These three kit-supplied resources are the bundled template interface.
        if ref in VIRTUAL and PurePosixPath(ref).suffix in types:
            self.virtual.add(ref)
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

    def read(self, root, relative):
        remaining(self.deadline)
        suffix = PurePosixPath(relative).suffix.lower()
        limit = (MAX_FONT_BYTES if suffix in FONT else
                 MAX_IMAGE_BYTES if suffix in IMAGE - {".svg"} else MAX_TEXT_BYTES)
        data = read_regular(root, relative, min(limit, self.byte_limit - self.total))
        self.total += len(data)
        return data

    def load(self, name, source, line, bundled=False, optional=False):
        url = ("/bundled/" if bundled else "/user/") + quote(name)
        if url not in self.assets:
            try:
                data = self.read(KIT / "assets" if bundled else self.root,
                                 name if bundled else FOLDER + "/" + name)
                if len(self.assets) >= MAX_ASSETS:
                    raise ValueError("too many template assets")
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
        cursor = growth = 0

        def line_at(pos):
            nonlocal line, cursor
            line += css.count("\n", cursor, pos)
            cursor = pos
            return line

        def fail(pos, reason):
            self.error(source, line_at(pos), reason)
        # No escaped identifiers or substitutions into CSS syntax. This keeps URL
        # discovery unambiguous even for conditional rules the browser never uses.
        bad = re.search(r"[\\\x00<]|\{\{", css)
        if bad:
            self.error(source, line + css.count("\n", 0, bad.start()), "CSS escapes, markup and placeholders are unsupported")

        def token(match):
            nonlocal growth
            remaining(self.deadline)
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
                url = self.asset(ref, source, line_at(match.start()), IMAGE | FONT)
                replacement = f'url("{url}")'
                extra = max(0, len(replacement) - len(value))
                growth += extra
                if growth > MAX_TEXT_BYTES or self.total + extra > self.byte_limit:
                    raise ValueError(f"{source}: expanded CSS URLs exceed byte limit")
                self.total += extra
                return replacement
            if match["call"] and match["function"].lower() not in FUNCTIONS:
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
        remaining(self.loader.deadline)
        if len(attrs) > 64:
            self.error("too many HTML attributes")
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
        raw = self.get_starttag_text()
        for key, value in attrs:
            match = ATTRIBUTE.match(raw, cursor)
            attr_line = line
            if match:
                attr_line += raw.count("\n", cursor, match.start(1))
                line = attr_line + raw.count("\n", match.start(1), match.end())
                cursor = match.end()
            value = value or ""
            if "{{" in value and (key, value) not in {("lang", "{{lang}}"), ("dir", "{{dir}}"), ("data-fit", "{{fit}}")}:
                self.error(f"unsupported substitution in {key}", attr_line)
            if (tag, key) in {("img", "src"), ("link", "href")}:
                value = self.loader.asset(value, self.source, attr_line, IMAGE if tag == "img" else {".css"})
            elif key == "style":
                value = self.loader.css(value, self.source, attr_line)
            elif key not in ATTRS and (tag, key) not in {("link", "rel"), ("meta", "charset")}:
                self.error(f"disallowed attribute {key}", attr_line)
            if value in ("{{lang}}", "{{dir}}", "{{fit}}"):
                output.extend([f' {key}="', Placeholder(value[2:-2]), '"'])
            else:
                output.append(f' {key}="{html.escape(value)}"')
        self.output.extend(["<" + tag, *output, ">"])
        if tag not in {"meta", "link", "img", "br"}:
            self.stack.append((tag, fields.get("data-check") == "text" or bool(self.stack and self.stack[-1][1])))

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
        cursor = 0
        def literal(chunk):
            if "{{" in chunk or "}}" in chunk:
                self.error("incomplete placeholder in text", line)
            self.output.append(html.escape(chunk, quote=False))

        for match in PLACEHOLDER.finditer(data):
            chunk = data[cursor:match.start()]
            literal(chunk)
            line += chunk.count("\n")
            key = match[1]
            if key not in VALUES:
                self.error(f"unknown template value {key}", line)
            if key in {"caption", "detail", "headline"} and not (self.stack and self.stack[-1][1]):
                self.error(f'{key} requires data-check="text"', line)
            self.output.append(Placeholder(key))
            cursor = match.end()
        literal(data[cursor:])


def resolve(root, selection, deadline=None, byte_limit=MAX_PLAN_TEMPLATE_BYTES):
    """Return the checked template, or None for a bundled name."""
    if selection in template_values.TEMPLATES:
        return None
    if not isinstance(selection, str) or not selection.startswith("user:"):
        message = f"unknown template {selection!r} (bundled templates: {', '.join(template_values.TEMPLATES)})"
        if isinstance(selection, str) and NAME.fullmatch(selection):
            try:
                with directory(root, FOLDER) as fd:
                    mode = os.stat(selection + ".html", dir_fd=fd, follow_symlinks=False).st_mode
                    if stat.S_ISREG(mode):
                        message += f"; select user:{selection} to use the app template"
            except OSError:
                pass
        raise ValueError(message)
    name = selection[5:]
    deadline = new_deadline() if deadline is None else deadline
    with loading(deadline):
        return _load(root, name, selection, deadline, byte_limit)


def _load(root, name, selection, deadline, byte_limit):
    if not NAME.fullmatch(name):
        raise ValueError(f"invalid template name {selection!r} (expected [a-z0-9-]+)")
    source = name + ".html"
    loader = Loader(root, deadline, byte_limit)
    try:
        data = loader.read(root, FOLDER + "/" + source)
    except FileNotFoundError as exc:
        raise ValueError(f"unknown template {selection!r}: missing {FOLDER}/{source}") from exc
    except (OSError, ValueError) as exc:
        raise ValueError(f"{FOLDER}/{source}:1: {exc}") from exc
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
    # Keep only substitutions and the literal HTML between them in the plan cache.
    tokens = []
    for kind, parts in groupby(markup.output, type):
        if kind is str:
            tokens.append("".join(parts))
        else:
            tokens.extend(parts)
    return Template(tokens, loader.assets, loader.digests, loader.virtual, loader.total)


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
                stream.write(starter.replace(b"user:TEMPLATE_NAME", ("user:" + args.name).encode("ascii")))
        print(f"{FOLDER}/{name}")
    except (ValueError, OSError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
