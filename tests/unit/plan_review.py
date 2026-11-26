"""Regression cases for the listing plan and its effective store rules."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import plan
import specs


class PlanReview(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name).resolve()
        self.app = self.repo / "apps" / "demo"
        self.file = self.app / plan.LISTING
        self.file.parent.mkdir(parents=True)
        (self.app / ".listing-kit/flows").mkdir()
        (self.app / ".listing-kit/flows/one.yaml").touch()
        self.rules = specs.load()
        self.target = dict(id="phone", state="active", store="play", slot="phone", size=[1080, 1920])
        self.data = dict(format=2, app={"id": "test"}, locales=["en-US"],
                         targets=[self.target], screens=[dict(id=x, flow=".listing-kit/flows/one.yaml") for x in ("a", "b")])
        self.file.write_text(json.dumps(self.data))

    def problems(self):
        return plan.check(self.data, self.rules, self.app)

    def errors(self):
        return [msg for level, path, msg in self.problems() if level == "ERROR"]

    def cli(self, command):
        env = dict(os.environ, PYTHONIOENCODING="utf-8:strict")
        return subprocess.run([sys.executable, plan.__file__, command, str(self.app)],
                              capture_output=True, text=True, env=env)

    def override(self, slot):
        (self.app / specs.OVERRIDE).write_text(json.dumps(
            {"stores": {"play": {"screenshots": {"slots": [slot]}}}}))

    def test_malformed_effective_rules(self):
        for key, value in (("id", []), ("folder", ["bad"]), ("side", {"min": False}), ("min", False),
                           ("max", "8"), ("minSize", [1920]), ("maxRatio", "none"),
                           ("ratios", ["1:0"]), ("upload", "unknown"), ("framing", 0)):
            with self.subTest(key=key):
                self.override(dict({"id": "ten-inch"}, **{key: value}))
                with self.assertRaises(specs.SpecsError):
                    specs.load(self.app)
                result = self.cli("outputs")
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertNotIn("Traceback", result.stderr)

    def test_check_rejects_invalid_rules(self):
        specs.slot(self.rules, "apple", "ipad-13")["sizes"] = [42]
        self.assertTrue(specs.check(self.rules))
        self.assertTrue(self.errors())

    def test_plain_plan_helpers_share_rules(self):
        self.target.update(store="apple", slot="ipad-13", size=[2064, 2752])
        specs.slot(self.rules, "apple", "ipad-13")["suffix"] = "custom"
        self.assertEqual(self.problems(), [])
        name = plan.output_name(self.data, self.target, self.data["screens"][0], self.rules)
        self.assertEqual(name, "01_a_custom.png")
        self.assertEqual(Path(plan.manifest(self.data, self.rules, self.app)["outputs"][0]["outputPath"]).name, name)

    def test_helpers_reject_escaping_components(self):
        screen = dict(self.data["screens"][0], id="../screen")
        with self.assertRaises(plan.PlanError):
            plan.raw_path(self.target, screen, "en-US")
        with self.assertRaises(plan.PlanError):
            plan.raw_path(dict(self.target, id="outer/inner"), self.data["screens"][0], "en-US")
        self.target.update(store="apple", slot="ipad-13", size=[2064, 2752])
        specs.slot(self.rules, "apple", "ipad-13")["suffix"] = "../../bad"
        with self.assertRaises(plan.PlanError):
            plan.output_name(self.data, self.target, self.data["screens"][0], self.rules)

    def test_output_helpers_check_effective_rules(self):
        specs.slot(self.rules, "play", "phone")["folder"] = "/outside"
        with self.assertRaises(plan.PlanError):
            plan.output_name(self.data, self.target, self.data["screens"][0], self.rules)
        with self.assertRaises(plan.PlanError):
            plan.manifest(self.data, self.rules, self.app)

    def test_destination_collisions(self):
        other = dict(self.target, id="other")
        self.data["targets"].append(other)
        self.assertTrue(any("phone" in m and "other" in m and "01_a.png" in m for m in self.errors()))
        self.data["locales"].append({"id": "de", "apple": "de-DE", "play": "de"})
        self.target["locales"], other["locales"] = ["de"], ["en-US"]
        self.assertEqual(self.problems(), [])
        other["locales"] = ["de"]
        other["state"] = "retired"
        self.assertEqual(self.problems(), [])
        for target in self.data["targets"]:
            target.update(store="apple", slot="ipad-13", size=[2064, 2752], state="active")
        self.assertTrue(self.errors())
        other["upload"] = "console"
        self.assertEqual(self.problems(), [])
        rules = self.rules["stores"]["apple"]["graphics"]
        rules[1]["file"] = rules[0]["file"]
        self.data["graphics"] = {"apple": {g["id"]: {"headline": {"en-US": "Header"}} for g in rules}}
        self.assertIn("graphics.apple.header-16x9 and graphics.apple.header-21x9 both claim store-assets/apple/en-US/header-16x9.png", self.errors())

    def test_case_insensitive_rule_folder_collisions(self):
        slot = specs.slot(self.rules, "play", "phone")
        specs.slots(self.rules, "play").append(dict(slot, id="copy", folder=slot["folder"].upper()))
        self.data["targets"].append(dict(self.target, slot="copy", id="other"))
        self.assertTrue(self.errors())

    def test_output_symlinks(self):
        for relative in ("fastlane", "fastlane/metadata/android/en-US/images/phoneScreenshots",
                         "fastlane/metadata/android/en-US/images/phoneScreenshots/02_b.png",
                         ".listing-kit/raw/phone", "store-assets/apple/en-US/header-16x9.png"):
            with self.subTest(relative=relative):
                self.data["graphics"] = {"apple": {"header-16x9": {"headline": {"en-US": "Header"}}}}
                self.file.write_text(json.dumps(self.data))
                path = self.app / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(self.repo / "outside")
                r = self.cli("outputs")
                path.unlink()
                self.assertEqual((r.returncode, r.stdout), (1, ""))
                self.assertNotIn("Traceback", r.stderr)

    def test_input_paths(self):
        (self.repo / ".git").touch()
        (self.app / "escape").symlink_to(self.repo)
        (self.repo / "escape").symlink_to(self.repo.parent)
        self.data.update(style={"fonts": {"default": {}}}, graphics={"play": {"icon": {}}})
        font = self.data["style"]["fonts"]["default"]
        screen = self.data["screens"][0]
        screen["flows"] = {}
        for owner, key, good, bad in (
            (screen, "flow", "flows/test", "flows/../test"),
            (screen["flows"], "phone", "repo:flows/test", "repo:../flows/test"),
            (self.data["app"], "demoEntry", "entry.ts", "C:\\entry.ts"),
            (self.data["graphics"]["play"]["icon"], "from", "repo:brand/icon.png", "repo:../icon.png"),
            (self.data["style"], "logo", "repo:brand/logo.png", "repo:escape/logo"),
            (font, "headline", ["repo:brand/font", "bundled:Inter", "local.ttf"], ["bundled:../font"]),
        ):
            with self.subTest(key=key):
                self.data["graphics"]["play"]["icon"].setdefault("from", "icon.png")
                for value in (bad, ["/etc/font"] if owner is font else "escape/file"):
                    owner[key] = value
                    self.file.write_text(json.dumps(self.data))
                    with self.assertRaises(plan.PlanError):
                        plan.load(self.app)
                owner[key] = good
                self.file.write_text(json.dumps(self.data))
                plan.load(self.app)

    def test_graphic_overrides(self):
        for store, name in (("play", "featureGraphic"), ("apple", "header-16x9"), ("play", "icon")):
            with self.subTest(graphic=name):
                (self.app / "logo.png").touch()
                g = {"palette": {"ink": "#151719"}, "logo": "logo.png"}
                g.update({"from": "logo.png"} if name == "icon" else {"headline": {"en-US": "Title"}})
                self.data["graphics"] = {store: {name: g}}
                self.assertEqual(self.problems(), [])
                g["logo"] = "../logo"
                self.assertEqual(self.errors(), ["invalid file reference: expected a relative path without parent components"])
                g.update(logo="logo.png", palette=0)
                self.assertEqual(self.errors(), ["expected an object"])

    def test_play_bounds(self):
        cases = {"phone": ([[1080, 2400]], [[319, 500], [3841, 3841]]),
                 "wear": ([[384, 384], [3841, 3841]], [[383, 383], [384, 385]]),
                 "xr": ([[7680, 4800], [7696, 4810]], [[1600, 1000]]),
                 "automotive": ([[800,1280], [1024,768]], [[1280,800], [800,1279], [1600,2560]])}
        for name, (good, bad) in cases.items():
            for size in good + bad:
                with self.subTest(name=name, size=size):
                    self.assertEqual(plan._size_accepted(self.rules, "play", specs.slot(
                        self.rules, "play", name), size), size in good)

    def test_counts_and_empty_draft(self):
        self.data["screens"][0]["except"] = ["phone"]
        self.assertTrue(self.errors())
        self.data["screens"] = [dict(id=str(i), flow="f") for i in range(9)]
        self.assertTrue(self.errors())
        self.data["screens"] = []
        self.assertEqual(self.problems(), [("WARN", "targets[0]", "active target produces no screenshots"),
                                           ("WARN", "$", "nothing planned yet")])
        self.data.update(targets=[], screens=[dict(id="x", flow=".listing-kit/flows/one.yaml")])
        self.assertEqual(self.problems(), [("WARN", "$", "nothing planned yet"),
                                           ("WARN", "screens[0]", "screen applies to no active target")])

    def test_play_aggregate_minimum_by_locale(self):
        self.target.update(slot="wear", size=[384,384], locales=["en-US", "de"])
        self.data["locales"].append({"id": "de", "apple": "de-DE", "play": "de"})
        self.data["targets"].append(dict(self.target, id="tv", slot="tv", size=[1280,720], locales=["de"]))
        self.data["screens"].pop()
        self.assertTrue(any("en-US" in m for m in self.errors()))
        self.assertFalse(any(" de " in m for m in self.errors()))
        self.target["locales"] = ["de"]
        self.assertEqual(self.problems(), [])

    def test_raw_only_panels(self):
        self.target.update(slot="wear", size=[384, 384])
        self.data["screens"].append(dict(id="end", panel=dict(headline={}, rows=[])))
        self.assertTrue(any("panel" in m for m in self.errors()))

    def test_portable_names(self):
        for obj, key, values in ((self.target, "id", ["a"*49, "con", "lpt9"]),
                                 (self.target, "suffix", ["A", "a"*49, "bad?", "com1"]),
                                 (self.data["screens"][0], "id", ["a"*49, "aux"]),
                                 (self.data, "locales", [["en-US", "en-us"], ["D:de"], ["nul"], ["EN"]])):
            for value in values:
                with self.subTest(key=key, value=value):
                    before = obj.get(key)
                    obj[key] = value
                    self.assertTrue(self.errors())
                    if before is None:
                        del obj[key]
                    else:
                        obj[key] = before

    def test_version_and_store_identity(self):
        for version in (0, -1, True, 1.0, 3):
            with self.subTest(version=version):
                self.data["format"] = version
                self.assertTrue(self.errors())
        self.data.update(format=2, app=dict(ios="only.ios"))
        self.assertTrue(self.errors())
        self.target["state"] = "retired"
        self.assertFalse(self.errors())

    def test_non_json_api_values(self):
        nested = []
        for _ in range(1100):
            nested = [nested]
        for value in ({3:1}, {"x":1, 3:1}, float("nan"), float("inf"), 10**5000, nested):
            with self.subTest(kind=type(value).__name__):
                self.data["notes"] = {"value":value}
                self.assertTrue(self.errors())

    def test_hostile_json_files(self):
        for payload in (b'{"targets":[],"targets":[]}', b'{"key":"\\ud800"}', b'{"\\ud800":1}',
                        b'['*1200 + b']'*1200, b'\xff',
                        *(json.dumps(dict(self.data, notes={"x":"MARK"})).encode().replace(b'"MARK"', x)
                          for x in (b'NaN', b'Infinity', b'-Infinity', b'1e999', b'9'*5000))):
            with self.subTest(payload=payload[:30]):
                self.file.write_bytes(payload)
                for command in ("check", "outputs"):
                    r = self.cli(command)
                    self.assertEqual(r.returncode, 1)
                    diagnostic, empty = (r.stdout, r.stderr) if command == "check" else (r.stderr, r.stdout)
                    self.assertEqual(empty, "")
                    self.assertTrue(diagnostic.startswith("ERROR\t"), diagnostic)
                    self.assertNotIn("Traceback", diagnostic)
        self.file.write_bytes(self.file.read_bytes().replace(b'9'*5000, b'1').replace(b'"format":', b'"format":1,"format":'))
        self.assertIn("duplicate", self.cli("check").stdout.lower())

    def test_app_relative_dot_prefix(self):
        self.data["screens"][0]["flow"] = "./.listing-kit/flows/one.yaml"
        self.assertEqual(self.problems(), [])

    def test_non_ascii_diagnostic_on_ascii_stream(self):
        self.file.write_text(json.dumps(dict(self.data, **{"日本語": 1})))
        result = subprocess.run([sys.executable, plan.__file__, "check", str(self.app)],
                                env=dict(os.environ, PYTHONIOENCODING="ascii:strict"),
                                capture_output=True)
        self.assertEqual((result.returncode, result.stderr), (1, b""))
        self.assertTrue(result.stdout.startswith(b"ERROR\t"))


if __name__ == "__main__":
    unittest.main()
