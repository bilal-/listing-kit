"""Format 2 contract and regressions from the second plan review."""
import datetime
import json
import os
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
        self.assertIn(("ERROR", "graphics.play.icon", dest + " conflicts with input " + dest), self.check())

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
        self.assertEqual(self.manifest()["outputs"][2]["outputPath"].split("/")[-1], "03_one_landscape.png")
        self.data["screens"] += [dict(id=i, flow=self.flow) for i in ("a", "b", "c")]
        self.assertEqual(self.check(), [("ERROR", "targets[0]", "phone requires 2 to 8 screens for en-US; found 10")])

    def test_port_decisions(self):
        source = FIXTURES / "shellbell"
        new, old = [json.loads((source / f).read_text()) for f in ("listing.new.json", "listing.json")]
        self.assertEqual(new["approved"], {"metadata": True, "screens": True})
        for target, original in zip(new["targets"], old["targets"]):
            self.assertEqual(target.get("status"), original.get("status"))
        for name, header in new["graphics"]["apple"].items():
            self.assertEqual(header["template"], "header")
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
        self.data["app"]["demoEntry"] = "missing.ts"
        self.data["screens"][1]["flows"] = {"apple": ".listing-kit/flows/unused.yaml"}
        self.assertEqual(self.check(purpose="capture"), [expected[0], (
            "ERROR", "phone/one", "missing input file: flows/missing.yaml")])

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
        self.assertEqual(self.check(), [("ERROR", "style.fonts", "unknown locale key")])
        self.data["style"]["fonts"]["default"] = self.data["style"]["fonts"].pop("de")
        self.assertEqual(self.check(), [
            ("ERROR", "style.fonts.default.headline[0]", "unknown bundled font 'Other'")])

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
        self.record([rows[0]["outputPath"]])
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
        self.assertCountEqual(self.check(), [("ERROR", "platforms", "unknown condition key"),
                                            ("ERROR", "targets[0].capture.nativeSize", "expected two positive integers"),
                                            ("ERROR", "targets[0].capture.runtime", "expected a non-empty string"),
                                            ("ERROR", "targets[0].capture.appId", "expected a non-empty string")])

    def test_manifest_and_tsv_cli(self):
        self.data["screens"][0].update(draft=True, flows={"play": self.flow})
        self.target["capture"] = {"runtime": "35", "nativeSize": [1080, 2400], "appId": "example.beta",
                                  "deviceType": "Pixel", "orientation": "portrait", "display": "internal"}
        self.data["style"] = {"mode": "framed", "template": "caption-top"}
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
        self.assertEqual(manifest["manifest"], 1)
        first, _, last = manifest["outputs"]
        expected = {"kind": "screenshot", "targetId": "phone", "screenId": "one",
                                 "localeId": "en-US", "storeCode": "en-US", "store": "play", "slotId": "phone",
                                 "index": 1, "size": [1080, 1920], "styleMode": "framed", "template": "caption-top",
                                 "flowPath": self.flow, "rawPath": ".listing-kit/raw/phone/en-US/one.png",
                                 "outputPath": "localized/play/en-US/images/phoneScreenshots/01_one.png",
                                 "upload": "fastlane", "draft": True, "textFallback": False}
        self.assertEqual({k: first[k] for k in expected}, expected)
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

    def record(self, files):
        (self.app / ".listing-kit/outputs.json").write_text(json.dumps({"format": 1, "files": files}))

    def test_owned_outputs_only(self):
        current = self.manifest()["outputs"][0]["outputPath"]
        owned = "fastlane/screenshots/en-US/old.png"
        for name in (owned, current, "fastlane/screenshots/en-US/privacy_url.txt", "outside.png"):
            (self.app / name).parent.mkdir(parents=True, exist_ok=True)
            (self.app / name).touch()
        self.assertEqual(self.manifest()["stale"], [])
        self.record([current, owned, "outside.png", "fastlane/screenshots/gone.png"])
        self.assertEqual(self.check(), [("WARN", owned, "stale output")])
        self.assertEqual(self.manifest()["stale"], [owned])

    def test_invalid_inventory(self):
        for value, field, msg in (
                ([], "", "expected an object"),
                ({"files": []}, ".format", "expected inventory format 1"),
                ({"format": 2, "files": []}, ".format", "expected inventory format 1"),
                ({"format": True, "files": []}, ".format", "expected inventory format 1"),
                ({"format": 1}, ".files", "expected an array"),
                ({"format": 1, "files": "x"}, ".files", "expected an array"),
                ({"format": 1, "files": [3]}, ".files[0]", "expected an app-relative file path"),
                ({"format": 1, "files": ["../escape"]}, ".files[0]", "expected an app-relative file path")):
            with self.subTest(value=value):
                (self.app / plan.RECORD).write_text(json.dumps(value))
                self.assertEqual(self.check(), [("ERROR", ".listing-kit/outputs.json" + field, msg)])

    def test_owned_path_through_directory_alias(self):
        current = self.app / self.manifest()["outputs"][0]["outputPath"]
        current.parent.mkdir(parents=True)
        current.touch()
        alias = current.parents[3] / "old-locale"
        alias.symlink_to(current.parents[2])
        self.record([(alias.relative_to(self.app) / "images" / current.parent.name / current.name).as_posix()])
        self.assertEqual(self.check(), [])

    def test_inventory_cannot_claim_through_escaping_tree(self):
        (self.app / "store-assets").symlink_to(self.repo)
        (self.repo / "apple").mkdir()
        (self.repo / "apple/old.png").touch()
        self.record(["store-assets/apple/old.png"])
        self.assertEqual(self.check(), [])

    def test_input_output_conflicts(self):
        rows = self.manifest()["outputs"]
        row = rows[0]
        for key in ("rawPath", "outputPath"):
            dest = row[key]
            for source in (dest, dest + "/input", str(Path(dest).parent)):
                with self.subTest(dest=dest, source=source):
                    self.data["style"] = {"logo": source}
                    expected = [("WARN", "style.logo", "missing input file: " + source)]
                    for r in rows:
                        if r[key] == source or source.startswith(r[key] + "/") or r[key].startswith(source + "/"):
                            expected.append(("ERROR", "phone/" + r["screenId"], r[key] + " conflicts with input " + source))
                    self.assertEqual(self.check(), expected)

    def test_output_file_directory_conflicts(self):
        graphic = "store-assets/apple/en-US/header-16x9.png"
        self.data["graphics"] = {"apple": {"header-16x9": {"headline": {"en-US": "Hello"}}}}
        self.data["trees"] = {"play": {"metadata": graphic}}
        self.assertEqual(self.check(), [
            ("ERROR", "graphics.apple.header-16x9", "%s conflicts with phone/%s output %s/en-US/images/phoneScreenshots/%02d_%s.png" %
             (graphic, screen, graphic, i, screen)) for i, screen in enumerate(("one", "two"), 1)])
        del self.data["trees"], self.data["graphics"]
        (self.app / "fastlane").touch()
        self.assertEqual(self.check(), [
            ("ERROR", "phone/" + screen, "fastlane/metadata/android/en-US/images/phoneScreenshots/%02d_%s.png requires directory fastlane" %
             (i, screen)) for i, screen in enumerate(("one", "two"), 1)])

    def test_configured_tree_file_names_each_affected_output(self):
        self.data["trees"] = {"play": {"metadata": "file"}}
        (self.app / "file").touch()
        self.assertEqual(self.check(), [
            ("ERROR", "phone/one", "file/en-US/images/phoneScreenshots/01_one.png requires directory file"),
            ("ERROR", "phone/two", "file/en-US/images/phoneScreenshots/02_two.png requires directory file"),
            ("ERROR", "trees.play.metadata", "expected directory: file")])

    def test_output_leaf_symlink(self):
        dest = self.manifest()["outputs"][0]["outputPath"]
        leaf = self.app / dest
        leaf.parent.mkdir(parents=True)
        leaf.symlink_to(self.app / self.flow)
        self.assertEqual(self.check(), [("ERROR", "phone/one", dest + " must be a regular file, found symlink"),
                                       ("ERROR", "phone/one", dest + " conflicts with input " + self.flow)])

    def test_lexical_input_below_output(self):
        dest = self.manifest()["outputs"][0]["outputPath"]
        leaf = self.app / dest
        leaf.mkdir(parents=True)
        (leaf / "logo").symlink_to(self.app / self.flow)
        self.data["style"] = {"logo": dest + "/logo"}
        self.assertEqual(self.check(), [
            ("ERROR", "phone/one", dest + " must be a regular file, found non-regular file"),
            ("ERROR", "phone/one", dest + " conflicts with input " + dest + "/logo")])

    def test_capture_locale_order_and_unicode_uniqueness(self):
        self.data["locales"] = [{"id": "é", "play": "fr"}, "en-US"]
        self.target["locales"] = ["en-US", "é"]
        for row in self.manifest()["outputs"]:
            self.assertEqual(row["captureLocaleId"], "é")
            self.assertIn("/é/", row["rawPath"])
        self.data["locales"].append({"id": "E\u0301", "play": "de"})
        self.assertEqual(self.check(), [("ERROR", "locales[2].id", "duplicate locale id")])

    def test_dynamic_rule_names(self):
        rules = self.rules["stores"]["play"]["graphics"]
        for key in ("path", "value", "required", "fields", "self"):
            rules.append(dict(rules[0], id=key, file=key))
        self.data["graphics"] = {"play": {r["id"]: {"headline": {"en-US": r["id"]}} for r in rules[-5:]}}
        (self.app / specs.OVERRIDE).write_text(json.dumps({"stores": {"play": {"graphics": rules[-5:]}}}))
        (self.app / plan.LISTING).write_text(json.dumps(self.data))
        result = subprocess.run([sys.executable, plan.__file__, "check", str(self.app)], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_numbering_per_locale_and_route(self):
        self.data["locales"].append({"id": "de", "play": "de"})
        self.target["locales"] = ["de"]
        extra = dict(self.target, id="extra", locales=["en-US", "de"])
        self.data["targets"] += [dict(extra, id="retired", state="retired"), extra, dict(extra, id="manual", upload="console")]
        rows = self.manifest()["outputs"]
        self.assertEqual([r["index"] for r in rows], [1, 2, 1, 3, 2, 4, 1, 1, 2, 2])
        for r in rows:
            target = next(t for t in self.data["targets"] if t["id"] == r["targetId"])
            screen = next(s for s in self.data["screens"] if s["id"] == r["screenId"])
            self.assertEqual(plan.output_name(self.data, target, screen, self.rules, r["localeId"]), Path(r["outputPath"]).name)

    def test_capture_orientation_from_size(self):
        for size, orientation in (([1080, 1920], "portrait"), ([1920, 1080], "landscape")):
            with self.subTest(size=size):
                self.target["size"] = size
                job = self.manifest()["captures"][0]
                self.assertEqual(job["orientation"], orientation)
                self.assertEqual(job["store"], "play")

    def test_flow_paths_match(self):
        (self.repo / ".git").mkdir()
        self.data["screens"][0]["flows"] = {"play": "repo:flows/override.yaml"}
        m = self.manifest()
        jobs = {j["rawPath"]: j["flowPath"] for j in m["captures"]}
        self.assertEqual([r["flowPath"] for r in m["outputs"]], ["../../flows/override.yaml", self.flow])
        for row in m["outputs"]:
            self.assertEqual(jobs[row["rawPath"]], row["flowPath"])

    def test_consumer_manifest(self):
        self.data = json.loads((FIXTURES / "plan-split.json").read_text())
        m = self.manifest()
        self.assertEqual(m["app"], {"apple": "example.ios", "play": "example.android"})
        self.assertEqual(m["trees"], {
            "apple": dict(fastlaneDir="ios/fastlane", metadata="ios/fastlane/metadata",
                          screenshots="ios/fastlane/screenshots", storeAssets="artwork/apple"),
            "play": dict(fastlaneDir="android/fastlane", metadata="android/fastlane/metadata/android",
                         screenshots="android/fastlane/metadata/android", storeAssets="artwork/play")})
        jobs = m["captures"]
        self.assertEqual(len(jobs), 8)
        self.assertEqual(len({j["rawPath"] for j in jobs}), 8)
        self.assertEqual(jobs[0], dict(targetId="iphone", store="apple", screenId="one", localeId="en-US", deviceLocale="en-US",
                         flowPath=self.flow, demoEntry=None, appId="example.ios", deviceType="iPhone 17 Pro",
                         display=None, orientation="portrait", nativeSize=[1206, 2622], runtime=None,
                         rawPath=".listing-kit/raw/iphone/en-US/one.png"))
        self.assertEqual([j["deviceLocale"] for j in jobs if j["targetId"] == "phone" and j["screenId"] == "one"],
                         ["en-US", "zh-CN", "iw-IL"])
        self.data["app"].update(ios="new.ios", demoEntry=self.flow)
        self.data["trees"]["apple"].update(fastlaneDir="publish", metadata="copy", screenshots="shots")
        self.data["trees"]["storeAssets"] = "art"
        target, screen = self.data["targets"][0], self.data["screens"][0]
        target["capture"] = dict(appId="beta", deviceType="sim", display="outer", runtime="20",
                                 orientation="landscape", nativeSize=[100, 90])
        screen["flows"] = {"iphone": "repo:alt.yaml"}
        (self.repo / ".git").mkdir()
        m = self.manifest()
        self.assertEqual(m["trees"]["apple"], dict(fastlaneDir="publish", metadata="copy", screenshots="shots", storeAssets="art/apple"))
        self.assertEqual(m["app"]["apple"], "new.ios")
        self.assertEqual(m["captures"][0], dict(jobs[0], **target["capture"], flowPath="../../alt.yaml",
                                                 demoEntry=self.flow))
        self.data["style"] = dict(mode="framed", template="feature", fit="contain", palette={"ink": "#000000"}, bezel={"color": "#c0c0c0"},
                                  logo="repo:mark.png", fonts={"default": {"headline": ["bundled:Inter"], "detail": ["base.ttf"]}})
        target["style"] = dict(template="panel", fit="cover", palette={"detail": "#808080"})
        screen["style"] = dict(template="caption-top", bezel={"bleed": True}, fonts={"zh": {"detail": ["repo:zh.ttf"]}})
        screen.update(detail={"zh": "詳"}, altText={"en-US": ""})
        self.data["screens"].append(dict(id="panel", panel=dict(headline={"en-US": "End"}, rows=[
            dict(label={"zh": "甲"}, text={"en-US": "Bye"})])))
        self.data["graphics"]["apple"]["header-16x9"]["template"] = "header"
        self.data["graphics"]["play"] = {"icon": {"from": "repo:icon.png"}}
        m = self.manifest()
        row = next(r for r in m["outputs"] if (r["targetId"], r["screenId"], r["localeId"]) == ("iphone", "one", "zh"))
        def string(value, fallback=False):
            return dict(value=value, fallback=fallback)
        self.assertEqual(row["text"], dict(caption=string("Open the app", True), detail=string("詳"), altText=string("", True)))
        bundled = Path(plan.__file__).resolve().parents[2] / "assets/fonts/Inter.ttf"
        self.assertEqual(row["style"], dict(mode="framed", template="caption-top", fit="cover", palette=dict(ink="#000000", detail="#808080"),
                         bezel=dict(color="#c0c0c0", bleed=True), logo="../../mark.png",
                         fonts={"headline": [Path(os.path.relpath(bundled, self.app)).as_posix()], "detail": ["../../zh.ttf"]}))
        panel = next(r for r in m["outputs"] if r["screenId"] == "panel" and r["localeId"] == "zh")
        self.assertEqual(panel["text"]["panel"], dict(headline=string("End", True), rows=[dict(label=string("甲"), text=string("Bye", True))]))
        self.assertEqual(len(m["captures"]), 8)
        graphic = next(r for r in m["outputs"] if r["slotId"] == "icon")
        header = next(r for r in m["outputs"] if r["slotId"] == "header-16x9")
        self.assertEqual(header["template"], "header")
        self.assertEqual(header["style"]["template"], "header")
        self.assertIsNone(graphic["template"])
        self.assertIsNone(graphic["style"]["template"])
        self.assertIsNone(graphic["style"]["fit"])
        self.assertEqual(graphic["style"]["bezel"], {})
        self.assertEqual(graphic["style"]["palette"], {"ink": "#000000"})
        self.assertEqual(graphic["style"]["logo"], row["style"]["logo"])
        self.assertEqual(graphic["style"]["fonts"], {"headline": row["style"]["fonts"]["headline"], "detail": ["base.ttf"]})
        self.assertEqual(graphic["from"], "../../icon.png")
        self.assertEqual(graphic["label"], next(g["label"] for g in self.rules["stores"]["play"]["graphics"] if g["id"] == "icon"))
        self.assertEqual(row["label"], specs.slot(self.rules, "apple", "iphone-di-medium")["label"])

    def test_individual_consumer_inputs_change_the_manifest(self):
        screen = self.data["screens"][0]
        panel = dict(headline={"en-US": "End"}, rows=[dict(label={"en-US": "A"}, text={"en-US": "B"})])
        self.data["screens"].append(dict(id="closing", panel=panel))
        graphic = dict(headline={"en-US": "Feature"}, detail={"en-US": "Detail"}, altText={"en-US": "Alt"})
        icon = {"from": "old.png"}
        self.data["graphics"] = {"play": {"featureGraphic": graphic, "icon": icon}}
        self.target.update(capture={}, style={})
        self.data["trees"] = {"play": {}}
        screen["style"] = {}
        baseline = self.manifest()
        changes = [
            (self.data["app"], "id", "updated", ("app", "play")),
            (self.data["app"], "demoEntry", "entry.ts", ("captures", 0, "demoEntry")),
            (screen, "flow", "next.yaml", ("captures", 0, "flowPath")),
            (self.data["trees"], "storeAssets", "assets", ("trees", "play", "storeAssets")),
            (self.data["trees"]["play"], "fastlaneDir", "deploy", ("trees", "play", "fastlaneDir")),
            (self.data["trees"]["play"], "metadata", "meta", ("trees", "play", "screenshots")),
            (panel["headline"], "en-US", "Next", ("outputs", 2, "text", "panel", "headline")),
            (icon, "from", "new.png", ("outputs", 4, "from")),
        ]
        for key, value in dict(appId="beta", deviceType="other", display="outer", orientation="landscape",
                               nativeSize=[100, 200], runtime="24").items():
            changes.append((self.target["capture"], key, value, ("captures", 0, key)))
        for key in ("caption", "detail", "altText"):
            changes.append((screen, key, {"en-US": "New"}, ("outputs", 0, "text")))
        for key in ("label", "text"):
            changes.append((panel["rows"][0][key], "en-US", "New", ("outputs", 2, "text", "panel", "rows", 0, key)))
        for key in ("headline", "detail", "altText"):
            changes.append((graphic[key], "en-US", "New", ("outputs", 3, "text", key)))
        for key, value in dict(mode="framed", template="band", fit="cover", palette={"ink": "#ff0000"},
                               bezel={"bleed": True}, logo="logo.png").items():
            changes.append((screen["style"], key, value, ("outputs", 0, "style", key)))
        for role in ("headline", "detail"):
            changes.append((self.target["style"], "fonts", {"default": {role: ["font.ttf"]}}, ("outputs", 0, "style", "fonts", role)))
        for store_key, row in (("screenshots", 0), ("graphics", 3)):
            rules = self.rules["stores"]["play"][store_key]
            rule = specs.slot(self.rules, "play", "phone") if row == 0 else next(r for r in rules if r["id"] == "featureGraphic")
            changes.append((rule, "label", "New console label", ("outputs", row, "label")))
        for obj, key, value, path in changes:
            with self.subTest(key=key, path=path):
                previous = obj.copy()
                obj[key] = value
                before, after = baseline, self.manifest()
                for part in path:
                    before, after = before[part], after[part]
                self.assertNotEqual(before, after)
                obj.clear()
                obj.update(previous)

    def test_stale_symlink_to_current_file(self):
        row = self.manifest()["outputs"][0]
        current = self.app / row["outputPath"]
        current.parent.mkdir(parents=True)
        current.touch()
        stale = current.parent / "02_retired.png"
        stale.symlink_to(current.name)
        self.record([stale.relative_to(self.app).as_posix()])
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
        self.assertEqual(self.manifest()["stale"], [])
        self.record(["fastlane/metadata/en-US/old-header.png"])
        self.assertEqual(self.manifest()["stale"], ["fastlane/metadata/en-US/old-header.png"])

    def test_unrecorded_nonportable_filename_is_ignored(self):
        folder = self.app / "fastlane/screenshots/en-US"
        folder.mkdir(parents=True)
        (folder / "old:screen.png").touch()
        self.assertEqual(self.manifest()["stale"], [])

    def test_control_safe_diagnostics(self):
        self.assertEqual(plan._line(("ERROR", "x\x1b\u2028", "bad")), "ERROR\tx\\x1b\\u2028\tbad")


if __name__ == "__main__":
    unittest.main()
