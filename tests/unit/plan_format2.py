"""Format 2 contract and regressions from the second plan review."""
import copy
import datetime
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import plan
import specs

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class FormatTwo(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name).resolve()
        self.app = self.repo / "apps/demo"
        self.flow = ".listing-kit/flows/open.yaml"
        (self.app / self.flow).parent.mkdir(parents=True)
        (self.app / self.flow).touch()
        self.rules = specs.load()
        self.target = dict(id="phone", store="play", slot="phone", size=[1080, 1920], state="active")
        self.data = dict(format=2, app={"id": "test"}, locales=["en-US"], targets=[self.target],
                         screens=[dict(id=i, flow=self.flow) for i in ("one", "two")])

    def check(self, **kwargs):
        return plan.check(self.data, self.rules, self.app, **kwargs)

    def manifest(self):
        return plan.manifest(self.data, self.rules, self.app)

    def test_requirement_replacement_and_null_deletion(self):
        update = dict(id="iphone-duo-outer", required={"rule": "always"}, capture=None)
        (self.app / specs.OVERRIDE).write_text(json.dumps(
            {"stores": {"apple": {"screenshots": {"slots": [update]}}}}))
        slot = specs.slot(specs.load(self.app), "apple", update["id"])
        self.assertEqual(slot["required"], {"rule": "always"})
        self.assertNotIn("capture", slot)

    def test_all_repo_inputs_and_scan_inventory(self):
        (self.repo / ".git").write_text("gitdir: elsewhere")
        common = self.repo / "shared"
        common.touch()
        ref = "repo:shared"
        self.data["app"]["demoEntry"] = ref
        self.data["style"] = dict(logo=ref, fonts={"default": {"headline": [ref, "bundled:Inter"]}})
        self.data["screens"][0].update(flow=ref, flows={"phone": ref})
        self.data["graphics"] = {"play": {"icon": {"from": ref}}}
        with patch.object(subprocess, "run", side_effect=AssertionError("invoked a subprocess")):
            self.assertEqual(self.check(), [
                ("WARN", "screens[0].flow", "flow is outside .listing-kit/flows"),
                ("WARN", "screens[0].flows.phone", "flow is outside .listing-kit/flows")])
            self.assertEqual(set(plan.input_files(self.data, self.rules, self.app)),
                             {common, self.app / self.flow, self.app / plan.LISTING, self.app / specs.OVERRIDE,
                              Path(plan.__file__).resolve().parents[2] / "assets/fonts/Inter.ttf"})
        dest = "fastlane/metadata/android/en-US/images/icon.png"
        self.data["graphics"]["play"]["icon"]["from"] = dest
        self.assertIn(("ERROR", "graphics.play.icon.from", "source is a planned output: " + dest), self.check())

    def test_no_repo_marker(self):
        self.data["style"] = {"logo": "repo:shared"}
        # Emulate a plain extracted copy even if TMPDIR is inside a checkout.
        is_file, is_dir = Path.is_file, Path.is_dir
        with patch.object(Path, "is_file", lambda p: p.name != ".git" and is_file(p)), \
             patch.object(Path, "is_dir", lambda p: p.name != ".git" and is_dir(p)):
            self.assertEqual(self.check(), [
                ("ERROR", "style.logo", "invalid file reference: repo: requires a .git ancestor")])
        for marker in (self.repo / ".git", self.app.parent / ".git"):
            marker.mkdir()
        (self.app.parent / "shared").touch()
        self.assertEqual(self.check(), [])

    def test_slot_totals_and_play_suffix(self):
        self.data["targets"].append(dict(self.target, id="landscape", suffix="landscape"))
        self.assertEqual(self.manifest()["outputs"][2]["outputPath"].split("/")[-1], "01_one_landscape.png")
        self.data["screens"] += [dict(id=i, flow=self.flow) for i in ("a", "b", "c")]
        self.assertEqual(self.check(), [("ERROR", "targets[0]", "phone requires 2 to 8 screens for en-US; found 10")])

    def test_port_decisions(self):
        source = FIXTURES / "shellbell"
        new, old = [json.loads((source / f).read_text()) for f in ("listing.new.json", "listing.json")]
        self.assertEqual(new["approved"], {"metadata": True, "screens": True})
        for target, original in zip(new["targets"], old["targets"]):
            self.assertEqual(target.get("status"), original.get("status"))
        for name, header in new["graphics"]["apple"].items():
            self.assertEqual(header["template"], "shellbell-" + name)
            self.assertEqual(header["status"], old["appleHeaders"]["status"])
        self.assertEqual(new["graphics"]["play"]["featureGraphic"]["status"], old["featureGraphic"]["status"])
        self.assertEqual(new["graphics"]["play"]["icon"]["from"], "repo:brand/android/play-store-512.png")
        md = old["metadata"]
        self.assertEqual(new["console"]["playCategory"], md["playCategory"])
        self.assertEqual(new["console"]["playPrivacyUrl"], md["privacyUrl"])
        for key, file in (("marketingUrl", "en-US/marketing_url"), ("supportUrl", "en-US/support_url"),
                          ("privacyUrl", "en-US/privacy_url"), ("copyright", "copyright"),
                          ("appleCategory", "primary_category")):
            self.assertEqual((source / "fastlane/metadata" / (file + ".txt")).read_text().strip(), md[key])

    def test_missing_flow_stages(self):
        self.data["screens"][0]["flow"] = "flows/missing.yaml"
        expected = [("WARN", "screens[0].flow", "flow is outside .listing-kit/flows"),
                    ("WARN", "screens[0].flow", "missing input file: flows/missing.yaml")]
        self.assertEqual(self.check(), expected)
        self.assertEqual(self.check(purpose="capture"), [expected[0], ("ERROR", *expected[1][1:])])

    def test_empty_outputs(self):
        self.target.update(slot="seven-inch", size=[1920, 1080])
        self.data["screens"] = [dict(id="orphan", only=[], flow=self.flow)]
        self.assertIn(("WARN", "targets[0]", "active target produces no screenshots"), self.check())
        self.assertIn(("WARN", "screens[0]", "screen applies to no active target"), self.check())
        self.target["state"] = "retired"
        self.assertIn(("WARN", "$", "no active targets"), self.check())

    def test_tree_symlink(self):
        (self.app / "ios/fastlane").mkdir(parents=True)
        (self.app / "fastlane").symlink_to("ios/fastlane")
        self.assertEqual(self.check(), [])
        self.assertEqual(len(self.manifest()["outputs"]), 2)

    def test_conflicting_rules(self):
        slots = specs.slots(self.rules, "play")
        tv = specs.slot(self.rules, "play", "tv")
        tv.update(ratio="16:9", ratios=["1:1"], sizes=[])
        tv["required"]["unless"] = "typo"
        path = "stores.play.screenshots.slots[%d]" % slots.index(tv)
        self.assertCountEqual(specs.check(self.rules), [
            ("ERROR", path + ".ratios", "ratio and ratios cannot both be set"),
            ("ERROR", path + ".sizes", "expected at least one size"),
            ("ERROR", path + ".required.unless", "unknown condition 'typo'")])

    def test_sourced_bounds_and_automotive(self):
        self.assertEqual(specs.slot(self.rules, "apple", "vision-pro")["lifecycle"], "console-only")
        self.assertNotIn("ratio", specs.slot(self.rules, "play", "tv"))
        self.assertNotIn("max", specs.slot(self.rules, "play", "wear").get("side", {}))
        self.assertNotIn("max", specs.slot(self.rules, "play", "xr").get("side", {}))
        self.target.update(slot="automotive", size=[800, 1280])
        self.assertEqual(self.check(), [("ERROR", "targets[0]", "automotive requires 2 screens at 1024x768 for en-US; found 0")])
        self.data["targets"].append(dict(self.target, id="car-wide", size=[1024, 768], suffix="wide"))
        self.assertEqual(self.check(), [])

    def test_tv_vision_filename(self):
        classify = lambda p: specs.apple_slot_for_file(self.rules, 3840, 2160, p)["id"]
        self.assertEqual(classify("en-US/appleTV/01_television_tv.png"), "apple-tv")
        self.assertEqual(classify("en-US/01_vision.png"), "vision-pro")

    def test_explicit_root_unknown_unless_and_fonts(self):
        with self.assertRaises(TypeError):
            plan.check(self.data, self.rules)
        rule = specs.slot(self.rules, "apple", "iphone-duo-outer")["required"]
        self.assertEqual(specs.requirement(rule, {"supportsIphone": True}, datetime.date(2026, 1, 1)), ("optional", ""))
        self.data["style"] = {"fonts": {"de": {"headline": ["bundled:Other"]}}}
        self.assertEqual(self.check(), [("ERROR", "style.fonts.de", "unknown locale 'de'"),
                                        ("ERROR", "style.fonts.de.headline[0]", "unknown bundled font 'Other'")])

    def test_split_locale_manifest(self):
        self.data = json.loads((FIXTURES / "plan-split.json").read_text())
        rows = self.manifest()["outputs"]
        paths = [(r["localeId"], r["storeCode"], r["rawPath"], r["outputPath"]) for r in rows]
        self.assertIn(("zh", "zh-Hans", ".listing-kit/raw/iphone/en-US/one.png",
                       "ios/fastlane/screenshots/zh-Hans/01_one_iphone-medium.png"), paths)
        self.assertIn(("zh", "zh-CN", ".listing-kit/raw/phone/zh/one.png",
                       "android/fastlane/metadata/android/zh-CN/images/phoneScreenshots/01_one.png"), paths)
        self.assertFalse(any(r["store"] == "apple" and r["localeId"] == "play-only" for r in rows))
        self.assertTrue(all(r["textFallback"] for r in rows if r["localeId"] == "zh" and r["screenId"] == "one"))
        self.assertIn(("WARN", "screens[0].caption.zh", "missing translation; using en-US"), self.check())
        self.assertEqual({r["storeCode"] for r in rows if r["slotId"] == "header-16x9"}, {"en-US", "zh-Hans"})

    def test_publish_and_stale_after_reorder_or_retirement(self):
        rows = self.manifest()["outputs"]
        old = self.app / rows[0]["outputPath"]
        old.parent.mkdir(parents=True)
        old.touch()
        self.data["screens"].reverse()
        self.data["screens"][1]["draft"] = True
        for state in ("active", "deferred", "retired"):
            self.target.update(state=state, reason="waiting")
            self.assertEqual(self.manifest()["stale"], [rows[0]["outputPath"]])
            problems = self.check(purpose="publish")
            self.assertIn(("ERROR", "screens[1].draft", "draft cannot be published"), problems)
            self.assertIn(("ERROR", rows[0]["outputPath"], "stale output"), problems)

    def test_conditions_and_capture_types(self):
        self.data["platforms"] = {"hasWearOs": True}
        self.assertEqual(specs.conditions_from_plan(self.data, {"hasWearOs": False})["hasWearOs"], True)
        self.assertIn(("WARN", "targets", "missing required play slot wear"), self.check())
        self.data["platforms"] = {"typo": True}
        self.target["capture"] = dict(deviceType="watch", display="internal", orientation="portrait",
                                      nativeSize=[True, 2], runtime=5, appId=[])
        self.assertCountEqual(self.check(), [("ERROR", "platforms.typo", "unknown condition 'typo'"),
                                            ("ERROR", "targets[0].capture.nativeSize", "expected two positive integers"),
                                            ("ERROR", "targets[0].capture.runtime", "expected a non-empty string"),
                                            ("ERROR", "targets[0].capture.appId", "expected a non-empty string")])

    def test_manifest_and_tsv_cli(self):
        self.data["screens"][0].update(draft=True, flows={"play": self.flow})
        self.target["capture"] = {"runtime": "35", "nativeSize": [1080, 2400], "appId": "example.beta",
                                  "deviceType": "Pixel", "orientation": "portrait", "display": "internal"}
        self.data["style"] = {"mode": "framed", "template": "caption"}
        self.data["graphics"] = {"play": {"tvBanner": {"headline": {"en-US": "TV"}}}}
        self.data["trees"] = {"play": {"metadata": "localized/play"}}
        rules = self.rules["stores"]["play"]["graphics"]
        banner = next(g for g in rules if g["id"] == "tvBanner")
        (self.app / specs.OVERRIDE).write_text(json.dumps({"stores": {"play": {"graphics": [
            {"id": "tvBanner", "file": "banner-custom", "upload": "console"}]}}}))
        (self.app / plan.LISTING).write_text(json.dumps(self.data))

        def cli(*args):
            return subprocess.run([sys.executable, plan.__file__, *args, str(self.app)],
                                  capture_output=True, text=True)

        result = cli("manifest")
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        manifest = json.loads(result.stdout)
        first, _, last = manifest["outputs"]
        self.assertEqual(first, {"kind": "screenshot", "targetId": "phone", "screenId": "one",
                                 "localeId": "en-US", "storeCode": "en-US", "store": "play", "slotId": "phone",
                                 "index": 1, "size": [1080, 1920], "styleMode": "framed", "template": "caption",
                                 "flowPath": self.flow, "rawPath": ".listing-kit/raw/phone/en-US/one.png",
                                 "outputPath": "localized/play/en-US/images/phoneScreenshots/01_one.png",
                                 "upload": "fastlane", "draft": True, "textFallback": False})
        self.assertEqual((last["size"], last["outputPath"], last["upload"]),
                         (banner["size"], "store-assets/play/en-US/banner-custom.png", "console"))
        self.assertEqual([line.split("\t")[-1] for line in cli("outputs").stdout.splitlines()],
                         [r["outputPath"] for r in manifest["outputs"]])
        self.assertEqual(cli("check", "--for", "publish").stdout, "ERROR\tscreens[0].draft\tdraft cannot be published\n")
        (self.app / self.flow).unlink()
        self.assertEqual(cli("check", "--for", "capture").returncode, 1)

    def test_store_mapping_and_translation_helpers(self):
        self.data["locales"] = [{"id": "english", "apple": None, "play": "en-US"}]
        self.assertEqual(self.check(), [])
        self.assertEqual(plan.text({"english": "Hello"}, "other", self.data["locales"]), ("Hello", True))
        for key, value, message in (("apple", "xx", "unknown Apple locale 'xx'"),
                                    ("play", "en/US", "expected a portable locale code")):
            with self.subTest(store=key):
                self.data["locales"] = [{"id": "loc", key: value}]
                self.assertEqual(self.check(), [("ERROR", "locales[0]." + key, message)])

    def test_bundled_inter_exists(self):
        self.data["style"] = {"fonts": {"default": {"headline": ["bundled:Inter"]}}}
        bundled = Path(plan.__file__).resolve().parents[2] / "assets/fonts/Inter.ttf"
        self.assertIn(bundled, plan.input_files(self.data, self.rules, self.app))
        self.assertEqual(bundled.read_bytes()[:4], b"\x00\x01\x00\x00")

    def test_stale_symlink_to_current_file(self):
        row = self.manifest()["outputs"][0]
        current = self.app / row["outputPath"]
        current.parent.mkdir(parents=True)
        current.touch()
        stale = current.parent / "02_retired.png"
        stale.symlink_to(current.name)
        self.assertEqual(self.manifest()["stale"], [stale.relative_to(self.app).as_posix()])

    def test_planned_apple_slot_aggregate(self):
        self.target.update(store="apple", slot="iphone-di-medium", size=[1206, 2622])
        self.data["targets"].append(dict(self.target, id="wide", size=[2622, 1206], suffix="wide"))
        self.data["screens"] = [dict(id=f"s{i}", flow=self.flow) for i in range(6)]
        self.assertEqual(self.check(), [("ERROR", "targets[0]", "iphone-di-medium requires 1 to 10 screens for en-US; found 12")])
        self.data["targets"][1]["upload"] = "console"
        self.assertEqual(self.check(), [])

    def test_platform_helper_detects_and_overrides(self):
        self.assertEqual(specs.conditions_from_plan(self.data), {"supportsAndroidPhone": True})
        self.data["platforms"] = {"supportsAndroidPhone": False}
        self.assertEqual(specs.conditions_from_plan(self.data), {"supportsAndroidPhone": False})

    def test_vision_fastlane_route_matches_filename(self):
        self.target.update(store="apple", slot="vision-pro", size=[3840, 2160], upload="fastlane", suffix="headset")
        self.assertEqual(self.check(), [
            ("ERROR", "phone/one", "Apple upload path selects apple-tv instead of vision-pro"),
            ("ERROR", "phone/two", "Apple upload path selects apple-tv instead of vision-pro")])
        del self.target["suffix"]
        self.assertEqual(self.check(), [])

    def test_public_tsv_view(self):
        rows = list(plan.outputs(self.data, self.rules, self.app))
        self.assertEqual([r[3] for r in rows], [r["outputPath"] for r in self.manifest()["outputs"]])

    def test_stale_graphic_in_apple_metadata(self):
        locale = self.app / "fastlane/metadata/en-US"
        locale.mkdir(parents=True)
        (locale / "old-header.png").touch()
        (locale / "description.txt").touch()
        self.assertEqual(self.manifest()["stale"], ["fastlane/metadata/en-US/old-header.png"])

    def test_stale_nonportable_filename_is_reported(self):
        folder = self.app / "fastlane/screenshots/en-US"
        folder.mkdir(parents=True)
        (folder / "old:screen.png").touch()
        self.assertEqual(self.manifest()["stale"], ["fastlane/screenshots/en-US/old:screen.png"])

    def test_control_safe_diagnostics(self):
        self.assertEqual(plan._line(("ERROR", "x\x1b\u2028", "bad")), "ERROR\tx\\x1b\\u2028\tbad")


if __name__ == "__main__":
    unittest.main()
