#!/usr/bin/env python3
"""Compare facts from upstream store pages and fastlane source with reviewed digests."""
import argparse
from html.parser import HTMLParser
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile
import unicodedata
from urllib import request
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import json_input
import specs

DIGESTS = Path(specs.BUNDLED).parent / "digests"
NUMBER = r"[0-9]+(?:,[0-9]{3})*"
PX = r"(?:px|pixels?)"
SIZE = re.compile(rf"(?<!\d)({NUMBER})\s*(?:{PX}\s*)?(?:×|x|by)\s*({NUMBER})(?:\s*{PX})?\b", re.I)
QUALIFIER = r"(?:minimum(?: of)?|maximum(?: of)?|at least|at most|up to|no more than|no less than)"
RANGE = r"(?:and|to|[-–—])"
SIDE = re.compile(rf"\b(?:(?:between |from )?{NUMBER}(?:\s*{PX})?\s*{RANGE}\s*{NUMBER}\s*{PX}"
                  rf"|(?:{QUALIFIER} )?{NUMBER}\s*{PX})\b", re.I)
RATIO = re.compile(rf"\b(?:{QUALIFIER} )?\d+(?:\.\d+)?(?:\s+times\b|\s*:\s*\d+(?:\.\d+)?\b)", re.I)
MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
         r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?")
DAY = r"\d{1,2}(?:st|nd|rd|th)?"
DATE = re.compile(r"\b(?:" + MONTH + r" (?:" + DAY + r",? )?\d{4}|"
                  + DAY + " " + MONTH + r" \d{4}|\d{4}-\d{2}-\d{2})\b", re.I)
UNIT = r"(?:characters?|bytes?)"
LIMIT = re.compile(rf"\b(?:(?:between |from )?{NUMBER}(?: {UNIT})?\s*{RANGE}\s*{NUMBER} {UNIT}"
                   rf"|{QUALIFIER} {NUMBER}(?: {UNIT})?|{NUMBER} {UNIT})\b", re.I)
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


class Page(HTMLParser):
    """Emit visible text blocks, retaining heading, table and item boundaries."""

    blocks = HEADINGS | set("article section li ul ol div p dt dd table tr td th caption br".split())

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
            self.events.append(("start", tag))
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


def pixel_matches(text):
    # A pair consumes both sides including units. Only scan gaps for other rules.
    end = 0
    for match in SIZE.finditer(text):
        yield from other_pixel_matches(text, end, match.start())
        yield match, "x".join(n.replace(",", "") for n in match.groups())
        end = match.end()
    yield from other_pixel_matches(text, end, len(text))


def other_pixel_matches(text, start, end):
    matches = (m for rule in (SIDE, RATIO, DATE) for m in rule.finditer(text, start, end))
    for match in sorted(matches, key=lambda m: m.start()):
        yield match, match.group()


def limit_matches(text):
    for match in LIMIT.finditer(text):
        yield match, match.group().lower().replace(",", "")


def labelled_facts(events, find_matches, inline_fields=False):
    heading = row = item = container = ""
    parents = []
    for role, text in events:
        if role == "start":
            parents.append((heading, row, item, container))
            container = text
            heading, item = item or heading, ""
        elif role == "end":
            if parents:
                heading, row, item, container = parents.pop()
        elif role == "row":
            row = ""
        else:
            end = 0
            inline = ""
            for match, value in find_matches(text):
                prefix = text[end:match.start()].strip(" ;,")
                # A colon followed by space introduces a field, including in
                # ordinary prose. A ratio's colon stays inside the match.
                field = re.search(r"(?:^|[;.])\s*([^:;]+?)\s*:(?:\s|$)", prefix)
                if field:
                    inline = field[1].strip()
                elif end == 0 and (inline_fields or role in ("label", "heading") or
                                   (container == "li" and not item)):
                    inline = prefix.strip(" ():–—-")
                context = inline or row or item or heading or "Page"
                if inline and row and role != "label":
                    context = row + " / " + inline
                elif inline_fields and inline and not field and heading and role == "text":
                    context = heading + " / " + inline
                yield context + " :: " + value
                end = match.end()
            if role == "heading":
                heading, row, item = inline or text, "", ""
            elif role == "label":
                row = inline if end else text
            elif container == "li" and (inline or not end and not item):
                item = inline or text


