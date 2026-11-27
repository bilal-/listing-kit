import hashlib
import html
import io
from contextlib import redirect_stdout
from html.parser import HTMLParser
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

KIT = Path(sys.argv.pop(1)).resolve()


class Images(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.images = {}
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            image = dict(attrs)
            self.images[image["src"]] = image.get("alt")


class ImportListing(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        subprocess.run(["git", "init", "-q", self.root], check=True)
        self.config = self.root / ".listing-kit"
        self.config.mkdir()
        self.meta = self.root / "fastlane/metadata/android"
        (self.meta / "en-US").mkdir(parents=True)
        (self.meta / "en-US/title.txt").write_text("Map Notes")
        (self.root / "app.json").write_text('{"expo":{}}')
        phone = dict(id="handset", store="play", slot="phone", size=[1080, 1920], state="active")
        self.plan = dict(format=2, app="org.example.map", locales=["en-US"],
                         style=dict(palette=dict(background=["#eeeeee"], ink="#111111"),
                                    fonts={"default": dict(headline=["bundled:Inter"], detail=["bundled:Inter"])}),
                         targets=[phone, dict(phone, id="slate", slot="ten-inch", size=[1920, 1080])],
                         screens=[dict(id="map", flow=".listing-kit/flows/map.yaml"),
                                  dict(id="lakes", flow=".listing-kit/flows/lakes.yaml"),
                                  dict(id="legend", panel=dict(headline={"en-US": "Legend"}, rows=[
                                      dict(label={"en-US": "River"}, text={"en-US": "Blue"})]))],
                         graphics=dict(play=dict(featureGraphic=dict(headline={"en-US": "Maps"}))))
        self.save()

    def save(self):
        (self.config / "listing.json").write_text(json.dumps(self.plan))

    def cli(self, *args, rc=0):
        result = subprocess.run([KIT / "bin/listing-kit", *args], cwd=self.root,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if rc is not None:
            self.assertEqual(result.returncode, rc, result.stdout)
        return result.stdout

    def test_selectors(self):
        for flags, wanted in [(("--screen", "legend"), 2), (("--screen", "legend", "--target", "slate"), 1)]:
            with self.subTest(flags=flags):
                self.cli("compose", "--preview", *flags)
                page = (self.config / "preview.html").read_text()
                self.assertEqual(page.count("<iframe "), wanted)
                self.assertNotIn("featureGraphic.png", page)
                self.assertEqual(self.cli("compose", "--dry-run", *flags).count("would write "), wanted)

    def test_partial_preview_and_dry_run(self):
        for mode in ("--preview", "--dry-run"):
            with self.subTest(mode=mode):
                out = self.cli("compose", mode, rc=1)
                self.assertIn(".listing-kit/raw/handset/en-US/map.png", out)
                self.assertIn("4 missing captures", out)
                if mode == "--preview":
                    page = (self.config / "preview.html").read_text()
                    self.assertIn("featureGraphic.png", page)
                    self.assertIn("03_legend.png", page)
                    self.assertIn("no raw capture", page)
                    self.assertEqual(page.count("<iframe "), 3)
                else:
                    self.assertEqual(out.count("would write "), 3)

    def test_unversioned(self):
        self.plan = {"trees": {"play": {"metadata": "unused"}}, "gallery": ["one"]}
        self.save()
        original = (self.config / "listing.json").read_bytes()
        report = self.cli("doctor")
        self.assertIn("found a plan in an older, unversioned layout", report)
        self.assertIn("references/plan-file.md", report)
        out = self.cli("detect")
        for value in ("expo-managed", "apple play", "play.metadata\tfastlane/metadata/android"):
            self.assertIn(value, out)
        self.assertNotIn("unused", out)
        out = self.cli("validate", rc=1)
        self.assertIn("title: 9", out)
        self.assertEqual(out.count("unversioned"), 1)
        self.assertIn("ignored", out)
        self.assertEqual((self.config / "listing.json").read_bytes(), original)

    def test_unversioned_with_only_a_store_tree(self):
        (self.root / "app.json").unlink()
        self.plan = {"custom": "gallery"}
        self.save()
        self.assertIn("stores\tplay\n", self.cli("detect"))

    def test_doctor_invalid(self):
        for raw, expected in [("{", "INVALID"), ('{"format":99}', "newer plan format 99")]:
            (self.config / "listing.json").write_text(raw)
            self.assertIn(expected, self.cli("doctor"))

    def test_outdated_hook(self):
        hook = self.root / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\n# BEGIN listing-kit review hook\n")
        hook.chmod(0o755)
        self.assertIn("outdated", self.cli("hook", "status", rc=1))
        self.assertNotIn("MISSING hook", self.cli("doctor"))

    def test_android_declaration(self):
        out = self.cli("detect")
        self.assertIn("supportsAndroidPhone\tunknown\tno static evidence", out)
        self.assertIn("active phone target", out)
        self.assertIn("runtime support unverified", out)

    def test_help_and_import_guide(self):
        self.assertIn("compose --help", self.cli("help"))
        help_text = self.cli("compose", "--help")
        for term in (".listing-kit/preview.html", "raw capture", "--screen", "--target"):
            self.assertIn(term, help_text)
        guide = (KIT / "references/plan-file.md").read_text()
        for term in ("listing.legacy.json", "listing-kit review", "compose --preview"):
            self.assertIn(term, guide)

    def test_archived_raw(self):
        self.plan["targets"][0]["rawPattern"] = "archive/{locale}/{index}_{screen}.png"
        self.save()
        expected = "archive/en-US/01_map.png"
        self.assertIn(expected, self.cli("plan", "outputs"))
        capture = json.loads(self.cli("plan", "manifest"))["captures"][0]
        self.assertEqual(capture["rawPath"], ".listing-kit/raw/handset/en-US/map.png")
        path = self.root / expected
        path.parent.mkdir(parents=True)
        path.write_bytes(b"archived")
        self.assertIn("would write", self.cli("compose", "--target", "handset", "--screen", "map", "--dry-run"))
        self.assertEqual(path.read_bytes(), b"archived")
        for invalid in ("../archive/{screen}.png", "/archive/{screen}.png", "archive/{other}.png"):
            self.plan["targets"][0]["rawPattern"] = invalid
            self.save()
            self.assertIn("rawPattern", self.cli("plan", "check", rc=1))

    def test_capture_with_archive(self):
        sys.path.insert(0, str(KIT / "scripts/capture"))
        import capture
        self.plan["targets"][0]["rawPattern"] = "archive/{screen}.png"
        self.save()
        (self.config / "flows").mkdir()
        (self.config / "flows/map.yaml").touch()
        args = ["capture", str(self.root), "--dry-run", "--target", "handset", "--screen", "map"]
        log = io.StringIO()
        with redirect_stdout(log), patch.object(sys, "argv", args), patch.object(capture, "prepare", return_value=("device", None)):
            self.assertEqual(capture.main(), 0, log.getvalue())
        self.assertIn(".listing-kit/raw/handset/en-US/map.png", log.getvalue())

    def test_archive_cannot_be_moved_as_stale_art(self):
        archive = "fastlane/metadata/android/en-US/images/previous"
        self.plan["targets"][0]["rawPattern"] = archive + "/{screen}.png"
        self.save()
        path = self.root / archive / "map.png"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"archived")
        (self.config / "outputs.json").write_text(json.dumps(dict(format=1, files=[archive + "/map.png"])))
        self.assertIn("capture input", self.cli("plan", "check", rc=1))

    def test_graphic_alignment(self):
        self.plan["graphics"]["play"]["featureGraphic"]["align"] = "start"
        self.save()
        self.cli("compose", "--preview", rc=1)
        page = html.unescape((self.config / "preview.html").read_text())
        self.assertIn("--graphic-align:start", page)
        self.assertIn("text-align:var(--graphic-align", page)

    def test_graphic_spacing(self):
        self.plan["graphics"]["play"]["featureGraphic"]["gap"] = 2.5
        self.save()
        self.cli("compose", "--preview", rc=1)
        page = html.unescape((self.config / "preview.html").read_text())
        self.assertIn("--graphic-gap:2.5vmin", page)
        self.assertIn("gap:var(--graphic-gap", page)

    def test_console(self):
        self.plan["console"] = dict(playCategory="Education", contactEmail=None,
                                    playPrivacyUrl="https://example.test/privacy")
        self.save()
        (self.meta / "contact_website.txt").write_text("https://example.test/help")
        self.assertIn("01_map.png: MISSING", self.cli("handoff", rc=1))
        for name in ("INDEX.md", "INDEX.html"):
            guide = (self.config / "upload" / name).read_text()
            for value in ("Education", "https://example.test/privacy", "https://example.test/help",
                          "Contact email", "enter privately", "enter in Play Console"):
                self.assertIn(value, guide)
            self.assertNotIn("Run listing-kit publish first", guide)

    def test_receipt(self):
        files = {"metadata/en-US/title.txt": hashlib.sha256(b"Map Notes").hexdigest()}
        manifest = dict(files=files, galleries={})
        digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        identity = dict(app=self.plan["app"], selector="internal")
        done = dict(manifest, store="play", identity=identity, operation="one", status="done",
                    manifestHash=digest)
        pending_files = {"metadata/en-US/changelogs/12.txt": hashlib.sha256(b"New map").hexdigest()}
        pending_manifest = dict(files=pending_files, galleries={})
        pending_hash = hashlib.sha256(json.dumps(pending_manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        pending = dict(done, files=pending_files, manifestHash=pending_hash, operation="two", status="pending")
        receipt = dict(format=2, stores=dict(play=dict(identity=identity, operations=[done, pending])))
        (self.config / "publish.receipt.json").write_text(json.dumps(receipt))
        self.assertIn("01_map.png: MISSING", self.cli("handoff", rc=1))
        index = (self.config / "upload/INDEX.md").read_text()
        self.assertIn("metadata/en-US/title.txt", index)
        self.assertIn("internal", index)
        self.assertNotIn("changelogs/12.txt", index)

    def test_descriptions(self):
        self.plan["locales"].append("fr-FR")
        self.plan["graphics"]["play"]["icon"] = {"from": "art/icon.png"}
        self.plan["screens"][0]["altText"] = {"en-US": "River & hills", "fr-FR": "Fleuve et collines"}
        self.plan["graphics"]["play"]["featureGraphic"]["altText"] = {"en-US": "Map overview"}
        self.save()
        outputs = json.loads(self.cli("plan", "manifest"))["outputs"]
        for row in outputs:
            path = self.root / row["outputPath"]
            path.parent.mkdir(parents=True, exist_ok=True)
            w, h = row["size"]
            def chunk(kind, data):
                return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
            path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w,h,8,2,0,0,0))
                             + chunk(b"IDAT", zlib.compress(bytes(h*(1+3*w)))) + chunk(b"IEND", b""))
        (self.root / ".gitignore").write_text(".listing-kit/local.json\n")
        (self.config / "local.json").write_text("{}")
        self.cli("review")
        images = Images((self.root / "listing-review.html").read_text()).images
        self.cli("handoff")
        for row in outputs:
            if row["slotId"] == "icon":
                self.assertIn("icon", images[row["outputPath"]].lower())
            expected = row["text"].get("altText", {}).get("value")
            if expected:
                self.assertEqual(images[row["outputPath"]], expected)
                for name in ("INDEX.md", "INDEX.html"):
                    lines = html.unescape((self.config / "upload" / name).read_text()).splitlines()
                    self.assertTrue(any(expected in line and ".png" in line and row["storeCode"] in line
                                        for line in lines), expected)


if __name__ == "__main__":
    unittest.main()
