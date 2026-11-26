"""Exercise handoff rebuilds against disposable app roots, including interrupted installs."""
import hashlib
import io
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote

SCRIPTS = Path(__file__).resolve().parents[2] / "skills/listing-kit/scripts"
sys.path.insert(0, str(SCRIPTS / "handoff"))
import handoff


class HandoffTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name).resolve()
        self.app = self.temp / "project/app"
        self.out = self.app / ".listing-kit/upload"
        self.name = self.put("fastlane/metadata/en-US/name.txt", b"Example")

    def put(self, rel, content):
        path = self.app / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def png(self, rel, w, h):
        header = struct.pack(">I4sIIBBBBB", 13, b"IHDR", w, h, 8, 2, 0, 0, 0)
        return self.put(rel, b"\x89PNG\r\n\x1a\n" + header + bytes(4) + b"\0\0\0\0IDAT")

    def run_build(self, *args, success=True):
        log = io.StringIO()
        with redirect_stderr(log), redirect_stdout(log):
            rc = handoff.main([str(self.app)] + list(map(str, args)))
        self.assertEqual(rc, 0 if success else 1, log.getvalue())
        return log.getvalue()

    def test_01_protected_paths(self):
        for target in (self.app / "fastlane/child", self.app / "store-assets/new",
                       self.app / "fastlane", self.app / "store-assets", self.app, self.app.parent):
            with self.subTest(target=target):
                self.run_build("--out", target, success=False)
                self.assertEqual(self.name.read_bytes(), b"Example")

    def test_01_ownership(self):
        self.run_build()
        for name in ("extra", "empty-folder", "apple/en-US/text/name.txt", "INDEX.md"):
            with self.subTest(name=name):
                path = self.out / name
                original = path.read_bytes() if path.is_file() else None
                if name == "empty-folder":
                    path.mkdir()
                else:
                    path.write_bytes(b"important")
                self.assertIn(name, self.run_build(success=False))
                if original is not None:
                    self.assertEqual(path.read_bytes(), b"important")
                    path.write_bytes(original)
                elif path.is_dir():
                    path.rmdir()
                else:
                    self.assertEqual(path.read_bytes(), b"important")
                    path.unlink()

    def test_01_unmarked(self):
        self.out.mkdir(parents=True)
        (self.out / "personal.txt").touch()
        self.assertIn("personal.txt", self.run_build(success=False))
        self.assertTrue((self.out / "personal.txt").exists())
        (self.out / ".listing-kit-upload").touch()
        self.assertIn("personal.txt", self.run_build(success=False))

    def test_02_special_destinations(self):
        target = self.temp / "file"
        target.write_text("mine")
        link = self.temp / "alias"
        link.symlink_to(self.temp / "project", target_is_directory=True)
        for dest in (target, link, link / "child"):
            with self.subTest(dest=dest):
                self.run_build("--out", dest, success=False)
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_text(), "mine")

    def test_02_rollback(self):
        self.run_build()
        self.name.write_bytes(b"Changed")
        rename = os.rename
        for error in (OSError("install failed"), KeyboardInterrupt()):
            def fail_install(src, dst):
                if Path(dst) == self.out and (Path(src) / "apple/en-US/text/name.txt").read_bytes() == b"Changed":
                    raise error
                rename(src, dst)
            with self.subTest(error=type(error).__name__), patch.object(os, "rename", fail_install):
                try:
                    handoff.build(str(self.app))
                except (OSError, KeyboardInterrupt):
                    pass
                self.assertEqual((self.out / "apple/en-US/text/name.txt").read_bytes(), b"Example")
                self.assertEqual(list(self.out.parent.iterdir()), [self.out])

    def test_02_recover_after_process_death(self):
        self.run_build()
        self.name.write_bytes(b"Changed")
        script = """
import os, sys
sys.path.insert(0, sys.argv[1])
import handoff
rename = os.rename
def interrupt(src, dst):
    if str(dst) == sys.argv[3]:
        os._exit(77)
    rename(src, dst)
os.rename = interrupt
handoff.build(sys.argv[2])
"""
        proc = subprocess.run([sys.executable, "-c", script, str(SCRIPTS / "handoff"), str(self.app), str(self.out)])
        self.assertEqual(proc.returncode, 77)
        self.name.write_bytes(b"\xff")
        self.run_build(success=False)
        self.assertEqual((self.out / "apple/en-US/text/name.txt").read_bytes(), b"Example")
        self.assertEqual(list(self.out.parent.iterdir()), [self.out])

    @unittest.skipUnless(os.name == "posix", "POSIX termination signals")
    def test_02_termination_during_install(self):
        self.run_build()
        self.name.write_bytes(b"Changed")
        script = """
import os, signal, sys
sys.path.insert(0, sys.argv[1])
import handoff
rename = os.rename
def terminate(src, dst):
    if str(dst) == sys.argv[3]:
        os.kill(os.getpid(), signal.SIGTERM)
    rename(src, dst)
os.rename = terminate
handoff.build(sys.argv[2])
"""
        proc = subprocess.run([sys.executable, "-c", script, str(SCRIPTS / "handoff"), str(self.app), str(self.out)])
        self.assertLess(proc.returncode, 0)
        self.assertIn((self.out / "apple/en-US/text/name.txt").read_bytes(), [b"Example", b"Changed"])
        self.assertEqual(list(self.out.parent.iterdir()), [self.out])

    def test_03_source_links(self):
        target = self.temp / "outside"
        target.write_text("private")
        self.name.unlink()
        self.name.symlink_to(target)
        self.assertIn("name.txt", self.run_build(success=False))
        self.name.unlink()
        self.name.parent.rmdir()
        self.name.parent.symlink_to(self.temp, target_is_directory=True)
        self.assertIn("en-US", self.run_build(success=False))

    def test_03_override_paths(self):
        self.put(".listing-kit/specs.override.json", json.dumps({"stores": {"apple": {"fields": [
            {"stem": "../../../escaped", "scope": "app", "label": "Bad"}]}}}).encode())
        self.assertIn("escaped", self.run_build(success=False))

    def test_03_stage_destination(self):
        for dest in (Path("../escape"), self.temp / "escape"):
            plan = handoff.Plan()
            plan.add(None, dest, "test", b"escaped")
            with patch.object(handoff, "inventory", return_value=(plan, {"verified": "today"})):
                self.assertIn("staging", self.run_build(success=False))
            self.assertFalse((self.temp / "escape").exists())
            self.assertFalse(self.out.exists())

    def test_03_copy_rechecks_source(self):
        header = self.put("store-assets/apple/en-US/header.mov", b"header")
        outside = self.temp / "private"
        outside.write_bytes(b"secret")
        install = handoff.output.install
        def change(*args):
            header.unlink()
            header.symlink_to(outside)
            return install(*args)
        with patch.object(handoff.output, "install", side_effect=change):
            self.assertIn("header.mov", self.run_build(success=False))
        self.assertFalse(self.out.exists())

    def test_03_index_cannot_follow_a_staging_link(self):
        outside = self.temp / "private"
        outside.write_bytes(b"mine")
        write = handoff.output._write
        def link_index(stage, *args):
            (stage / "INDEX.md").symlink_to(outside)
            return write(stage, *args)
        with patch.object(handoff.output, "_write", side_effect=link_index):
            self.run_build(success=False)
        self.assertEqual(outside.read_bytes(), b"mine")
        self.assertFalse(self.out.exists())

    def test_04_special_roots(self):
        self.put("fastlane/metadata/default/subtitle.txt", b"Sub")
        for name in ("fonts", "review_information", "trade_representative_contact_information", "app_clip_review_information"):
            self.put("fastlane/metadata/" + name + "/name.txt", b"Private")
        self.png("fastlane/screenshots/appleTV/es-ES/tv.png", 1920, 1080)
        self.png("fastlane/screenshots/iMessage/fr-FR/msg.png", 1206, 2622)
        self.run_build()
        self.assertEqual(sorted(p.name for p in (self.out / "apple").iterdir()), ["en-US", "es-ES", "fr-FR"])
        self.assertTrue(list((self.out / "apple/es-ES").glob("*Apple TV/*tv.png")))
        self.assertTrue(list((self.out / "apple/fr-FR").glob("*iMessage*/*msg.png")))

    def test_05_locale_union_and_default(self):
        self.name.unlink()
        self.name.parent.rmdir()
        self.put("fastlane/metadata/default/name.txt", b"Default")
        self.put("fastlane/metadata/android/en-US/title.txt", b"Play")
        self.run_build()
        self.assertEqual((self.out / "apple/default/text/name.txt").read_bytes(), b"Default")
        self.put("store-assets/apple/de-DE/header.jpg", b"header")
        self.png("store-assets/play/it-IT/screenshots/android-xr/x.png", 1920, 1200)
        self.png("fastlane/screenshots/fr-FR/a.png", 1206, 2622)
        self.run_build()
        for loc in ("de-DE", "fr-FR"):
            self.assertEqual((self.out / "apple" / loc / "text/name.txt").read_bytes(), b"Default")
        self.assertFalse((self.out / "apple/default").exists())
        self.assertTrue(list((self.out / "play/it-IT").glob("*Android XR/*x.png")))

    def test_06_shared_sizes(self):
        for name, wh in (("tv", (3840, 2160)), ("vision", (3840, 2160)), ("ipad", (2048, 2732)),
                         ("12.9", (2732, 2048)), ("2nd", (2048, 2732)), ("app_ipad_pro_129", (2048, 2732))):
            self.png("fastlane/screenshots/en-US/" + name + ".png", *wh)
        self.run_build()
        for name, label in (("tv", "Apple TV"), ("vision", "Apple Vision Pro"), ("ipad", "iPad 13in"),
                            ("12.9", "iPad 12.9in"), ("2nd", "iPad 12.9in"), ("app_ipad_pro_129", "iPad 12.9in")):
            self.assertTrue(list((self.out / "apple/en-US").glob("*" + label + "/*" + name + ".png")), name)

    def test_06_manual_slot_size(self):
        for store, slot in (("apple", "vision-pro"), ("play", "xr")):
            path = self.png("store-assets/%s/en-US/screenshots/%s/wrong.png" % (store, slot), 1206, 2622)
            self.assertIn("wrong.png", self.run_build(success=False))
            path.unlink()

    def test_07_active_set(self):
        for name, wh in (("duo_framed", (1398, 2034)), ("2_framed", (1206, 2622)), ("2", (1206, 2622)), ("watch", (422, 514))):
            self.png("fastlane/screenshots/en-US/" + name + ".png", *wh)
        self.put(".listing-kit/asset-plan.json", b'{"apple":{"en-US":{"deferredScreenshots":{"iPhone Duo":"Later"}}}}')
        self.run_build()
        self.assertEqual(sorted(p.name.split("-", 1)[-1] for p in self.out.rglob("*.png")), ["2_framed.png", "watch.png"])

    def test_07_review_and_handoff_manual_set(self):
        self.png("store-assets/apple/en-US/screenshots/mac/mac.png", 1280, 800)
        self.png("store-assets/apple/en-US/screenshots/iphone-duo-outer/old.png", 1398, 2034)
        self.put(".listing-kit/asset-plan.json", b'{"apple":{"en-US":{"deferredScreenshots":{"iPhone Duo":"Later"}}}}')
        self.run_build()
        subprocess.run(["bash", str(SCRIPTS / "package/build-review.sh"), str(self.app)],
                       check=True, stdout=subprocess.DEVNULL)
        page = (self.app / "listing-review.html").read_text()
        self.assertIn('src="store-assets/apple/en-US/screenshots/mac/mac.png"', page)
        self.assertNotIn('src="store-assets/apple/en-US/screenshots/iphone-duo-outer/old.png"', page)
        self.assertEqual([p.name for p in self.out.rglob("*.png")], ["01-mac.png"])

    def test_08_text_bytes(self):
        self.name.write_bytes(b"  Example\r\n")
        raw = b" a\r\nb\r\n"
        self.put("fastlane/metadata/android/en-US/video.txt", raw)
        self.put("fastlane/metadata/android/en-US/changelogs/123.txt", raw)
        self.run_build()
        for path, expected in (("apple/en-US/text/name.txt", b"Example"),
                               ("play/en-US/text/video.txt", raw), ("play/en-US/text/release-notes-123.txt", raw)):
            self.assertEqual((self.out / path).read_bytes(), expected)

    def test_08_invalid_text(self):
        self.put("fastlane/metadata/default/name.txt", b"Default")
        for path in (self.name, self.put("fastlane/metadata/android/en-US/video.txt", b"url")):
            path.write_bytes(b"\xff")
            self.assertIn(path.name, self.run_build(success=False))
            path.write_bytes(b"valid")
        self.name.chmod(0)
        try:
            if not os.access(self.name, os.R_OK):
                self.assertIn("name.txt", self.run_build(success=False))
        finally:
            self.name.chmod(0o600)

    def test_09_order(self):
        for stem in ("1", "2", "10"):
            for folder in ("fastlane/screenshots/en-US", "fastlane/metadata/android/en-US/images/phoneScreenshots"):
                self.png(folder + "/" + stem + ".png", 1206, 2622)
        self.run_build()
        for store, order in (("apple", ["1", "2", "10"]), ("play", ["1", "10", "2"])):
            paths = sorted(p.name for p in (self.out / store).rglob("*.png"))
            self.assertEqual(paths, ["%02d-%s.png" % (i, stem) for i, stem in enumerate(order, 1)])

    def test_10_graphics(self):
        img = "fastlane/metadata/android/en-US/images/"
        self.put(img + "TVBanner.JPG", b"banner")
        self.put("store-assets/apple/en-US/header.mov", b"movie")
        self.run_build()
        self.assertEqual((self.out / "apple/en-US/graphics/header.mov").read_bytes(), b"movie")
        self.assertEqual((self.out / "play/en-US/graphics/TVBanner.JPG").read_bytes(), b"banner")
        self.put(img + "tvBanner.JPEG", b"duplicate")
        log = self.run_build(success=False)
        self.assertIn("TVBanner.JPG", log)
        self.assertIn("tvBanner.JPEG", log)

    def test_11_index(self):
        self.put("fastlane/metadata/copyright.txt", b"Mine")
        name = "a|`%0A\nb.mov"
        self.put("store-assets/apple/en-US/" + name, b"movie")
        self.run_build()
        rows = [s.split(" | ") for s in (self.out / "INDEX.md").read_text().splitlines() if re.match(r"^\| \d+ ", s)]
        found = {}
        for i, (number, path, place, digest) in enumerate(rows, 1):
            self.assertEqual(int(number[2:]), i)
            path = unquote(path.strip("`"))
            self.assertEqual(digest.rstrip(" |").strip("`"), hashlib.sha256((self.out / path).read_bytes()).hexdigest())
            found[path] = place.strip("`")
        self.assertIn("apple/en-US/graphics/" + name, found)
        self.assertEqual(found["apple/en-US/text/copyright.txt"], "App Store Connect > Version > Copyright")
        self.run_build()

    def test_12_opener(self):
        for platform, command in (("darwin", "open"), ("linux", "xdg-open"), ("win32", None)):
            with self.subTest(platform=platform), patch.object(sys, "platform", platform), \
                    patch.object(os, "name", "nt" if not command else "posix"), \
                    patch.object(os, "startfile", create=True) as start, \
                    patch.object(handoff.shutil, "which", return_value=command), \
                    patch.object(subprocess, "call", return_value=0) as call, patch.object(subprocess, "Popen") as popen:
                self.assertTrue(handoff.open_folder("folder"))
                if platform == "linux":
                    self.assertEqual(popen.call_args[0][0], [command, "folder"])
                    self.assertTrue(popen.call_args[1]["start_new_session"])
                    self.assertFalse(popen.return_value.method_calls)
                elif platform == "darwin":
                    self.assertEqual(call.call_args[0][0], [command, "folder"])
                else:
                    start.assert_called_once_with("folder")


if __name__ == "__main__":
    unittest.main()