def pixel_sizes(events):
    return labelled_facts(events, pixel_matches)


def limits(events):
    return labelled_facts(events, limit_matches, inline_fields=True)


def dated_items(blocks):
    # The first heading can follow its date. Subsequent headings start new entries.
    heading = ""
    body = []
    for role, text in blocks:
        if role == "heading" and not DATE.fullmatch(text):
            if heading:
                yield from dated_entry(heading, body)
                body = []
            heading = DATE.sub("", text).strip(" ()–—-:,")
            if not DATE.search(text):
                continue
        if text:
            body.append(text)
    yield from dated_entry(heading, body)


def dated_entry(title, body):
    if not body:
        return
    if not title:
        first = body[0]
        match = DATE.search(first)
        title = (first[:match.start()] or first[match.end():]) if match else first
        title = title.strip(" ()–—-:,")
    surrounding = []
    for index, text in enumerate(body):
        dates = list(DATE.finditer(text))
        if not dates:
            if text != title:
                surrounding.append(text)
            continue
        after = body[index + 1:index + 2]
        if after and (after[0] == title or DATE.search(after[0])):
            after = []
        context = " ".join(surrounding + [text] + after)
        for match in dates:
            fact = (title or "Page") + " :: " + match.group()
            rest = context.replace(match.group(), "", 1).strip(" ()–—-:,")
            if rest and rest != title:
                fact += " :: " + (context if text != match.group() else " ".join(surrounding + after))
            yield fact
        surrounding = []


def dated_list(events):
    blocks = []
    for role, text in events:
        if role in ("start", "end"):
            yield from dated_items(blocks)
            blocks.clear()
        else:
            blocks.append((role, text))
    yield from dated_items(blocks)


# Read only literal data from fastlane. A recognized declaration must be
# consumed completely, including its final delimiter, before it becomes a fact.
PAIR = r"\[\s*(\d+)\s*,\s*(\d+)\s*\]"
PAIR_ARRAY = r"\[\s*(?:" + PAIR + r"\s*,\s*)*" + PAIR + r"\s*,?\s*\]"
SIZES = re.compile(PAIR_ARRAY + "|" + PAIR)
DISPLAY = r"""(?:\b(?:\w+::)*[A-Z]\w*|['"][^'"\n]+['"]|:\w+)"""
FORWARD = re.compile(r"(?P<display>" + DISPLAY + r")\s*(?P<operator>=>|=(?!=)|:(?!:))\s*")
REVERSE_NAME = re.compile(r"=>\s*(?P<display>" + DISPLAY + r")")
REVERSE = re.compile(r"(?P<sizes>" + SIZES.pattern + r")\s*" + REVERSE_NAME.pattern)
ROW_END = re.compile(r"(?:\.freeze)?[ \t]*(?=[,}\n]|$)")
DEVICE = re.compile(r"(?:IOS|IPAD|IPHONE|APPLE_TV|IMESSAGE|WATCH|VISION)(?:_|$)", re.I)
LIST_NAMES = {
    "languages.rb": ("ALL_LANGUAGES",),
    "supply.rb": ("METADATA_UPLOAD_FIELDS", "METADATA_FIELDS", "IMAGES_TYPES",
                  "IMAGE_TYPES", "SCREENSHOT_TYPES"),
}
ASSIGNMENT = re.compile(r"^[ \t]*([A-Z][A-Z_0-9]*)[ \t]*=(?!=)\s*", re.M)
SPACE = re.compile(r"(?:\s+|\#[^\n]*)*")
LIST_ITEM = re.compile(r"""'([^'\\]*)'|"([^"\\]*)"|:([\w-]+)""")
LIST_END = re.compile(r"(?:\.freeze)?[ \t]*(?:\#[^\n]*)?(?=\n|$)")


