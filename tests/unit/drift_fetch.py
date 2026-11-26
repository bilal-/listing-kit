"""Exercise urllib policy without opening a socket."""
import io
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills/listing-kit/scripts/specs"))
import drift


class FetchTest(unittest.TestCase):
    url = "https://developer.apple.com/news/upcoming-requirements/"

    def test_fetch(self):
        with patch("urllib.request.build_opener") as build:
            build.return_value.open.return_value = io.BytesIO(b"<p>saved</p>")
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


if __name__ == "__main__":
    unittest.main()
