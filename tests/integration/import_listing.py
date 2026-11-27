import hashlib
import html
import io
from contextlib import redirect_stdout
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

KIT = Path(sys.argv.pop(1)).resolve()
sys.path.insert(0, str(KIT / "scripts/compose"))
import cdp  # noqa: E402
HAVE_BROWSER = bool(cdp.find_browser())


def png(width, height):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(height * (1 + 3 * width)))) + chunk(b"IEND", b""))


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
        prefix = "fastlane/metadata/android/en-US/images/"
        phone = prefix + "phoneScreenshots/03_legend.png"
        tablet = prefix + "tenInchScreenshots/03_legend.png"
        for flags, wanted in [(("--screen", "legend"), [phone, tablet]),
                              (("--screen", "legend", "--target", "slate"), [tablet])]:
            with self.subTest(flags=flags):
                self.cli("compose", "--preview", *flags)
                page = (self.config / "preview.html").read_text()
                self.assertCountEqual(re.findall(r"<figcaption>([^<]+)</figcaption>", page), wanted)
                self.assertEqual(page.count("<iframe "), len(wanted))
                out = self.cli("compose", "--dry-run", *flags)
                self.assertCountEqual(re.findall(r"^would write (.+)$", out, re.M), wanted)

    def test_clean_example_compose(self):
        example = self.root / "clean-example"
        shutil.copytree(KIT.parents[1] / "examples/expo-recipe-box", example)
        # Match the renderer OS recorded by the distributed example on every CI host.
        sys.path.insert(0, str(KIT / "scripts/compose"))
        import compose
        lock = example / ".listing-kit/compose.lock.json"
        before = lock.read_bytes()
        renderer_os, = {row["renderer"]["os"] for row in json.loads(before)["outputs"].values()
                        if row.get("renderer")}
        log = io.StringIO()
        with redirect_stdout(log), patch.object(sys, "platform", renderer_os):
            rc = compose.main([str(example)])
        self.assertEqual(rc, 0, log.getvalue())
        self.assertRegex(log.getvalue(), r"(?m)^compose: 0 written, [1-9]\d* unchanged, 0 held, 0 failed$")
        self.assertNotIn("--restyle", log.getvalue())
        self.assertEqual(before, lock.read_bytes())

    def test_plan_only_stores(self):
        shutil.rmtree(self.root / "fastlane")
        (self.root / "app.json").unlink()
        self.plan["targets"].append(dict(id="iphone", store="apple", slot="iphone-di-medium",
                                         size=[1206, 2622], state="active"))
        self.save()
        out = self.cli("detect")
        self.assertIn("stores\tapple play\n", out)
        self.assertIn("play.metadata\tfastlane/metadata/android", out)
        self.assertIn("apple.metadata\tfastlane/metadata", out)

    def test_play_screenshots_present_when_zero_planned(self):
        self.plan["screens"] = []
        self.save()
        path = self.meta / "en-US/images/phoneScreenshots/extra.png"
        path.parent.mkdir(parents=True)
        path.write_bytes(png(1080, 1920))
        self.assertIn("✗ planned Play en-US/phone: 1 of 0 screenshots", self.cli("validate", rc=1))

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
        self.assertRegex(out, r"(?m)^\s*! .*unversioned")
        self.assertRegex(out, r"[1-9][0-9]* warnings")
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
        data = png(1080, 1920)
        path.write_bytes(data)
        self.cli("compose", "--target", "handset", "--screen", "map", "--preview")
        self.assertIn("would write", self.cli("compose", "--target", "handset", "--screen", "map", "--dry-run"))
        self.assertEqual(path.read_bytes(), data)
        for invalid in ("../archive/{screen}.png", "/archive/{screen}.png", "archive/{other}.png"):
            self.plan["targets"][0]["rawPattern"] = invalid
            self.save()
            self.assertIn("rawPattern", self.cli("plan", "check", rc=1))

    def test_bad_archived_capture(self):
        target = self.plan["targets"][0]
        target["rawPattern"] = "archive/{screen}.png"
        path = self.root / "archive/map.png"
        path.parent.mkdir()
        for style, data in [("raw", b"archived"), ("raw", png(2, 2)), ("framed", png(2, 2)[:-4])]:
            target["style"] = {"mode": style}
            self.save()
            path.write_bytes(data)
            for flags in [("--preview",), ("--dry-run",), ()]:
                with self.subTest(style=style, flags=flags, size=len(data)):
                    # Without a browser a real framed compose stops earlier with exit 3,
                    # naming the same output, before it can inspect the capture.
                    blocked = style == "framed" and not flags and not HAVE_BROWSER
                    out = self.cli("compose", "--target", "handset", "--screen", "map", *flags,
                                   rc=3 if blocked else 1)
                    self.assertIn("01_map.png", out)
                    self.assertNotIn("would write", out)
                    if flags == ("--preview",):
                        page = (self.config / "preview.html").read_text()
                        self.assertIn("archive/map.png", page)
                        self.assertNotIn("<iframe ", page)

    def test_expanded_raw_pattern_internals(self):
        target, screen = self.plan["targets"][0], self.plan["screens"][0]
        for field, name in [("target", "git"), ("screen", "listing-kit")]:
            target["id"], screen["id"] = "handset", "map"
            (target if field == "target" else screen)["id"] = name
            target["rawPattern"] = "archive/.{" + field + "}/{index}.png"
            self.save()
            with self.subTest(field=field):
                self.assertIn("rawPattern", self.cli("plan", "check", rc=1))

    def test_archived_status_bars(self):
        target = self.plan["targets"][0]
        target.update(store="apple", slot="iphone-di-medium", size=[1206, 2622],
                      rawPattern="archive/{screen}.png")
        self.save()
        path = self.root / "archive/map.png"
        path.parent.mkdir()
        path.write_bytes(png(2, 2))
        (self.root / ".gitignore").write_text(".listing-kit/local.json\n")
        (self.config / "local.json").write_text("{}")
        (self.root / "fastlane/metadata/en-US").mkdir()
        (self.root / "fastlane/metadata/en-US/name.txt").write_text("Map Notes")
        self.cli("review")
        page = (self.root / "listing-review.html").read_text()
        self.assertIn("archive/map.png", Images(page).images)
        self.assertIn("Inspect raw status bars", page)
        (self.root / "listing-review.html").unlink()
        self.cli("hook", "install")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        path.unlink()  # The hook must read the indexed capture.
        (path.parent / "lakes.png").write_bytes(png(2, 2))
        subprocess.run(["bash", ".git/hooks/pre-commit"], cwd=self.root, check=True)
        staged = subprocess.check_output(["git", "show", ":listing-review.html"], cwd=self.root, text=True)
        self.assertIn("archive/map.png", Images(staged).images)
        self.assertNotIn("archive/lakes.png", Images(staged).images)

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
        fields = {"playCategory": ("category.txt", "Education"),
                  "contactEmail": ("contact_email.txt", "publisher@example.test"),
                  "playPrivacyUrl": ("privacy_url.txt", "https://example.test/privacy"),
                  "contactWebsite": ("contact_website.txt", "https://example.test/help")}
        for source in ("plan", "metadata"):
            with self.subTest(source=source):
                self.plan["console"] = {key: value for key, (_, value) in fields.items()} if source == "plan" else {}
                self.save()
                if source == "metadata":
                    for filename, value in fields.values():
                        (self.meta / filename).write_text(value)
                handoff = self.cli("handoff", rc=1)
                self.assertIn("01_map.png: MISSING", handoff)
                validate = self.cli("validate", rc=1) + self.cli("validate", "--verbose", rc=1)
                for _, value in fields.values():
                    self.assertNotIn(value, handoff + validate)
                    for filename in ("INDEX.md", "INDEX.html"):
                        guide = html.unescape((self.config / "upload" / filename).read_text())
                        self.assertTrue(any(value in line and "public on your store page" in line
                                            for line in guide.splitlines()), filename)
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
            path.write_bytes(png(w, h))
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