def display_fact(name, literal):
    pairs = ["[{},{}]".format(w, h) for w, h in re.findall(PAIR, literal)]
    value = pairs[0] if re.fullmatch(PAIR, literal) else "[" + ",".join(pairs) + "]"
    return name.strip(":\'\"") + " :: " + value


def display_sizes(text):
    text = re.sub(r"#[^\n]*", "", text)
    for row in FORWARD.finditer(text):
        name = row["display"]
        start = row.end()
        if not text.startswith("[", start) and not DEVICE.match(name.split("::")[-1].strip(":\'\"")):
            continue
        sizes = SIZES.match(text, start)
        terminator = LIST_END if row["operator"] == "=" else ROW_END
        if not sizes or not terminator.match(text, sizes.end()):
            raise ValueError("unsupported Ruby size literal for " + name)
        yield display_fact(name, sizes.group())
    literal_names = set()
    for row in REVERSE.finditer(text):
        literal_names.add(row.start("display"))
        if not ROW_END.match(text, row.end()):
            raise ValueError("unsupported Ruby display literal")
        yield display_fact(row["display"], row["sizes"])
    for row in REVERSE_NAME.finditer(text):
        name = row["display"]
        if DEVICE.match(name.split("::")[-1]) and row.start("display") not in literal_names:
            raise ValueError("unsupported Ruby size literal for " + name)



def literal_list(text, pos):
    items = []
    if text.startswith(("%w", "%i"), pos):
        symbol = text[pos + 1] == "i"
        delimiter = text[pos + 2:pos + 3]
        if not delimiter or delimiter.isalnum() or delimiter.isspace():
            raise ValueError("invalid percent-literal delimiter")
        close = {"[": "]", "{": "}", "(": ")", "<": ">"}.get(delimiter, delimiter)
        end = text.index(close, pos + 3)
        for word in text[pos + 3:end].split():
            if not re.fullmatch(r"[\w-]+", word):
                raise ValueError("unsupported percent-literal word")
            items.append(":" + word if symbol else json.dumps(word, ensure_ascii=False))
        return items, end + 1
    if not text.startswith("[", pos):
        raise ValueError("expected a literal list")
    pos = SPACE.match(text, pos + 1).end()
    while not text.startswith("]", pos):
        match = LIST_ITEM.match(text, pos)
        if not match or (match[2] is not None and "#" in match[2]):
            raise ValueError("unsupported Ruby list element")
        if match[3] is not None:
            items.append(":" + match[3])
        else:
            word = match[1] if match[1] is not None else match[2]
            items.append(json.dumps(word, ensure_ascii=False))
        pos = SPACE.match(text, match.end()).end()
        if text.startswith("]", pos):
            break
        if not text.startswith(",", pos):
            raise ValueError("expected a comma between list elements")
        pos = SPACE.match(text, pos + 1).end()
    return items, pos + 1


def ruby_constants(filename, text):
    if filename == "app_screenshot.rb":
        yield from display_sizes(text)
        return
    if filename not in LIST_NAMES:
        raise ValueError("unknown fastlane source file: " + filename)
    for declaration in ASSIGNMENT.finditer(text):
        name = declaration[1]
        if name in LIST_NAMES[filename]:
            try:
                items, end = literal_list(text, declaration.end())
                if not LIST_END.match(text, end):
                    raise ValueError("unexpected text after list")
            except ValueError as exc:
                raise ValueError("{}: {}".format(name, exc)) from exc
            yield name + " :: [" + ",".join(items) + "]"


def clean_fact(fact):
    return "".join(c for c in fact if unicodedata.category(c) not in ("Cc", "Cf"))


