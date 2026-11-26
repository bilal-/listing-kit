"""Exercise handoff rebuilds against disposable app roots, including interrupted installs."""
import datetime
import hashlib
import html
import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / "skills/listing-kit/scripts"
sys.path.insert(0, str(SCRIPTS / "handoff"))
import handoff


class HandoffTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name).resolve()
        self.app = self.temp / "watchlist/television-guide/2nd/app"
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

    def run_build(self, *, success=True):
        log = io.StringIO()
        with redirect_stderr(log), redirect_stdout(log):
            rc = handoff.main([str(self.app)])
        self.assertEqual(rc, 0 if success else 1, log.getvalue())
        return log.getvalue()

    def test_01_ownership(self):
        self.run_build()
        for name in ("untracked-recipe.txt", "empty-folder", "apple/en-US/text/name.txt", "INDEX.md"):
            with self.subTest(name=name):
                path = self.out / name
                original = path.read_bytes() if path.is_file() else None
                if name == "empty-folder":
                    path.mkdir()
                else:
                    path.write_bytes(b"important")
                message = self.run_build(success=False).rstrip()
                self.assertIn(name, message)
                self.assertTrue(message.endswith("move or delete these, then rerun"), message)
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

    def test_02_empty_upload(self):
        self.out.mkdir(parents=True)
        self.run_build()
        self.assertTrue((self.out / "INDEX.md").is_file())

    def test_02_upload_is_file(self):
        self.put(".listing-kit/upload", b"mine")
        self.run_build(success=False)
        self.assertEqual(self.out.read_bytes(), b"mine")

    def test_02_upload_links(self):
        outside = self.temp / "outside"
        outside.mkdir()
        for link in (self.out.parent, self.out):
            with self.subTest(link=link):
                link.parent.mkdir(exist_ok=True)
                link.symlink_to(outside, target_is_directory=True)
                self.assertIn("symlink", self.run_build(success=False))
                self.assertTrue(link.is_symlink())
                self.assertEqual(list(outside.iterdir()), [])
                link.unlink()

    def test_02_rollback(self):
        self.run_build()
        self.name.write_bytes(b"Changed")
        rename = Path.rename
        for error in (OSError("install failed"), KeyboardInterrupt()):
            def fail_install(src, dst):
                if Path(dst) == self.out and (Path(src) / "apple/en-US/text/name.txt").read_bytes() == b"Changed":
                    raise error
                rename(src, dst)
            with self.subTest(error=type(error).__name__), patch.object(Path, "rename", fail_install):
                with self.assertRaises(type(error)):
                    handoff.build(str(self.app))
                self.assertEqual((self.out / "apple/en-US/text/name.txt").read_bytes(), b"Example")
                self.assertEqual(list(self.out.parent.iterdir()), [self.out])

    def test_recovery_before_invalid_input(self):
        self.run_build()
        self.out.rename(self.out.with_name(".upload-previous"))
        for n in ("one", "two"):
            self.put(".listing-kit/.upload-stage-" + n + "/.listing-kit-upload", b"")
            self.put(".listing-kit/.upload-stage-" + n + "/partial", b"partial")
        (self.out.parent / ".upload-stage-empty").mkdir()
        personal = self.put(".listing-kit/.upload-stage-personal/recipe", b"mine")
        (personal.parent / ".listing-kit-upload").symlink_to(self.name)
        self.name.write_bytes(b"\xff")
        self.run_build(success=False)
        self.assertEqual((self.out / "apple/en-US/text/name.txt").read_bytes(), b"Example")
        self.assertEqual(set(self.out.parent.iterdir()), {self.out, personal.parent})
        self.assertEqual(personal.read_bytes(), b"mine")

    def test_user_file_added_during_rebuild(self):
        self.run_build()
        with handoff.output.locked_upload(self.app) as upload:
            plan = handoff.Plan(self.app)
            plan.add(None, Path("apple/en-US/text/name.txt"), "App Information > Name", b"Changed")
            personal = self.put(".listing-kit/upload/notes-to-self.txt", b"mine")
            with self.assertRaisesRegex(ValueError, "notes-to-self.txt"):
                handoff.output.install(upload, plan)
        self.assertEqual(personal.read_bytes(), b"mine")
        self.assertEqual((self.out / "apple/en-US/text/name.txt").read_bytes(), b"Example")

    def test_concurrent_first_install(self):
        args = [sys.executable, str(SCRIPTS / "handoff/handoff.py"), str(self.app)]
        with subprocess.Popen(args, stdout=subprocess.PIPE) as first:
            subprocess.run(args, check=True, stdout=subprocess.PIPE)
            first.communicate(timeout=15)
            self.assertEqual(first.returncode, 0)
        self.assertEqual(list(self.out.parent.iterdir()), [self.out])
        self.run_build()

    def test_finder_rebuild(self):
        self.run_build()
        for name in (".DS_Store", "._name.txt", "Thumbs.db", "desktop.ini"):
            (self.out / "apple/en-US/text" / name).touch()
        self.run_build()
        self.assertEqual([p.name for p in (self.out / "apple/en-US/text").iterdir()], ["name.txt"])

    def test_internal_links(self):
        self.name.unlink()
        self.name.symlink_to(self.put("shared/name", b"Shared"))
        (self.name.parent.parent / "en-GB").symlink_to("en-US")
        self.run_build()
        self.assertEqual((self.out / "apple/en-GB/text/name.txt").read_bytes(), b"Shared")
        self.name.unlink()
        outside = self.temp / "external-name"
        outside.write_bytes(b"private")
        self.name.symlink_to(outside)
        self.assertIn("name.txt", self.run_build(success=False))

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

    def test_override_destination(self):
        # A real override and source whose destination would escape the staging folder.
        source = self.temp / "escaped.txt"
        source.write_bytes(b"source")
        override = {"stores": {"apple": {"fields": [
            {"stem": os.path.relpath(source.with_suffix(""), self.name.parent), "scope": "locale", "label": "Bad"}]}}}
        self.put(".listing-kit/specs.override.json", json.dumps(override).encode())
        self.assertIn("escaped", self.run_build(success=False))
        self.assertFalse((self.out / "escaped.txt").exists())
        self.assertFalse(self.out.exists())
        self.assertEqual(list(self.temp.rglob("escaped.txt")), [source])
        self.assertEqual(source.read_bytes(), b"source")

    def test_incomplete_override(self):
        for entry in ({"stem": "custom", "label": "Custom"}, {"stem": "custom", "scope": "locale"}):
            self.put("fastlane/metadata/en-US/custom.txt", b"value")
            self.put(".listing-kit/specs.override.json", json.dumps(
                {"stores": {"apple": {"fields": [entry]}}}).encode())
            self.assertIn("override", self.run_build(success=False))

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
        self.assertIn("use for every language", (self.out / "INDEX.md").read_text())
        self.put("store-assets/apple/de-DE/header.jpg", b"header")
        self.png("store-assets/play/it-IT/screenshots/xr/x.png", 1920, 1200)
        self.png("fastlane/screenshots/fr-FR/a.png", 1206, 2622)
        self.run_build()
        for loc in ("de-DE", "fr-FR"):
            self.assertFalse((self.out / "apple" / loc / "text/name.txt").exists())
        self.assertTrue((self.out / "apple/default/text/name.txt").is_file())
        self.assertTrue(list((self.out / "play/it-IT").glob("*Android XR/*x.png")))

    def test_06_shared_sizes(self):
        cases = (("home_tv", 3840, 2160, "Apple TV"), ("home_vision", 3840, 2160, "Apple Vision Pro"),
                 ("home", 2732, 2048, "iPad 13in"), ("home_ipad", 2048, 2732, "iPad 13in"),
                 ("home_ipad13", 2048, 2732, "iPad 13in"), ("home_ipad-12.9", 2732, 2048, "iPad 12.9in"))
        for name, w, h, _ in cases:
            self.png("fastlane/screenshots/en-US/" + name + ".png", w, h)
        self.png("fastlane/screenshots/appleTV/en-US/else_vision.png", 3840, 2160)
        self.run_build()
        for name, _, _, label in cases:
            self.assertTrue(list((self.out / "apple/en-US").glob("*" + label + "/*" + name + ".png")), name)
        self.assertTrue(list((self.out / "apple/en-US").glob("*Apple TV/*else_vision.png")))

    def test_ambiguous_size(self):
        self.png("fastlane/screenshots/en-US/home.png", 3840, 2160)
        log = self.run_build(success=False)
        for hint in ("home.png", "ambiguous", "tv", "vision"):
            self.assertIn(hint, log)

    def test_manual_slot(self):
        self.png("store-assets/play/en-US/screenshots/xr/x.png", 1206, 2622)
        self.run_build()
        self.png("store-assets/apple/en-US/screenshots/vision-pro/wrong.png", 1206, 2622)
        self.assertIn("wrong.png", self.run_build(success=False))

    def test_xr_alias_removed(self):
        self.png("store-assets/play/en-US/screenshots/android-xr/x.png", 1920, 1200)
        self.assertIn("android-xr", self.run_build(success=False))

    def test_framed_notes_are_ignored(self):
        new_app = self.temp / "recipes"
        self.app.rename(new_app)
        self.app = new_app
        self.out = self.app / ".listing-kit/upload"
        self.png("fastlane/screenshots/en-US/home.png", 1206, 2622)
        self.put("fastlane/screenshots/en-US/notes_framed.txt", b"draft")
        self.run_build()
        self.assertTrue(list(self.out.rglob("01-home.png")))

    def test_07_active_set(self):
        for name, wh in (("duo_framed", (1398, 2034)), ("2_framed", (1206, 2622)), ("2", (1206, 2622)), ("unframed", (1206, 2622)), ("03_watchlist", (1206, 2622)),
                         ("03_watchlist_framed", (1206, 2622)), ("wrist", (422, 514))):
            self.png("fastlane/screenshots/en-US/" + name + ".png", *wh)
        self.put(".listing-kit/asset-plan.json", b'{"apple":{"en-US":{"deferredScreenshots":{"iPhone Duo":"Later"}}}}')
        self.run_build()
        self.assertEqual(sorted(p.name.split("-", 1)[-1] for p in self.out.rglob("*.png")), ["framed.png", "watchlist_framed.png", "wrist.png"])

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

    def test_header_candidates(self):
        base = "store-assets/apple/en-US/"
        for name in (".DS_Store", "._header.png", ".hidden.jpg", "layout.psd", "notes.txt"):
            self.put(base + name, b"draft")
        self.put(base + "header-21x9.mov", b"movie")
        self.png(base + "wide.png", 5244, 2950)
        self.png(base + "cinema.png", 3840, 1646)
        self.run_build()
        index = (self.out / "INDEX.md").read_text()
        self.assertEqual(sorted(p.name for p in (self.out / "apple/en-US/graphics").iterdir()), ["cinema.png", "header-21x9.mov", "wide.png"])
        for name, ratio in (("cinema.png", "21:9"), ("wide.png", "16:9"), ("header-21x9.mov", "21:9")):
            self.assertTrue(any(name in line and ("Header Asset " + ratio) in line for line in index.splitlines()))

    def test_play_only_and_empty_text(self):
        self.name.unlink()
        self.name.parent.rmdir()
        for name, raw in (("title", b"Play"), ("video", b""), ("changelogs/1", b"")):
            self.put("fastlane/metadata/android/fr-FR/" + name + ".txt", raw)
        self.run_build()
        self.assertEqual([p.name for p in self.out.rglob("*.txt")], ["title.txt"])
        self.assertFalse((self.out / "apple").exists())
        index = (self.out / "INDEX.md").read_text()
        self.assertIn("Play", index.splitlines()[0])
        self.assertIn("fr-FR", index)
        self.assertNotIn("App Store Connect", index)

    def test_empty_assets(self):
        self.png("fastlane/screenshots/en-US/home.png", 1206, 2622)
        self.put("fastlane/screenshots/en-US/empty_framed.png", b"")
        for path in ("store-assets/apple/en-US/header.png",
                     "store-assets/apple/en-US/screenshots/vision-pro/empty.png",
                     "fastlane/metadata/android/en-US/images/icon.jpg",
                     "fastlane/metadata/android/en-US/images/phoneScreenshots/empty.png"):
            self.put(path, b"")
        self.png("fastlane/metadata/android/en-US/images/icon.png", 512, 512)
        self.run_build()
        self.assertEqual(sorted(p.name for p in self.out.rglob("*.png")), ["01-home.png", "icon.png"])
        self.assertFalse(list(self.out.rglob("*.jpg")))
        omitted = (self.out / "INDEX.md").read_text().split("## Not included")[1]
        for path in self.app.rglob("*"):
            if path.is_file() and path.suffix in (".png", ".jpg") and path.stat().st_size == 0:
                self.assertIn(str(path.relative_to(self.app)), omitted)

    def test_manifest(self):
        self.put("store-assets/apple/en-US/a|`%0A\nb.mov", b"movie")
        self.run_build()
        files = {str(p.relative_to(self.out)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.out.rglob("*") if p.is_file() and p.name != ".listing-kit-upload"}
        self.assertEqual(json.loads((self.out / ".listing-kit-upload").read_text()), files)
        self.assertEqual((self.out / ".gitignore").read_text().splitlines(), ["*"])
        index = (self.out / "INDEX.md").read_text()
        self.assertNotIn("SHA-256", index)
        self.assertNotIn("a|`", index)
        # Both guides must display a path that can be copied verbatim.
        self.assertIn("a|`%0A\nb.mov", html.unescape(index))
        self.assertIn("a|`%0A\nb.mov", html.unescape((self.out / "INDEX.html").read_text()))
        self.run_build()

    def test_first_time_index(self):
        self.put("fastlane/metadata/copyright.txt", b"Mine")
        self.put("fastlane/metadata/default/privacy_url.txt", b"url")
        self.put("fastlane/metadata/fr-FR/description.txt", b"Bonjour")
        self.put(".listing-kit/asset-plan.json", b'{"apple":{"en-US":{"deferredScreenshots":{"iPhone Duo":"Awaiting artwork"}}}}')
        self.run_build()
        index = (self.out / "INDEX.md").read_text()
        for term in ("copy", "paste", "drag", "file-name order", "cmd+shift+.",
                     "english (u.s.)", "## not included", "review contact", "demo account", "age rating",
                     "privacy answers", "pricing", "the build", "iphone duo", "awaiting artwork"):
            self.assertIn(term, index.lower())
        for filename, instruction in (("copyright.txt", "the version under iOS App"), ("name.txt", "App Information"),
                                      ("description.txt", "the version under iOS App"), ("privacy_url.txt", "App Privacy"),
                                      ("privacy_url.txt", "from default")):
            self.assertTrue(any(filename in line and instruction in line for line in index.splitlines()))
        self.assertEqual(list(self.out.rglob("copyright.txt")), [self.out / "apple/app-wide/copyright.txt"])

    def test_backup_marker_survives_interrupted_removal(self):
        self.run_build()
        previous = self.out.with_name(".upload-previous")
        marker = previous / ".listing-kit-upload"
        rmtree = handoff.shutil.rmtree

        def interrupt(path, *args, **kwargs):
            path = Path(path)
            if path == previous:
                marker.unlink()  # rmtree may visit the marker first.
            elif previous not in path.parents:
                return rmtree(path, *args, **kwargs)
            raise OSError("cleanup interrupted")

        with patch.object(handoff.shutil, "rmtree", side_effect=interrupt):
            self.assertIn("cleanup interrupted", self.run_build(success=False))
        self.assertTrue(marker.is_file())
        self.run_build()
        self.assertFalse(previous.exists())

    def test_bundled_rules_error(self):
        with patch.object(handoff, "apple", side_effect=KeyError("broken")):
            error = self.run_build(success=False)
        self.assertIn("broken", error)
        self.assertNotIn("override", error)

    def test_hidden_changelog(self):
        self.put("fastlane/metadata/android/en-US/changelogs/._default.txt", b"\xff")
        self.run_build()
        self.assertFalse(list(self.out.rglob("*._default*")))

    def test_order_prefixes(self):
        for folder in ("fastlane/screenshots/en-US", "fastlane/metadata/android/en-US/images/phoneScreenshots"):
            for name in ("01. Home", "02 - Notes", "03_Shop", "3D_maps"):
                self.png(folder + "/" + name + ".png", 1206, 2622)
        self.run_build()
        for store in ("apple", "play"):
            self.assertEqual(sorted(p.name for p in (self.out / store).rglob("*.png")),
                             ["01-Home.png", "02-Notes.png", "03-Shop.png", "04-3D_maps.png"])

    def test_console_instructions(self):
        meta = "fastlane/metadata/"
        for name, value in (("primary_category", "FOOD_AND_DRINK"), ("secondary_category", "DEVELOPER_TOOLS"),
                            ("en-US/release_notes", "Changes"), ("en-US/privacy_url", "https://example.org"),
                            ("android/en-US/title", "Android")):
            self.put(meta + name + ".txt", value.encode())
        msg = self.run_build()
        index = (self.out / "INDEX.md").read_text()
        for term, content in ((str(self.out / "INDEX.html"), msg), ("Example", index.splitlines()[0]),
                              (datetime.date.today().isoformat(), index.split("##")[0])):
            with self.subTest(term=term):
                self.assertIn(term, content)
        for term, content in (("opened Finder", msg), ("use for every language", index)):
            with self.subTest(term=term):
                self.assertNotIn(term, content)
        for term in ("App Store Connect > your app > App Information", "App Store Connect > your app > App Privacy",
                     "the version under iOS App (for example 1.0 Prepare for Submission)",
                     "Play Console > your app > Grow users > Store presence > Main store listing > App name",
                     "choose Food & Drink from the list", "choose Developer Tools from the list",
                     "updates only: not shown for a first version", "pick or add the language", "relative to the folder",
                     "folder is a copy", "fastlane/", "rerun", "refused", "upload each graphic"):
            with self.subTest(term=term):
                self.assertIn(term.lower(), index.lower())

    def test_missing_fields(self):
        self.put("fastlane/metadata/default/keywords.txt", b"fallback")
        self.put("fastlane/metadata/android/fr-FR/short_description.txt", b"Bonjour")
        self.put("fastlane/metadata/en-US/description.txt", b"  ")
        override = {"stores": {"apple": {"fields": [
            {"stem": "custom", "scope": "locale", "label": "Custom field", "required": {"rule": "always"}},
            {"stem": "maybe", "scope": "locale", "label": "Unknown field",
             "required": {"rule": "if", "condition": "unknown"}},
            {"stem": "exception", "scope": "locale", "label": "Possible exception",
             "required": {"rule": "always", "unless": "unknown"}}]}}}
        self.put(".listing-kit/specs.override.json", json.dumps(override).encode())
        self.run_build()
        missing = (self.out / "INDEX.md").read_text().split("## Missing")[1].split("## ")[0]
        for label in ("Custom field", "Description", "Copyright", "Primary category", "App name", "Full description"):
            self.assertIn(label, missing)
        for label in ("Keywords", "What's new", "Subtitle", "Unknown field", "Possible exception", "Short description"):
            self.assertNotIn(label, missing)
        self.assertIn("en-US", missing)
        self.assertIn("fr-FR", missing)

    def test_html_matches_markdown(self):
        self.name.write_text("A <script> & Co")
        self.png("fastlane/screenshots/en-US/01_home.png", 1206, 2622)
        self.run_build()
        page = (self.out / "INDEX.html").read_text()
        self.assertNotIn("<script", page.lower())
        self.assertNotRegex(page.lower(), r"(?:src|href)=[\"'](?:https?:)?//")
        self.assertIn("A &lt;script&gt; &amp; Co", page)
        visible = html.unescape(page)
        for line in (self.out / "INDEX.md").read_text().splitlines():
            if not line or line.startswith("|---"):
                continue
            for cell in line.strip("|").split("|"):
                content = html.unescape(cell.strip().lstrip("#- ").replace(chr(96), ""))
                self.assertIn(content, visible)

    def test_open_nonzero(self):
        opener = self.put("bin/open", b'#!/bin/sh\nprintf "%s" "$1" > "$0.called"\nexit 2\n')
        opener.chmod(0o755)
        with patch.object(sys, "platform", "darwin"), patch.dict(os.environ, PATH=str(opener.parent)):
            log = io.StringIO()
            with redirect_stdout(log):
                self.assertEqual(handoff.main([str(self.app), "--open"]), 0)
            self.assertEqual(opener.with_suffix(".called").read_text(), str(self.out / "INDEX.html"))
            self.assertIn("Could not open", log.getvalue())
            self.assertNotIn("opened Finder", log.getvalue())

    def test_12_opener(self):
        for platform, command in (("darwin", "open"), ("linux", "xdg-open")):
            with self.subTest(platform=platform), patch.object(sys, "platform", platform), \
                    patch.object(handoff.shutil, "which", return_value=command), \
                    patch.object(subprocess, "call", return_value=0) as call, patch.object(subprocess, "Popen") as popen:
                self.assertTrue(handoff.open_index("INDEX.html"))
                if platform == "linux":
                    self.assertEqual(popen.call_args[0][0], [command, "INDEX.html"])
                    self.assertTrue(popen.call_args[1]["start_new_session"])
                    self.assertFalse(popen.return_value.method_calls)
                else:
                    self.assertEqual(call.call_args[0][0], [command, "INDEX.html"])


if __name__ == "__main__":
    unittest.main()
