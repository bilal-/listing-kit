"""Regression cases for the composer. All mutable inputs live in suite fixtures."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/listing-kit/scripts/compose"))
import compose
import cdp
import render


def png(w=2, h=2):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(h * (w * 3 + 1)))) + chunk(b"IEND", b""))


class Composer(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.kit = self.root / ".listing-kit"
        self.kit.mkdir()
        self.out = self.root / "shots/a.png"
        self.out.parent.mkdir()
        self.raw = self.root / "raw.png"
        self.raw.write_bytes(png())
        self.rec = dict(kind="screenshot", size=[2, 2], outputPath="shots/a.png",
                        rawPath="raw.png", styleMode="raw", targetId="a", screenId="a")
        self.man = dict(outputs=[self.rec], stale=[])
        for fn, result in [(compose.plan.load, {}), (compose.specs.load, {}),
                           (compose.plan.manifest, self.man)]:
            p = patch(fn.__module__ + "." + fn.__name__, return_value=result)
            p.start()
            self.addCleanup(p.stop)

    def run_cli(self, *args):
        log = io.StringIO()
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            code = compose.main([str(self.root), *args])
        self.log = log.getvalue()
        return code

    def job(self):
        return compose.Job(str(self.root), self.rec, {})

    @unittest.skipUnless(compose.magick(), "ImageMagick required")
    def test_01_unowned_and_edited_require_listed_adoption(self):
        for contents in [b"original", b"later edit"]:
            self.out.write_bytes(contents)
            self.assertEqual(self.run_cli(), 1)
            self.assertIn("exists and was not written by listing-kit (or was edited); move it away or rerun with --adopt", self.log)
            self.assertEqual(self.out.read_bytes(), contents)
            self.assertEqual(self.run_cli("--adopt"), 0, self.log)
            self.assertLess(self.log.index("shots/a.png"), self.log.index("wrote "))

    def stale(self):
        with patch.object(compose, "build", return_value=png()), patch.object(compose, "magick", return_value=["magick"]):
            self.assertEqual(self.run_cli(), 0)
        self.man.update(outputs=[], stale=["shots/a.png"])

    def test_02_stale_edits_stay_put(self):
        self.stale()
        self.out.write_bytes(b"hand edit")
        self.run_cli()
        self.assertEqual(self.out.read_bytes(), b"hand edit")

    def test_02_stale_archive_collision(self):
        self.stale()
        held = self.kit / "held/shots/a.png"
        held.parent.mkdir(parents=True)
        held.write_bytes(b"previous")
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual(held.read_bytes(), b"previous")
        self.assertEqual(len(list(held.parent.iterdir())), 2)
        self.assertFalse(self.out.exists())

    def test_02_stale_archive_symlink(self):
        self.stale()
        elsewhere = self.root / "other"
        elsewhere.mkdir()
        (self.kit / "held").symlink_to(elsewhere)
        self.assertNotEqual(self.run_cli(), 0)
        self.assertTrue(self.out.exists())
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_03_checkpoint_and_merge_on_partial_run(self):
        self.man["outputs"].append(dict(self.rec, outputPath="shots/b.png"))
        (self.kit / "outputs.json").write_text('{"format":1,"files":["legacy.png"]}')
        with patch.object(compose, "build", side_effect=[png(), KeyboardInterrupt]), patch.object(compose, "magick", return_value=True):
            with self.assertRaises(KeyboardInterrupt):
                self.run_cli()
        self.assertEqual(json.loads((self.kit / "compose.lock.json").read_text())["outputs"]["shots/a.png"]["sha256"],
                         hashlib.sha256(self.out.read_bytes()).hexdigest())
        self.assertEqual(set(json.loads((self.kit / "outputs.json").read_text())["files"]), {"legacy.png", "shots/a.png"})

    def test_03_concurrent_writer_fails_promptly(self):
        def other_writer(*unused):
            start = time.monotonic()
            with patch.object(compose, "build", return_value=b"other"):
                self.assertNotEqual(self.run_cli(), 0)
            self.assertLess(time.monotonic() - start, 1)
            return png()
        with patch.object(compose, "build", side_effect=other_writer), patch.object(compose, "magick", return_value=True):
            self.assertEqual(self.run_cli(), 0)

    def test_04_template_registry_before_open(self):
        for fn in [compose.template_hash, lambda name: render._fill(name, {})]:
            with patch("builtins.open", side_effect=AssertionError("opened an unknown template")):
                with self.assertRaisesRegex(ValueError, "template"):
                    fn("/unknown")

    def test_06_css_values(self):
        palette = dict(background=["#ffffff"], ink="#112233")
        for key, value in [("color", "red"), ("shadow", "x}body{color:red"), ("width", True),
                           ("radius", -1), ("width", float("nan")), ("radius", "5")]:
            with self.subTest(key=key), self.assertRaises(render.RenderError):
                render._vars(dict(palette=palette, bezel={key: value}))
        render._vars(dict(palette=dict(palette, ink="#11223380")))

    @unittest.skipUnless(compose.magick(), "ImageMagick required")
    def test_08_raw_snapshot_always_normalized(self):
        job = self.job()
        with patch.object(compose, "flatten_rgb", wraps=compose.flatten_rgb) as flatten:
            job.keys()
            self.raw.write_bytes(png(3, 2))
            self.assertIsNotNone(compose.build(job, None), job.problems)
            flatten.assert_called_once_with(png())

    def test_09_raw_key_uses_only_build_inputs(self):
        before = self.job().keys()
        self.rec.update(text={"caption": {"value": "new copy"}}, style={"palette": {"ink": "#ffffff"}})
        self.assertEqual(self.job().keys(), before)

    def test_14_timeout_validated_before_spawning(self):
        with patch.dict(os.environ, LK_BROWSER_TIMEOUT="bad"), patch("subprocess.Popen", side_effect=AssertionError("spawned")):
            with self.assertRaisesRegex(cdp.BrowserError, "LK_BROWSER_TIMEOUT"):
                cdp.Browser("/bin/false")

    def test_15_malformed_lock(self):
        for bad in ["{", "[]", '{"format":1,"outputs":{"x":{}}}']:
            (self.kit / "compose.lock.json").write_text(bad)
            self.assertNotEqual(self.run_cli("--dry-run"), 0)
            self.assertIn("compose.lock.json", self.log)

    def test_16_fixture_helpers_preserve_suite_cleanup(self):
        for filename in ["compose.test.sh", "fontcheck.test.sh"]:
            script = Path(__file__).with_name(filename).read_text()
            self.assertIn("new_tempdir T", script)
            self.assertIn('remove_fixture "$T"', script)
            self.assertNotIn("trap 'rm -rf", script)


class ChildTargets(unittest.TestCase):
    def test_05_pause_until_acknowledged(self):
        class Pipe(cdp.Browser):
            def __init__(self):
                self._id = 0
                self.queue = []
                self.calls = []
                self.deadline = time.monotonic() + 2
                self.timeout = 2
            def send(self, method, params=None, session=None):
                self.calls.append((method, session, params))
                self._id += 1
                reply = {"id": self._id, "sessionId": session, "result": {}}
                if method == "Target.createTarget":
                    reply["result"]["targetId"] = "top"
                if method == "Target.attachToTarget":
                    reply["result"]["sessionId"] = "parent"
                if method == "Page.navigate":
                    self.queue.append(dict(method="Target.attachedToTarget", sessionId="parent",
                                           params=dict(sessionId="child", targetInfo={"targetId": "worker"})))
                if session == "child" and method == "Fetch.enable":
                    reply["error"] = {"message": "interception rejected"}
                self.queue.append(reply)
                return self._id
            def _read(self):
                return self.queue.pop(0)
        pipe = Pipe()
        with self.assertRaisesRegex(cdp.BrowserError, "interception rejected"):
            cdp.Renderer(pipe).render({}, 1, 1)
        self.assertFalse(any(m == "Runtime.runIfWaitingForDebugger" for m, _, _ in pipe.calls))
        self.assertTrue(any(m == "Target.closeTarget" and p["targetId"] == "worker" for m, _, p in pipe.calls))


@unittest.skipUnless(cdp.find_browser(), "local Chromium-family browser required")
class Layout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.browser, cls.renderer = render.open_browser()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()

    def draw(self, template, palette, text, **kw):
        font = str(next((ROOT / "skills/listing-kit").rglob("*.ttf")))
        return render.render(self.renderer, template, kw.pop("size", (600, 300)), "en-US",
                             {"palette": palette}, dict(headline=[font], detail=[font]), text, **kw)[1]

    def test_07_required_asset_decode(self):
        with tempfile.TemporaryDirectory() as d:
            logo = Path(d) / "broken.png"
            logo.write_bytes(b"broken")
            with self.assertRaisesRegex(cdp.BrowserError, "broken.png|logo.png"):
                self.draw("feature", dict(background=["#ffffff"], ink="#000000"), {}, logo=str(logo))

    def test_10_gradient_under_text(self):
        report = self.draw("feature", dict(background=["#000000", "#ffffff"], ink="#757575"), {"headline": "Middle"})
        self.assertLess(report["worstContrast"], 1.5)

    def test_10_landscape_phone_scale(self):
        report = self.draw("feature", dict(background=["#ffffff"], ink="#808080"), {"headline": "Small"}, size=(2400, 400))
        self.assertIn("needs 4.5:1", str(report["problems"]))

    def test_11_panel_row_contrast(self):
        report = self.draw("panel", dict(background=["#ffffff"], ink="#000000", detail="#ffffff"),
                           {"headline": "Panel", "rows": [("Label", "Value")]})
        self.assertLess(report["worstContrast"], 1.01)

    def test_12_wide_capture_contained(self):
        report = self.draw("caption-top", dict(background=["#ffffff"], ink="#000000"), {"caption": "Wide"},
                           raw=png(40, 10), shot_size=(40, 10), size=(200, 400))
        self.assertEqual(report["device"]["objectFit"], "contain")
        self.assertEqual(report["device"]["crop"], 0)


if __name__ == "__main__":
    unittest.main()