def extract(source, text):
    extractor = source["extract"]
    if extractor == "ruby-constants":
        facts = ruby_constants(Path(urlsplit(source["url"]).path).name, text)
    else:
        page = Page()
        try:
            page.feed(text)
            page.close()
        except (AssertionError, NotImplementedError) as exc:
            # Python rejects malformed marked sections here: AssertionError on newer
            # versions, NotImplementedError from _markupbase on 3.8 and 3.9.
            raise ValueError("invalid HTML: " + str(exc)) from exc
        page.flush()
        facts = {"pixel-sizes": pixel_sizes, "limits": limits, "dated-list": dated_list}[extractor](page.events)
    result = sorted({clean_fact(fact) for fact in facts})
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


MAX_RESPONSE = 5 * 1024 * 1024


def response_body(response):
    lengths = response.headers.get_all("Content-Length", [])
    length = None
    if lengths:
        value = lengths[0].strip(" \t")
        if len(lengths) != 1 or not re.fullmatch(r"[0-9]+", value):
            raise ValueError("invalid Content-Length")
        digits = value.lstrip("0") or "0"
        if len(digits) > len(str(MAX_RESPONSE)) or int(digits) > MAX_RESPONSE:
            raise ValueError("Content-Length exceeds 5 MB")
        length = int(digits)
    body = bytearray()
    while True:
        chunk = response.read(min(65536, MAX_RESPONSE + 1 - len(body)))
        if not chunk:
            break
        body.extend(chunk)
        if len(body) > MAX_RESPONSE:
            raise ValueError("response exceeds 5 MB")
    if length is not None and len(body) != length:
        raise ValueError("response size differs from Content-Length")
    return body.decode("utf-8-sig")


def fetch(url):
    host = urlsplit(url).hostname
    domain = REDIRECT_SCOPE.get(host)
    if not domain:
        raise ValueError("no redirect scope configured for source host")
    validate_url(url, domain)
    opener = request.build_opener(request.ProxyHandler({}), SameDomainRedirect(domain))
    req = request.Request(url, headers={"User-Agent": "listing-kit-drift-watch"})
    with opener.open(req, timeout=30) as response:
        return response_body(response)


def baseline(path):
    if not path.exists():
        raise ValueError("missing baseline (seed with drift.py update --fetch)")
    with path.open(encoding="utf-8") as stream:
        facts = json_input.read(stream)
    if not isinstance(facts, list) or not facts or not all(isinstance(f, str) and f for f in facts):
        raise ValueError("invalid baseline: expected a nonempty list of facts")
    return {clean_fact(fact) for fact in facts}


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
            digest = args.digests / (name + ".json")
            if digest.is_symlink():
                raise ValueError("symlinked digest file")
            if args.fetch:
                text = fetch(source["url"])
            else:
                suffix = ".rb" if source["kind"] == "source" else ".html"
                text = (args.pages / (name + suffix)).read_text(encoding="utf-8-sig")
            fresh[name] = extract(source, text)
            if args.command == "check":
                old = baseline(digest)
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


def digest_directory(path):
    path = path.absolute()
    if ".." in path.parts:
        raise ValueError("parent traversal in digest directory")
    if path == DIGESTS:
        if path.parent.is_symlink() or path.is_symlink():
            raise ValueError("symlinked digest directory")
        return path
    root = os.environ.get("LK_DRIFT_TEST_ROOT")
    if root:
        root = Path(root).absolute()
        if root.is_dir() and root in path.parents:
            for parent in (path, *path.parents):
                if parent.is_symlink():
                    raise ValueError("symlinked digest directory")
                if parent == root:
                    return path
    raise ValueError("digest directory must be the bundled directory or inside LK_DRIFT_TEST_ROOT")


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
    try:
        args.digests = digest_directory(args.digests)
    except ValueError as exc:
        parser.error(str(exc))
    return compare_or_update(args, sources)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except specs.SpecsError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
