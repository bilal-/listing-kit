"""Exercise app-owned templates at the launcher, including plan and ownership diagnostics."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

KIT = Path(__file__).resolve().parents[2] / "skills/listing-kit"
sys.path.insert(0, str(KIT / "scripts/compose"))
from compose_regressions import png
import compose
import plan
import specs

HTML = """<!doctype html>
<html lang="{{lang}}" dir="{{dir}}">
<link rel="stylesheet" href="/base.css">
<link rel="stylesheet" href="/fonts.css">
<body><h1 class="headline" data-check="text">{{caption}}</h1>
<p class="detail" data-check="text">{{detail}}</p>
<img class="shot" data-check="device" src="/raw.png" alt="">
<img src="stamp.png" alt="private-template-markup">
"""
CSS = ".shot {width: 60%; height: 55%; object-fit: contain}\n"


class UserTemplates(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / ".git").mkdir()  # Bound plan discovery to this fixture.
        self.folder = self.root / ".listing-kit/templates"
        self.folder.mkdir(parents=True)
        self.plan = self.folder.parent / "listing.json"
        self.data = dict(format=2, app="example.app", locales=["en-US"],
                         style=dict(template="acorn", mode="framed",
                                    palette=dict(background=["#ffffff"], ink="#111111"),
                                    fonts=dict(default=dict(headline=["bundled:Inter"], detail=["bundled:Inter"]))),
                         targets=[dict(id="phone", store="play", slot="phone", size=[360, 640], state="active")],
                         screens=[dict(id="home", flow="home.yaml", caption={"en-US": "Today"}),
                                  dict(id="extra", flow="home.yaml", style={"mode": "raw"})])
        self.save()
        (self.folder / "acorn.html").write_text(HTML)
        (self.folder / "acorn.css").write_text(CSS)
        (self.folder / "stamp.png").write_bytes(png())
        raw = self.folder.parent / "raw/phone/en-US/home.png"
        raw.parent.mkdir(parents=True)
        raw.write_bytes(png(3, 5))
        raw.with_name("extra.png").write_bytes(png(360, 640))
        (self.root / "home.yaml").touch()

    def save(self):
        self.plan.write_text(json.dumps(self.data, indent=2))

    def cli(self, *args, rc=0, **env):
        result = subprocess.run([str(KIT / "bin/listing-kit"), *args], cwd=self.root, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=dict(os.environ, GIT_CEILING_DIRECTORIES=str(self.root.parent), **env))
        self.assertEqual(result.returncode, rc, result.stdout)
        return result.stdout

    def test_resolution(self):
        self.cli("plan", "check")
        (self.folder / "band.html").write_text("<script></script>")
        self.data["targets"][0]["template"] = "band"
        self.save()
        self.assertEqual(json.loads(self.cli("plan", "manifest"))["outputs"][0]["template"], "band")
        self.data["screens"][0]["template"] = "user:band"
        self.save()
        self.assertIn("band.html:1", self.cli("plan", "check", rc=1))
        for name in ("user:../band", "a/b", "user:A", "user:", "absent"):
            with self.subTest(name=name):
                self.data["screens"][0]["template"] = name
                self.save()
                line = next(i for i, s in enumerate(self.plan.read_text().splitlines(), 1) if json.dumps(name) in s)
                self.assertIn(f"listing.json:{line}", self.cli("plan", "check", rc=1))

    def test_starter(self):
        self.cli("template", "new", "con")
        self.data["style"]["template"] = "con"
        self.save()
        self.cli("plan", "check")
        self.cli("template", "new", "mint")
        path = self.folder / "mint.html"
        self.assertIn("<!--", path.read_text())
        path.write_text("keep")
        self.cli("template", "new", "mint", rc=1)
        self.assertEqual(path.read_text(), "keep")
        self.cli("template", "new", "../outside", rc=1)
        self.assertFalse((self.folder.parent / "outside.html").exists())

    def test_invalid_markup(self):
        page = self.folder / "acorn.html"
        for markup in ('<script>1</script>', '<img onerror="1">', '<img src="javascript:alert(1)">',
                       '<img src="data:image/svg+xml,script">', '<img src="http://example.invalid/a.png">', '<iframe srcdoc="hello"></iframe>',
                       '<link rel="dns-prefetch" href="//example.invalid">', '<img src="/etc/passwd">',
                       '<img src="file:///outside.png">', '<img src="missing.png">', '<link rel>'):
            with self.subTest(markup=markup):
                page.write_text("\n\n" + markup)
                self.assertIn("acorn.html:3", self.cli("plan", "check", rc=1))

    def test_lines_in_multiline_markup_and_css(self):
        page = self.folder / "acorn.html"
        page.write_text('<img alt="two\nlines"\n onload="go()">')
        self.assertIn("acorn.html:3", self.cli("plan", "check", rc=1))
        page.write_text('<style>\n.brand{background-image:image-set("https://example.invalid/x" 1x)}\n</style>')
        self.assertIn("acorn.html:2", self.cli("plan", "check", rc=1))
        page.write_text('<style>.brand{content:"unfinished\n; background:url(https://example.invalid/x)}/* " */</style>')
        self.assertIn("acorn.html:1", self.cli("plan", "check", rc=1))

    def test_preview_and_check_report_both_denials_before_browser(self):
        (self.root / "outside.png").write_bytes(png())
        (self.folder / "acorn.html").write_text('<img src="https://example.invalid/x">\n<img src="../../outside.png">')
        for args, rc in [(("plan", "check"), 1), (("compose", "--preview"), 2), (("compose",), 2)]:
            output = self.cli(*args, rc=rc, LK_BROWSER=str(self.root / "must-not-launch"))
            for i, ref in enumerate(("https://example.invalid/x", "../../outside.png"), 1):
                self.assertIn(f"acorn.html:{i}", output)
                self.assertIn(ref, output)
        self.assertFalse((self.folder.parent / "preview.html").exists())

    def test_css_assets_and_symlinks(self):
        css = self.folder / "acorn.css"
        css.write_text('/* palette */\nbody{background:url("absent.png")}')
        self.assertIn("acorn.css:2", self.cli("plan", "check", rc=1))
        css.write_text(CSS)
        for name in ("stamp.png", "acorn.css", "acorn.html"):
            with self.subTest(name=name):
                src = self.folder / name
                dest = self.root / name
                src.rename(dest)
                src.symlink_to(dest)
                self.assertIn(name, self.cli("plan", "check", rc=1))
                src.unlink()
                dest.rename(src)
        moved = self.root / "elsewhere"
        self.folder.rename(moved)
        self.folder.symlink_to(moved, target_is_directory=True)
        self.cli("plan", "check", rc=1)
        self.cli("template", "new", "escape", rc=1)
        self.assertFalse((moved / "escape.html").exists())

    def test_vector_and_font_inputs_in_plan_inventory(self):
        assets = self.folder / "art"
        assets.mkdir()
        svg = assets / "brand mark.svg"
        svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">\n'
                       '<path d="M0 0L10 10" stroke="black"/></svg>')
        css = assets / "brand.css"
        css.write_text('@font-face{font-family:Mark;src:url("bundled:fonts/Inter.ttf")}\n'
                       '.brand{background-image:url("./brand%20mark.svg")}')
        page = self.folder / "acorn.html"
        page.write_text(HTML + '<link rel="stylesheet" href="art/brand.css">')
        self.cli("plan", "check")
        inputs = plan.input_files(self.data, specs.load(self.root), self.root)
        for path in (svg, css, page, self.folder / "acorn.css", self.folder / "stamp.png"):
            self.assertIn(path, inputs)
        for bad in ('<script/>', '<image href="file:///elsewhere"/>', '<rect onclick="go()"/>',
                    '<path fill="url(https://example.invalid/a)"/>'):
            with self.subTest(bad=bad):
                svg.write_text('<svg xmlns="http://www.w3.org/2000/svg">\n' + bad + '</svg>')
                self.assertIn("brand mark.svg:2", self.cli("plan", "check", rc=1))

    def test_custom_panel_keys_include_exposed_frame_style(self):
        self.data["screens"].append(dict(id="last", flow="home.yaml"))
        self.data["screens"][0] = dict(id="home", panel=dict(headline={"en-US": "Today"}, rows=[]))
        (self.folder / "acorn.html").write_text('<body data-fit="{{fit}}"><h1 data-check="text">{{headline}}</h1>')
        record = plan.manifest(self.data, specs.load(self.root), self.root)["outputs"][0]
        original = compose.Job(self.root, record).keys()
        for setting in ({"fit": "cover"}, {"bezel": {"width": 5}}):
            changed = dict(record, style=dict(record["style"], **setting))
            content, style = compose.Job(self.root, changed).keys()
            self.assertEqual(content, original[0])
            self.assertNotEqual(style, original[1])

    def test_nested_asset_symlinks_and_nonregular_template(self):
        page = self.folder / "acorn.html"
        page.write_text('<img src="art/stamp.png">')
        elsewhere = self.root / "other"
        elsewhere.mkdir()
        (elsewhere / "stamp.png").write_bytes(png())
        (self.folder / "art").symlink_to(elsewhere, target_is_directory=True)
        self.assertIn("acorn.html:1", self.cli("plan", "check", rc=1))
        page.unlink()
        os.mkfifo(page)
        self.assertIn("regular file", self.cli("plan", "check", rc=1))

    @unittest.skipUnless(compose.render.cdp.find_browser() and compose.magick() or os.getenv("LK_REQUIRE_RENDER") == "1",
                         "render tools unavailable")
    def test_render_restyle_preview_and_clipping(self):
        self.cli("compose", "--screen", "home")
        dest, = self.root.glob("**/phoneScreenshots/*.png")
        self.assertEqual(compose.imginfo.image_info(str(dest)), (360, 640, 8, 2))
        self.assertIn("1 unchanged", self.cli("compose", "--screen", "home"))
        self.cli("compose", "--preview")
        preview = (self.folder.parent / "preview.html").read_text()
        self.assertIn("data:image/png;base64," + base64.b64encode(dest.read_bytes()).decode(), preview)
        self.assertNotIn("private-template-markup", preview)
        # Each input changes independently, including an image used only via CSS.
        for name, extra in [("acorn.html", b"<!-- redraw -->"), ("acorn.css", b".decoration{background-image:url(tile.png)}")]:
            (self.folder / "tile.png").write_bytes(png())
            with (self.folder / name).open("ab") as f:
                f.write(extra)
            self.cli("compose", rc=4)
            self.cli("compose", "--restyle")
        (self.folder / "tile.png").write_bytes(png(2, 3))
        self.cli("compose", rc=4)
        self.cli("compose", "--restyle")
        self.assertIn("1 unchanged", self.cli("compose", "--screen", "home"))
        (self.folder / "acorn.css").write_text(".headline{height:1px;overflow:hidden}")
        self.assertIn("text does not fit", self.cli("compose", "--restyle", rc=1))

    @unittest.skipUnless(compose.render.cdp.find_browser() or os.getenv("LK_REQUIRE_RENDER") == "1", "no browser")
    def test_csp_blocks_page_scripts_independently_of_source_validation(self):
        row = plan.manifest(self.data, specs.load(self.root), self.root)["outputs"][0]
        job = compose.Job(self.root, row)
        assets = compose.render.page_assets(**job.asset_args())
        # Inject harmless sentinels after load checks to exercise the second boundary.
        assets["/index.html"] += b'<script>window.inlineRan=1</script><script src="/test.js"></script>'
        assets["/test.js"] = b"window.fileRan=1"
        browser, renderer = compose.render.open_browser()
        self.addCleanup(browser.close)
        with patch.object(browser, "send", wraps=browser.send) as commands:
            _, ran = renderer.render(assets, *row["size"], probe="Boolean(window.inlineRan || window.fileRan)")
        self.assertFalse(ran)
        headers = [header["value"] for call in commands.call_args_list if call.args[0] == "Fetch.fulfillRequest"
                   for header in call.args[1]["responseHeaders"] if header["name"] == "Content-Security-Policy"]
        self.assertTrue(headers)
        self.assertTrue(all("script-src 'none'" in policy for policy in headers))

    def test_reference_and_example(self):
        reference = (KIT / "references/templates.md").read_text()
        example = reference.split("```html\n", 1)[1].split("```", 1)[0]
        (self.folder / "acorn.html").write_text(example)
        self.cli("plan", "check")
        if compose.render.cdp.find_browser() and compose.magick():
            self.cli("compose", "--preview")
            self.cli("template", "new", "starter")
            self.data["style"]["template"] = "starter"
            self.save()
            self.cli("compose", "--preview")
        for doc in (KIT / "SKILL.md", KIT.parents[1] / "docs/GUIDE.md"):
            self.assertIn("templates.md", doc.read_text())


if __name__ == "__main__":
    unittest.main()
