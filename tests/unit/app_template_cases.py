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
                         style=dict(template="user:acorn", mode="framed",
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

    def cli(self, *args, rc=0, timeout=60, **env):
        result = subprocess.run([str(KIT / "bin/listing-kit"), *args], cwd=self.root, text=True, timeout=timeout,
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

    def test_explicit_opt_in(self):
        for name in ("acorn", "absent"):
            with self.subTest(name=name):
                self.data["style"]["template"] = name
                self.save()
                error = self.cli("plan", "check", rc=1)
                for bundled in compose.template_values.TEMPLATES:
                    self.assertIn(bundled, error)
                self.assertEqual("user:" + name in error, name == "acorn")

    def test_loader_work_bounds(self):
        page = self.folder / "acorn.html"
        with self.subTest("large identifier"):
            page.write_text("<style>" + "a" * 2_000_000 + "</style>")
            self.assertIn("byte", self.cli("plan", "check", rc=1, timeout=4))
        with self.subTest("identifier below the byte cap"):
            page.write_text("<style>" + "a" * 120_000 + "{color:red}</style>")
            self.cli("plan", "check", timeout=4)
        with self.subTest("many attributes"):
            page.write_text("<p" + " title" * 150_000 + ">")
            self.assertIn("attribute", self.cli("plan", "check", rc=1, timeout=4))

    def test_exhausted_budget_never_opens_an_asset(self):
        with patch("os.open", side_effect=AssertionError("opened file with negative budget")):
            with self.assertRaisesRegex(ValueError, "byte limit"):
                compose.read_regular(self.root, "home.yaml", -2)

    def test_template_asset_budget(self):
        loader = compose.user_templates
        for limit, value in (("MAX_ASSETS", 1), ("MAX_TEMPLATE_BYTES", len(HTML.encode()) + 4),
                             ("MAX_IMAGE_BYTES", 5), ("MAX_FONT_BYTES", 5)):
            with self.subTest(limit=limit), patch.object(loader, limit, value, create=True):
                (self.folder / "acorn.css").write_text('@font-face{src:url(sample.ttf)}')
                (self.folder / "sample.ttf").write_bytes(b"fixture")
                with self.assertRaisesRegex(ValueError, "limit|byte|too many"):
                    loader.resolve(self.root, "user:acorn")

    def test_multiple_templates_share_budget_and_deadline(self):
        self.data["screens"][0]["template"] = "user:second"
        (self.folder / "second.html").write_text(HTML)
        self.save()
        loader = compose.user_templates
        with patch.object(loader, "new_deadline", wraps=loader.new_deadline) as deadline:
            plan.compose_inputs(self.root)
            deadline.assert_called_once()
        with patch.object(loader, "MAX_PLAN_TEMPLATE_BYTES", len(HTML.encode()) * 2):
            with self.assertRaisesRegex(plan.PlanError, "byte limit"):
                plan.compose_inputs(self.root)

    def test_template_loading_deadline(self):
        for args, rc in ((("plan", "check"), 1), (("compose", "--dry-run"), 2)):
            with self.subTest(args=args):
                self.assertIn("template loading timed out", self.cli(*args, rc=rc, LK_BROWSER_TIMEOUT="1e-12"))

    def test_brand_confined_and_bounded(self):
        meta = self.root / "store"
        locale = meta / "en-US"
        locale.mkdir(parents=True)
        title = locale / "title.txt"
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        other = Path(outside.name)
        (other / title.name).write_text("other name")
        def name():
            return compose.listing_name(self.root, {"trees": {"play": {"metadata": "store"}}},
                                        {"store": "play", "storeCode": "en-US"})
        title.symlink_to(other / title.name)
        self.assertIsNone(name())
        title.unlink()
        locale.rmdir()
        locale.symlink_to(other)
        self.assertIsNone(name())
        locale.unlink()
        locale.mkdir()
        os.mkfifo(title)
        # Enforce a wall-clock bound even if a blocking reader is reintroduced.
        result = subprocess.run([sys.executable, "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); import compose; "
            "print(compose.listing_name('.', {'trees': {'play': {'metadata': 'store'}}}, {'store':'play'}))",
            str(KIT / "scripts/compose")], cwd=self.root, timeout=3, check=True, capture_output=True)
        self.assertEqual(result.stdout.strip(), b"None")
        title.unlink()
        title.write_text("x" * 4097)
        self.assertIsNone(name())
        title.write_text("x" * 4096)
        self.assertEqual(name(), "x" * 4096)

    def test_brand_uses_locale_alias_before_other_locales(self):
        meta = self.root / "metadata"
        for code, name in (("de-DE", "Deutsch"), ("en-US", "English")):
            (meta / code).mkdir(parents=True)
            (meta / code / "name.txt").write_text(name)
        (meta / "en-GB").symlink_to("en-US")
        self.assertEqual(compose.listing_name(self.root, {"trees": {"apple": {"metadata": "metadata"}}},
                                              {"store": "apple", "storeCode": "en-GB"}), "English")

    def test_plan_font_and_logo_size_limits(self):
        for key, name, size in (("fonts", "local.ttf", (8 << 20) + 1), ("logo", "logo.png", (16 << 20) + 1)):
            with self.subTest(asset=key):
                path = self.root / name
                with path.open("wb") as stream:
                    stream.truncate(size)
                self.data["style"].pop("fonts", None)
                self.data["style"][key] = {"default": {"headline": [name]}} if key == "fonts" else name
                self.save()
                man, templates, roots = plan.compose_inputs(self.root)
                row = man["outputs"][0]
                job = compose.Job(self.root, row, templates, roots)
                job.keys()
                args = job.asset_args()
                asset = args["fonts"]["headline"][0] if key == "fonts" else args["logo"]
                self.assertEqual(len(asset.data), size)
                with path.open("ab") as stream:
                    stream.truncate((64 << 20) + 1)
                with self.assertRaisesRegex(ValueError, "67108864 byte limit"):
                    compose.Job(self.root, row, templates, roots).keys()

    def test_template_font_size_limit(self):
        with (self.folder / "local.ttf").open("wb") as stream:
            stream.truncate((8 << 20) + 1)
        (self.folder / "acorn.css").write_text('@font-face{src:url(local.ttf)}')
        with self.assertRaisesRegex(ValueError, "8388608 byte limit"):
            compose.user_templates.resolve(self.root, "user:acorn")

    def test_render_rechecks_fingerprinted_inputs(self):
        font = self.root / "local.ttf"
        font.write_bytes((KIT / "assets/fonts/Inter.ttf").read_bytes())
        logo = self.root / "logo.png"
        logo.write_bytes(png())
        self.data["style"].update(logo="logo.png", fonts={"default": dict.fromkeys(
            ("headline", "detail"), ["local.ttf"])})
        self.save()
        man, templates, roots = plan.compose_inputs(self.root)
        row = man["outputs"][0]
        for path in (font, logo, self.root / row["rawPath"]):
            with self.subTest(path=path.name):
                job = compose.Job(self.root, row, templates, roots)
                job.keys()
                original = path.read_bytes()
                try:
                    replacement = self.root / "replacement"
                    replacement.write_bytes(original + b"changed")
                    replacement.replace(path)
                    with self.assertRaisesRegex(ValueError, "changed during"):
                        job.asset_args()
                    path.unlink()
                    path.symlink_to(self.folder / "stamp.png")
                    with self.assertRaises((ValueError, OSError)):
                        job.asset_args()
                finally:
                    path.unlink()
                    path.write_bytes(original)

    def test_repo_font_and_logo_use_the_validated_root(self):
        app = self.root / "app"
        app.mkdir()
        (self.root / ".listing-kit").rename(app / ".listing-kit")
        art = self.root / "art"
        art.mkdir()
        (art / "logo.png").write_bytes(png())
        (art / "font.ttf").write_bytes((KIT / "assets/fonts/Inter.ttf").read_bytes())
        self.data["style"].update(logo="repo:art/logo.png", fonts={"default": dict.fromkeys(
            ("headline", "detail"), ["repo:art/font.ttf"])})
        (app / ".listing-kit/listing.json").write_text(json.dumps(self.data))
        man, templates, roots = plan.compose_inputs(app)
        row = man["outputs"][0]
        job = compose.Job(app, row, templates, roots)
        job.keys()
        assets = compose.render.page_assets(**job.asset_args())
        self.assertEqual(assets["/logo.png"], png())
        self.assertEqual(assets["/fonts/detail-0.ttf"], (art / "font.ttf").read_bytes())
        moved = self.root / "moved"
        art.rename(moved)
        art.symlink_to(moved)
        with self.assertRaises((ValueError, OSError)):
            job.asset_args()

    def test_capture_dependency_for_each_output(self):
        self.data["screens"][1] = dict(id="panel", panel=dict(headline={"en-US": "Example"}, rows=[]))
        self.save()
        for markup in ('<img src="/raw.png">', '<style>body{background:url(/raw.png)}</style>'):
            with self.subTest(markup=markup):
                (self.folder / "acorn.html").write_text(markup)
                self.assertIn("/raw.png", self.cli("plan", "check", rc=1))

        self.data["screens"].pop()
        self.data["graphics"] = {"play": {"featureGraphic": {"template": "user:acorn", "headline": {"en-US": "Hello"}}}}
        self.save()
        self.assertIn("/raw.png", self.cli("plan", "check", rc=1))

    def test_placeholder_must_be_one_validated_token(self):
        (self.folder / "acorn.html").write_text("<p>{{cap<!-- note -->tion}}</p>")
        self.assertIn("placeholder", self.cli("plan", "check", rc=1))

    @unittest.skipUnless(compose.render.cdp.find_browser() or os.getenv("LK_REQUIRE_RENDER") == "1", "no browser")
    def test_computed_srgb_contrast(self):
        for color in ("color(srgb 1 1 1)", "color(srgb 1 1 1 / .5)", "rgba(255,255,255,.5)"):
            with self.subTest(color=color):
                (self.folder / "acorn.css").write_text(CSS + ".headline{color:" + color + "}")
                self.assertIn("contrast 1.00:1", self.cli("compose", "--screen", "home", rc=1))

    @unittest.skipUnless(compose.render.cdp.find_browser() or os.getenv("LK_REQUIRE_RENDER") == "1", "no browser")
    def test_probe_preserves_srgb_channels_at_low_alpha(self):
        browser, renderer = compose.render.open_browser()
        self.addCleanup(browser.close)
        page = b"""<p data-check="text" style="color:color(srgb .1 .2 .3 / .006)">A</p>
                   <p data-check="text" style="color:color(srgb .1 none .3 / none)">B</p>"""
        _, info = renderer.render({"/index.html": page}, 100, 100, probe=compose.render.PROBE + "(true)")
        self.assertEqual([box["rgba"] for box in info["text"]], [[26, 51, 77, .006], [26, 0, 77, 0]])

    def test_starter(self):
        self.cli("template", "new", "con")
        self.data["style"]["template"] = "user:con"
        self.save()
        self.cli("plan", "check")
        self.cli("template", "new", "mint")
        path = self.folder / "mint.html"
        self.assertIn("user:mint", path.read_text())
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
        self.save()
        man, templates, roots = plan.compose_inputs(self.root)
        record = man["outputs"][0]
        original = compose.Job(self.root, record, templates, roots).keys()
        for setting in ({"fit": "cover"}, {"bezel": {"width": 5}}):
            changed = dict(record, style=dict(record["style"], **setting))
            content, style = compose.Job(self.root, changed, templates, roots).keys()
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
        self.save()
        man, templates, roots = plan.compose_inputs(self.root)
        row = man["outputs"][0]
        job = compose.Job(self.root, row, templates, roots)
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
        self.assertTrue(all("form-action 'none'" in policy for policy in headers))
        self.assertTrue(all("script-src 'none'" in policy for policy in headers))

    def test_reference_and_example(self):
        reference = (KIT / "references/templates.md").read_text()
        example = reference.split("```html\n", 1)[1].split("```", 1)[0]
        (self.folder / "acorn.html").write_text(example)
        self.cli("plan", "check")
        if compose.render.cdp.find_browser() and compose.magick():
            self.cli("compose", "--preview")
            self.cli("template", "new", "starter")
            self.data["style"]["template"] = "user:starter"
            self.save()
            self.cli("compose", "--preview")
        for doc in (KIT / "SKILL.md", KIT.parents[1] / "docs/GUIDE.md"):
            self.assertIn("templates.md", doc.read_text())


if __name__ == "__main__":
    unittest.main()
