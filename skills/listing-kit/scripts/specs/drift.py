#!/usr/bin/env python3
"""Compare facts from upstream store pages and fastlane source with reviewed digests."""
import argparse
from html.parser import HTMLParser
from http.client import HTTPException
import json
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile
from urllib import request
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import specs

DIGESTS = Path(specs.BUNDLED).parent / "digests"
SIZE = re.compile(r"(?<!\d)(\d{3,5})\s*[×x]\s*(\d{3,5})(?!\d)", re.I)
MONTH = (r"(?:January|February|March|April|May|June|July|August|September|October|"
         r"November|December)")
DATE = re.compile(r"\b(?:" + MONTH + r" (?:\d{1,2},? )?\d{4}|\d{4}-\d{2}-\d{2})\b", re.I)
NUMBER = r"\d+(?:,\d{3})*"
LIMIT = re.compile(r"\b(?:up to " + NUMBER + r"(?: (?:characters?|bytes?))?|"
                   + NUMBER + r" (?:characters?|bytes?))\b", re.I)
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


class Page(HTMLParser):
    """Emit visible text blocks, retaining heading, table and item boundaries."""

    blocks = HEADINGS | set("article section li ul ol div p dt dd table tr td th caption time br".split())

    def __init__(self):
        super().__init__()
        self.events = []
        self.stack = []
        self.text = []
        self.hidden = []
        self.first_cell = False

    def flush(self):
        value = " ".join("".join(self.text).split())
        if value:
            role = next((role for _, role in reversed(self.stack) if role), "text")
            self.events.append((role, value))
        self.text.clear()

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "template", "head", "noscript"):
            self.hidden.append(tag)
        if self.hidden or tag not in self.blocks:
            return
        if tag == "br":
            self.text.append(" ")
            return
        self.flush()
        role = None
        if tag in HEADINGS:
            role = "heading"
        elif tag in ("article", "li"):
            self.events.append(("start", ""))
        elif tag == "tr":
            self.first_cell = True
            self.events.append(("row", ""))
        elif tag in ("td", "th", "dt", "caption"):
            if tag != "td" or self.first_cell:
                role = "label"
            self.first_cell = False
        self.stack.append((tag, role))

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        if tag == "br" or tag not in self.blocks:
            return
        self.flush()
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if tag in ("article", "li"):
            self.events.append(("end", ""))
        elif tag in ("tr", "table", "dd"):
            self.events.append(("row", ""))

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


def pixel_sizes(events):
    for _, text in events:
        for w, h in SIZE.findall(text):
            yield w + "x" + h
        yield from DATE.findall(text)


def limits(events):
    heading = label = ""
    for role, text in events:
        if role == "row":
            label = ""
        matches = list(LIMIT.finditer(text))
        for match in matches:
            # A limit in the label itself can have its field name in the same cell.
            prefix = text[:match.start()].strip(" :(-") if role in ("label", "heading") else ""
            context = prefix or label or heading
            phrase = match.group().lower().replace(",", "")
            yield context + ": " + phrase if context else phrase
        if role == "heading":
            heading, label = text, ""
        elif role == "label" and not matches:
            label = text


def dated_items(blocks, in_item):
    # A plain list item can put its title and date in one sentence or adjacent
    # blocks. Prefer explicit headings when available (including on flat pages).
    if in_item and not any(role == "heading" for role, _ in blocks):
        text = " ".join(value for _, value in blocks)
        match = DATE.search(text)
        if match:
            title = (text[:match.start()].strip(" ()–—-:,") or
                     text[match.end():].strip(" ()–—-:,"))
            if title:
                yield title + ": " + match.group()
        return

    title = date = ""
    for role, text in blocks:
        match = DATE.search(text)
        if role == "heading" and not DATE.fullmatch(text):
            title = DATE.sub("", text).strip(" ()–—-:,")
        if match:
            date = match.group()
        if title and date:
            yield title + ": " + date
            title = date = ""


def dated_list(events):
    blocks = []
    depth = 0
    for role, text in events:
        if role in ("start", "end"):
            yield from dated_items(blocks, depth > 0)
            blocks.clear()
            depth += 1 if role == "start" else -1
        else:
            blocks.append((role, text))
    yield from dated_items(blocks, depth > 0)


# Match literal Ruby data only. Each pattern stops at the end of its array.
PAIR = r"\[\s*\d+\s*,\s*\d+\s*\]"
SIZES = r"(?P<sizes>\[\s*(?:" + PAIR + r"\s*,?\s*)+\]|" + PAIR + ")"
DISPLAY = r"""(?P<display>(?:\w+::)*[A-Z]\w*|['"][^'"\n]+['"]|:\w+)"""
DISPLAY_ROWS = [re.compile(DISPLAY + r"\s*=>\s*" + SIZES),
                re.compile(SIZES + r"\s*=>\s*" + DISPLAY)]
LIST_NAMES = {
    "languages.rb": ("ALL_LANGUAGES",),
    "supply.rb": ("METADATA_UPLOAD_FIELDS", "METADATA_FIELDS", "IMAGES_TYPES",
                       "IMAGE_TYPES", "SCREENSHOT_TYPES"),
}
LIST = re.compile(r"^\s*(\w+)\s*=\s*(%[wi])?(?:\[([^\]]*)\]|\(([^)]*)\)|\{([^}]*)\})",
                  re.M)
ITEM = re.compile(r"""(?:'([\w-]+)'|"([\w-]+)"|:([\w-]+))""")


