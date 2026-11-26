"""Exercise urllib policy without opening a socket."""
from contextlib import redirect_stdout
from email.message import Message
import io
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills/listing-kit/scripts/specs"))
import drift


class Response(io.BytesIO):
    def __init__(self, body, length=None):
        super().__init__(body)
        self.headers = Message()
        if length is not None:
            self.headers["Content-Length"] = length


class FetchTest(unittest.TestCase):
    url = "https://developer.apple.com/news/upcoming-requirements/"

    def test_fetch(self):
        with patch("urllib.request.build_opener") as build:
            build.return_value.open.return_value = Response(b"<p>saved</p>")
            self.assertEqual(drift.fetch(self.url), "<p>saved</p>")
            request, = build.return_value.open.call_args[0]
            self.assertEqual(request.full_url, self.url)
            self.assertEqual(request.header_items(), [("User-agent", "listing-kit-drift-watch")])
            self.assertEqual(build.return_value.open.call_args[1], {"timeout": 30})
            handlers = build.call_args[0]
            self.assertTrue(any(isinstance(h, urllib.request.ProxyHandler) and not h.proxies for h in handlers))
            redirect = next(h for h in handlers if isinstance(h, urllib.request.HTTPRedirectHandler))
            def follow(target):
                return redirect.redirect_request(request, None, 302, "Found", {}, target)
            self.assertEqual(follow("https://www.apple.com/new").full_url, "https://www.apple.com/new")
            for target in ("https://apple.com.evil.example/", "https://badapple.com/",
                           "http://developer.apple.com/", "https://user:pass@www.apple.com/"):
                with self.subTest(target=target), self.assertRaises((ValueError, urllib.error.URLError)):
                    follow(target)


    def test_bounded_reads(self):
        class Chunked(Response):
            def read(self, size=-1):
                if not 0 < size <= 65536:
                    raise AssertionError("expected a bounded chunk, got {}".format(size))
                return super().read(size)

        limit = 5 * 1024 * 1024
        with patch("urllib.request.build_opener") as build:
            opener = build.return_value.open
            opener.return_value = Chunked(b"a" * limit, str(limit))
            self.assertEqual(len(drift.fetch(self.url)), limit)
            for length in (None, "10"):
                with self.subTest(length=length), self.assertRaises(ValueError):
                    opener.return_value = Chunked(b"a" * (limit + 1), length)
                    drift.fetch(self.url)

    def test_bad_length_is_a_per_source_problem(self):
        def source(name):
            return dict(id=name, url=self.url, extract="pixel-sizes", kind="html")

        args = SimpleNamespace(command="check", fetch=True, digests=Path("."))
        body = b"<h2>Icon</h2><p>512x512</p>"
        class BadHeader(Response):
            def read(self, size=-1):
                raise AssertionError("invalid Content-Length must fail before reading")

        for length in ("-1", "12oops", str(sys.maxsize + 1), str(5 * 1024 * 1024 + 1)):
            log = io.StringIO()
            with self.subTest(length=length), patch("urllib.request.build_opener") as build, \
                    patch.object(drift, "baseline", return_value={"Icon :: 512x512"}), redirect_stdout(log):
                build.return_value.open.side_effect = [BadHeader(body, length), Response(body)]
                self.assertEqual(drift.compare_or_update(args, [source("bad"), source("next")]), 2)
                self.assertIn("bad: problem", log.getvalue())
                self.assertIn("next: unchanged", log.getvalue())


if __name__ == "__main__":
    unittest.main()
