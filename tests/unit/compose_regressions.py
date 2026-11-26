"""Regression cases for the composer. All mutable inputs live in suite fixtures."""
import contextlib
import hashlib
import io
import inspect
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/listing-kit/scripts/compose"))
import compose
import ownership
import cdp
import render


def png(w=2, h=2):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(h * (w * 3 + 1)))) + chunk(b"IEND", b""))


class RendererVersion(unittest.TestCase):
    def test_source_mutations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            kit = Path("skills/listing-kit")
            for directory in ("scripts/compose", "scripts/lib", "templates", "specs"):
                shutil.copytree(ROOT / kit / directory, root / kit / directory,
                                ignore=shutil.ignore_patterns("__pycache__"))
            guard = Path("tests/unit/renderer_version.py")
            (root / guard.parent).mkdir(parents=True)
            shutil.copy(ROOT / guard, root / guard)
            (root / "tests/fixtures").mkdir()
            command = [sys.executable, "-B", str(guard)]
            subprocess.run(command + ["--record"], cwd=root, check=True)

            imginfo = compose.imginfo
            mutations = (
                (compose.report_failures, "print(", 'print("Error:", ', False),
                (compose.text_of, 'val("caption")', 'val("detail")', True),
                (compose.flatten_rgb, '"white"', '"black"', True),
                (compose.Job, "shot_size = (w, h)", "shot_size = (h, w)", True),
                (compose.build, "size=(w, h)", "size=(h, w)", True),
                (compose.verify_rgb, "return data", 'return b""', True),
                (imginfo._png_passes, "expected = h * stride", "expected = w * stride", True),
                (imginfo._png, "return w, h, depth", "return h, w, depth", True),
                (imginfo._inspect, "else _png(f)", "else UNKNOWN", True),
                (imginfo.image_info, "_inspect(path)[0]", "_inspect(path)[0][::-1]", True),
            )
            for obj, before, after, guarded in mutations:
                with self.subTest(symbol=obj.__name__):
                    path = Path(inspect.getfile(obj)).relative_to(ROOT)
                    target = root / path
                    original = target.read_text()
                    source = inspect.getsource(obj)
                    self.assertIn(before, source)
                    target.write_text(original.replace(source, source.replace(before, after, 1)))
                    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
                    target.write_text(original)
                    self.assertEqual(result.returncode, int(guarded), result.stderr)
                    if guarded:
                        self.assertIn(f"{path.relative_to(kit)}:{obj.__name__}", result.stderr)


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
        return compose.Job(str(self.root), self.rec)

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

    def test_01_file_created_during_build_is_preserved(self):
        def late_file(*unused):
            self.out.write_bytes(b"other writer")
            return png()
        with patch.object(compose, "build", side_effect=late_file), patch.object(compose, "magick", return_value=True):
            self.assertEqual(self.run_cli("--adopt"), 1)
        self.assertEqual(self.out.read_bytes(), b"other writer")
        self.assertIn(ownership.CONFLICT, self.log)

    def test_03_interruption_between_publication_and_checkpoint(self):
        with patch.object(compose, "build", return_value=png()), patch.object(compose, "magick", return_value=True):
            with patch.object(ownership.State, "save", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    self.run_cli()
            self.assertTrue(self.out.exists())
            self.assertEqual(self.run_cli(), 0, self.log)
            self.assertIn("1 unchanged", self.log)
        self.assertIn("shots/a.png", json.loads((self.kit / "outputs.json").read_text())["files"])

    def test_01_output_tree_can_resolve_inside_app(self):
        actual = self.root / "actual"
        self.out.parent.rename(actual)
        self.out.parent.symlink_to(actual)
        with patch.object(compose, "magick", return_value=True), patch.object(compose, "build", return_value=png()):
            self.assertEqual(self.run_cli(), 0, self.log)
        self.assertEqual(self.out.read_bytes(), png())

    def test_raw_only_never_checks_for_a_browser(self):
        with patch.object(cdp, "find_browser", side_effect=AssertionError("browser lookup")), \
             patch.object(compose, "magick", return_value=True), patch.object(compose, "build", return_value=png()):
            self.assertEqual(self.run_cli(), 0, self.log)
            self.assertEqual(self.run_cli(), 0, self.log)

    def test_missing_imagemagick_preserves_browser_diagnostics(self):
        self.man["outputs"].append(dict(self.rec, styleMode="framed", outputPath="shots/b.png"))
        with patch.dict(os.environ, PATH=str(self.root), LK_BROWSER=str(self.root / "missing")):
            self.assertEqual(self.run_cli(), 3, self.log)
        self.assertIn("shots/b.png: framed screenshots need Chrome, Chromium, Edge or Brave.", self.log)
        self.assertIn("ImageMagick is needed.", self.log)

    @unittest.skipUnless(compose.magick(), "ImageMagick required")
    def test_unusable_explicit_browser_preserves_raw_work(self):
        nonexec = self.root / "non-executable"
        nonexec.touch()
        bad_launch = self.root / "bad interpreter"
        bad_launch.write_text("#!/missing/listing-kit-interpreter\n")
        bad_launch.chmod(0o755)
        malformed = self.root / "invalid handshake"
        malformed.write_text("#!/bin/sh\nprintf 'invalid\\000' >&4\n")
        malformed.chmod(0o755)
        silent = self.root / "silent browser"
        silent.write_text('#!/bin/sh\necho $$ > "$PID_FILE"\nexec /bin/sleep 30\n')
        silent.chmod(0o755)
        pid_file = self.root / "pid"
        frames = [dict(self.rec, styleMode="framed", outputPath="shots/" + name)
                  for name in ("b.png", "c.png")]
        for i, path in enumerate([self.root / "missing", nonexec, "/usr/bin/true",
                                  "/usr/bin/false", bad_launch, malformed, silent]):
            with self.subTest(browser=str(path)), patch.dict(os.environ, LK_BROWSER=str(path),
                    LK_BROWSER_TIMEOUT="0.5", PID_FILE=str(pid_file)):
                raw = dict(self.rec, outputPath=f"shots/raw-{i}.png")
                for include_raw in (False, True):
                    self.man["outputs"] = frames + ([raw] if include_raw else [])
                    self.assertEqual(self.run_cli(), 1 if include_raw else 3, self.log)
                    for frame in frames:
                        prefix = f"compose: {frame['outputPath']}:"
                        reasons = [line for line in self.log.splitlines() if line.startswith(prefix)]
                        self.assertEqual(len(reasons), 1, self.log)
                        self.assertIn("LK_BROWSER", reasons[0])
                        self.assertIn(str(path), reasons[0])
                    if path == silent:
                        with self.assertRaises(ProcessLookupError):
                            os.kill(int(pid_file.read_text()), 0)
                self.assertTrue((self.root / raw["outputPath"]).is_file())
                for record, key in [("outputs.json", "files"), ("compose.lock.json", "outputs")]:
                    paths = json.loads((self.kit / record).read_text())[key]
                    self.assertIn(raw["outputPath"], paths)
                    for frame in frames:
                        self.assertNotIn(frame["outputPath"], paths)

    def test_browserless_adopt_leaves_conflicting_frame_alone(self):
        self.rec.update(styleMode="framed")
        self.out.write_bytes(b"keep")
        with patch.dict(os.environ, LK_BROWSER=str(self.root / "missing")):
            self.assertEqual(self.run_cli("--adopt"), 3, self.log)
        self.assertNotIn("adopting shots/a.png", self.log)
        self.assertEqual(self.out.read_bytes(), b"keep")

    def test_unsuccessful_preview_does_not_report_adoption(self):
        preview = self.kit / "preview.html"
        preview.write_text("keep")
        self.raw.unlink()
        self.assertEqual(self.run_cli("--preview", "--adopt"), 1, self.log)
        self.assertNotIn("adopting .listing-kit/preview.html", self.log)
        self.assertEqual(preview.read_text(), "keep")

    @unittest.skipUnless(compose.magick(), "ImageMagick required")
    def test_pre_branch_frame_stays_current_alongside_new_raw_capture(self):
        raw = dict(self.rec, outputPath="shots/new.png")
        self.man["outputs"].append(raw)
        font = str(ROOT / "skills/listing-kit/assets/fonts/Inter.ttf")
        self.rec.update(styleMode="framed", storeCode="en-US", style=dict(
            fonts=dict(headline=[font], detail=[font]), palette=dict(background=["#ffffff"], ink="#000000")))
        self.out.write_bytes(png())
        # Format-1 style digest from 809aac9 for this caption-top style.
        entry = dict(content=self.job().keys()[0], sha256=compose.sha_file(self.out),
                     style="d3c9c69ab92472dfc5a065ffb65fe6951076c3a0df9daba705e81a8a34a0b941",
                     size=[2, 2], renderer=dict(os=sys.platform, browser="100"), checks={})
        (self.kit / "compose.lock.json").write_text(json.dumps(dict(format=1, outputs={"shots/a.png": entry})))
        (self.kit / "outputs.json").write_text(json.dumps(dict(format=1, files=["shots/a.png"])))
        with patch.dict(os.environ, LK_BROWSER=str(self.root / "missing")):
            self.assertEqual(self.run_cli(), 0, self.log)
        self.assertIn("1 written, 1 unchanged", self.log)
        self.assertTrue((self.root / raw["outputPath"]).is_file())

    def test_closing_an_exited_browser_on_macos(self):
        browser = object.__new__(cdp.Browser)
        browser.proc = Mock(pid=42)
        with patch("os.killpg", side_effect=PermissionError):
            browser._stop()
        browser.proc.wait.assert_called_once_with(timeout=2)

    def test_browser_launch_flags_are_opt_in(self):
        browser = object.__new__(cdp.Browser)
        browser.path, browser.profile = "browser", str(self.root)
        with patch.dict(os.environ), patch("subprocess.Popen") as spawn:
            os.environ.pop("LK_BROWSER_ARGS", None)
            browser._spawn(3, 4, [])
            self.assertNotIn("--no-sandbox", spawn.call_args.args[0])
            os.environ["LK_BROWSER_ARGS"] = "--no-sandbox --disable-dev-shm-usage"
            browser._spawn(3, 4, [])
            self.assertIn("--no-sandbox", spawn.call_args.args[0])
            self.assertIn("--disable-dev-shm-usage", spawn.call_args.args[0])

    def test_09_mixed_browser_versions_only_emit_one_note(self):
        self.rec.update(styleMode="framed", storeCode="en-US")
        self.man["outputs"].append(dict(self.rec, targetId="b", outputPath="shots/b.png"))
        browser = Mock()
        browser.version_major.side_effect = ["100", "101", "101"]
        with patch.object(render, "open_browser", return_value=(browser, Mock())) as launch, \
             patch.object(cdp, "find_browser", return_value="browser"), \
             patch.object(compose, "build", return_value=png()), patch.object(compose, "magick", return_value=True):
            self.assertEqual(self.run_cli("--target", "a"), 0)
            self.assertEqual(self.run_cli(), 0)
            self.assertEqual(self.log.count("different browser versions"), 1)
            self.assertEqual(self.run_cli(), 0)
            self.assertIn("2 unchanged", self.log)
            self.assertEqual(launch.call_count, 2)
            self.assertEqual(self.run_cli("--restyle"), 0)
            self.assertIn("1 written, 1 unchanged", self.log)
            self.assertNotIn("different browser versions", self.log)

    def test_15_invalid_inventory_preserved(self):
        for invalid in ["[]", "{", '{"format":1,"files":{}}', '{"format":1,"files":["../bad"]}']:
            path = self.kit / "outputs.json"
            path.write_text(invalid)
            self.assertNotEqual(self.run_cli(), 0)
            self.assertIn("malformed .listing-kit/outputs.json", self.log)
            self.assertEqual(path.read_text(), invalid)

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
            self.assertEqual(flatten.call_count, 1)
            self.assertEqual(flatten.call_args[0][0], png())

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


@unittest.skipUnless(cdp.find_browser(), "no browser")
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

    def test_preview_frame_paints_inline_template(self):
        font = str(next((ROOT / "skills/listing-kit").rglob("*.ttf")))
        rec = dict(kind="graphic", size=[600, 300], outputPath="header.png", slotId="header-16x9",
                   style=dict(fonts=dict(headline=[font], detail=[font]), palette=dict(background=["#000000"], ink="#ffffff")),
                   text=dict(headline={"value": "Header"}))
        page = compose.preview_page([compose.Job(".", rec)])
        probe = """(()=>{const r=document.querySelector('iframe').getBoundingClientRect();
                   return [r.left+3,r.top+3,r.left+5,r.top+5]})()"""
        shot, rect = self.renderer.render({"/index.html": page}, 400, 300, csp=False, probe=probe)
        ratio, = render.pixels.contrast_boxes(shot, (400, 300), [dict(rect=rect, rgba=[255,255,255,1], empty=False)])
        self.assertGreater(ratio, 20)

    def test_07_required_asset_decode(self):
        with tempfile.TemporaryDirectory() as d:
            logo = Path(d) / "broken.png"
            logo.write_bytes(b"broken")
            with self.assertRaisesRegex(cdp.BrowserError, "broken.png|logo.png"):
                self.draw("feature", dict(background=["#ffffff"], ink="#000000"), {}, logo=str(logo))

    def test_07_browser_identifies_font_that_fails_to_decode(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "broken.ttf"
            path.write_bytes(b"broken")
            assets = {"/index.html": b'<style>@font-face{font-family:Broken;src:url(/broken.ttf)}</style>',
                      "/broken.ttf": str(path)}
            with self.assertRaisesRegex(cdp.BrowserError, "broken.ttf"):
                self.renderer.render(assets, 100, 100)

    def test_11_row_label_coverage_uses_headline_font(self):
        seen = []
        def missing(text, paths):
            seen.append((text, paths))
            return []
        font = str(next((ROOT / "skills/listing-kit").rglob("*.ttf")))
        with tempfile.TemporaryDirectory() as d:
            other = Path(d) / "other.ttf"
            other.write_bytes(Path(font).read_bytes())
            with patch.object(render.fontcheck, "missing", side_effect=missing):
                render.render(self.renderer, "panel", (300, 500), "en-US",
                              {"palette": {"background": ["#ffffff"], "ink": "#000000"}},
                              dict(headline=[font], detail=[str(other)]), {"rows": [("Label", "value")]})
            self.assertTrue(any("LABEL" in text and paths == [font] for text, paths in seen))
            self.assertTrue(any("value" in text and paths == [str(other)] for text, paths in seen))

    def test_14_unrelated_events_cannot_extend_deadline(self):
        with patch.dict(os.environ, LK_BROWSER_TIMEOUT="0.6"):
            browser = cdp.Browser()
        try:
            start = time.monotonic()
            # Keep generating protocol events while the evaluated promise is pending.
            with self.assertRaisesRegex(cdp.BrowserError, "time|seconds"):
                cdp.Renderer(browser).render({"/index.html": b"<body></body>"}, 50, 50,
                    csp=False, probe="new Promise(()=>{let n=setInterval(()=>fetch('/noise').catch(()=>0),10);setTimeout(()=>clearInterval(n),1500)})")
            self.assertLess(time.monotonic()-start, 1.5)
        finally:
            browser.close()
        self.assertIsNotNone(browser.proc.poll())
        self.assertFalse(Path(browser.profile).exists())

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
    result = unittest.main(exit=False).result
    for case, reason in result.skipped:
        print(f"  skipped: {reason} ({case.id()})")
    sys.exit(0 if result.wasSuccessful() else 1)