def ruby_constants(filename, text):
    text = re.sub(r"#[^\n]*", "", text)
    if filename == "app_screenshot.rb":
        for pattern in DISPLAY_ROWS:
            for match in pattern.finditer(text):
                display = match["display"].split("::")[-1].strip(":'\"")
                for pair in re.findall(PAIR, match["sizes"]):
                    w, h = re.findall(r"\d+", pair)
                    yield "{}: {}x{}".format(display, w, h)
        return

    if filename not in LIST_NAMES:
        raise ValueError("unknown fastlane source file: " + filename)
    for constant, words, square, paren, brace in LIST.findall(text):
        if constant not in LIST_NAMES[filename]:
            continue
        body = square or paren or brace
        if words:
            items = body.split()
            if not all(re.fullmatch(r"[\w-]+", item) for item in items):
                raise ValueError("unsupported Ruby literal in " + constant)
        else:
            items = []
            for token in body.strip().rstrip(",").split(","):
                if not token.strip():
                    continue
                match = ITEM.fullmatch(token.strip())
                if not match:
                    raise ValueError("unsupported Ruby literal in " + constant)
                items.append(next(item for item in match.groups() if item))
        for item in items:
            yield constant + ": " + item


def extract(source, text):
    extractor = source["extract"]
    if extractor == "ruby-constants":
        facts = ruby_constants(Path(urlsplit(source["url"]).path).name, text)
    else:
        page = Page()
        try:
            page.feed(text)
            page.close()
        except AssertionError as exc:
            # Some Python versions reject malformed HTML marked sections here.
            raise ValueError("invalid HTML: " + str(exc)) from exc
        page.flush()
        facts = {"pixel-sizes": pixel_sizes, "limits": limits, "dated-list": dated_list}[extractor](page.events)
    result = sorted(set(facts))
    if not result:
        raise ValueError("zero facts extracted")
    return result


# Explicit redirect scopes for this manifest avoid guessing public suffixes.
# Keep GitHub's multi-tenant raw content service pinned to its own host.
REDIRECT_SCOPE = {"developer.apple.com": "apple.com", "support.google.com": "google.com",
                  "raw.githubusercontent.com": "raw.githubusercontent.com"}


def validate_url(url, domain):
    target = urlsplit(url)
    host = target.hostname or ""
    if (target.scheme != "https" or target.username is not None or
            not (host == domain or host.endswith("." + domain))):
        raise ValueError("URL outside the allowed HTTPS source domain")


class SameDomainRedirect(request.HTTPRedirectHandler):
    def __init__(self, domain):
        self.domain = domain

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl, self.domain)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    host = urlsplit(url).hostname
    domain = REDIRECT_SCOPE.get(host)
    if not domain:
        raise ValueError("no redirect scope configured for source host")
    validate_url(url, domain)
    opener = request.build_opener(request.ProxyHandler({}), SameDomainRedirect(domain))
    req = request.Request(url, headers={"User-Agent": "listing-kit-drift-watch"})
    with opener.open(req, timeout=30) as response:
        return response.read().decode("utf-8-sig")


def baseline(path):
    if not path.exists():
        raise ValueError("missing baseline (seed with drift.py update --fetch)")
    facts = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(facts, list) or not facts or not all(isinstance(f, str) and f for f in facts):
        raise ValueError("invalid baseline: expected a nonempty list of facts")
    return set(facts)


def formatted(facts):
    return json.dumps(facts, ensure_ascii=False, indent=2) + "\n"


def write_digest(path, facts):
    path.parent.mkdir(parents=True, exist_ok=True)
    out = NamedTemporaryFile(dir=path.parent, delete=False, mode="w", encoding="utf-8")
    tmp = Path(out.name)
    try:
        with out:
            out.write(formatted(facts))
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def compare_or_update(args, sources):
    fresh = {}
    status = 0
    for source in sources:
        name = source["id"]
        try:
            if args.fetch:
                text = fetch(source["url"])
            else:
                suffix = ".rb" if source["kind"] == "source" else ".html"
                text = (args.pages / (name + suffix)).read_text(encoding="utf-8-sig")
            fresh[name] = extract(source, text)
            if args.command == "check":
                old = baseline(args.digests / (name + ".json"))
                new = set(fresh[name])
                if old == new:
                    print(name + ": unchanged")
                else:
                    status = max(status, 1)
                    print(name + ": changed")
                    for fact in sorted(old - new):
                        print("  - " + fact)
                    for fact in sorted(new - old):
                        print("  + " + fact)
        except (OSError, HTTPException, ValueError) as exc:
            print("{}: problem: {}".format(name, exc))
            status = 2

    if args.command == "update" and status == 0:
        for name, facts in fresh.items():
            try:
                write_digest(args.digests / (name + ".json"), facts)
                print(name + ": updated")
            except OSError as exc:
                print("{}: problem: {}".format(name, exc))
                return 2
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    single = commands.add_parser("extract")
    single.add_argument("id")
    single.add_argument("file", type=Path)
    for command in ("check", "update"):
        sub = commands.add_parser(command)
        mode = sub.add_mutually_exclusive_group(required=True)
        mode.add_argument("--fetch", action="store_true")
        mode.add_argument("--pages", type=Path)
        sub.add_argument("--digests", type=Path, default=DIGESTS)
    args = parser.parse_args()
    sources = specs.load().get("watch")
    if not sources:
        parser.error("no watched sources in bundled store rules")
    if args.command == "extract":
        source = next((s for s in sources if s["id"] == args.id), None)
        if not source:
            parser.error("unknown watch id: " + args.id)
        try:
            print(formatted(extract(source, args.file.read_text(encoding="utf-8-sig"))), end="")
        except (OSError, ValueError) as exc:
            print("{}: problem: {}".format(args.id, exc), file=sys.stderr)
            return 2
        return 0
    return compare_or_update(args, sources)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except specs.SpecsError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
