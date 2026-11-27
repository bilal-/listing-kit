"""Exercise live-download shapes and process cleanup against fastlane.test.sh's stub."""
import json
import os
import pwd
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

KIT = Path(sys.argv.pop()).resolve().parents[1]
FIXTURE = Path(os.environ["FL_FIXTURE"])
CATEGORIES = ("primary_first_sub_category", "primary_second_sub_category", "secondary_category",
              "secondary_first_sub_category", "secondary_second_sub_category")


class LivePull(unittest.TestCase):
    def setUp(self):
        case = tempfile.TemporaryDirectory(dir=FIXTURE)
        self.addCleanup(case.cleanup)
        self.base = Path(case.name)
        self.app = self.base / "app"
        self.app.mkdir()
        self.remote = self.base / "remote/apple/metadata"
        (self.remote / "en-US").mkdir(parents=True)
        (self.remote / "en-US/name.txt").write_text("Sample")
        (self.base / "remote/apple/screenshots").mkdir()
        self.env = dict(os.environ, FL_FIXTURE=str(self.base), APP_STORE_CONNECT_API_KEY_PATH=str(FIXTURE / "apple.json"),
                        SUPPLY_JSON_KEY=str(FIXTURE / "play.json"))

    def command(self, *args):
        result = subprocess.run([KIT / "bin/listing-kit", *args], cwd=self.app, env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=20)
        return result.returncode, result.stdout

    def check_logs(self, mode, code, calls):
        home, parent = self.base / "home", self.base / "temp"
        home.mkdir()
        parent.mkdir()
        unchanged = home / "spaceship-unchanged.log"
        unchanged.write_text("keep")
        (home / "spaceship-modified.log").write_text("before")
        self.env.update(HOME=str(home), TMPDIR=str(parent), FL_PARENT_TMP=str(parent), FL_LOG_MODE=mode)
        rc, out = self.command("pull", "--store", "apple", "--app-identifier", "example.apple")
        self.assertEqual(rc, code, out)
        records = list(map(json.loads, (parent / "invocations").read_text().splitlines()))
        self.assertEqual(len(records), calls)
        for tmp, permissions, stale in records:
            self.assertEqual(Path(tmp).parent, parent)
            self.assertEqual(permissions, 0o700)
            self.assertFalse(stale, "a log survived until the next fastlane call")
        self.assertEqual(list(self.base.rglob("spaceship*.log")), [unchanged])
        self.assertEqual(unchanged.read_text(), "keep")
        self.assertEqual(out.count("Spaceship API logs removed: 4"), 1)
        self.assertEqual(out.count("Spaceship API logs removed: 5"), calls - 1)
        self.assertNotIn("private-response-marker", out)
        self.assertNotIn("spaceship-home.log", out)

    def test_success(self):
        self.check_logs("success", 0, 3)

    def test_nonzero(self):
        self.check_logs("error", 1, 2)

    def test_sigterm(self):
        self.check_logs("term", 130, 2)

    def test_system_temp_and_account_home_with_environment_overrides(self):
        sys.path.insert(0, str(KIT / "scripts/fastlane"))
        import lk_fastlane

        # Redirect the actual shared locations into the fixture, including /tmp on macOS.
        # The wrapper still selects the directories and runs the real cleanup.
        scratch = self.base / "scratch"
        scratch.mkdir(mode=0o700)
        system = self.base / "system-temp"
        account = self.base / "account-home"
        system.mkdir()
        account.mkdir()
        redirects = {Path("/tmp").resolve(): system,
                     Path(pwd.getpwuid(os.getuid()).pw_dir).resolve(): account}
        scan = lk_fastlane.spaceship_logs

        def scan_fixture(scratch, directories):
            return scan(scratch, {redirects.get(d, d) for d in directories})

        with patch.object(lk_fastlane, "spaceship_logs", scan_fixture):
            with lk_fastlane.clean_spaceship_logs(scratch):
                env = dict(self.env, TMPDIR=str(scratch), FL_PARENT_TMP=str(system),
                           HOME=str(account), FL_LOG_MODE="success")
                subprocess.run([os.environ["LK_TEST_FASTLANE"], "--version"], env=env, cwd=scratch,
                               capture_output=True, check=True)
                self.assertTrue((system / "spaceship-temp.log").is_file())
                self.assertTrue((account / "spaceship-home.log").is_file())
        self.assertEqual(list(self.base.rglob("spaceship*.log")), [])

    def test_live_fields(self):
        values = {"en-US/apple_tv_privacy_policy": "Line one\nLine two"}
        values.update({stem: "UTILITIES" if stem == "secondary_category" else "GAMES_ACTION"
                       for stem in CATEGORIES})
        for stem, value in values.items():
            (self.remote / (stem + ".txt")).write_text(value)
        rc, out = self.command("pull", "--store", "apple", "--app-identifier", "example.apple")
        self.assertEqual(rc, 0, out)
        meta = self.app / "fastlane/metadata"
        rules = json.loads((KIT / "specs/stores.json").read_text())["stores"]["apple"]["fields"]
        for stem, value in values.items():
            self.assertEqual((meta / (stem + ".txt")).read_text(), value)
            field = next((f for f in rules if f["stem"] == Path(stem).name), None)
            self.assertIsNotNone(field, stem)
            self.assertEqual(field["scope"], "locale" if "/" in stem else "app")
            self.assertEqual(field["required"], {"rule": "never"})
            self.assertNotIn("limit", field)

        def validate():
            return subprocess.check_output([sys.executable, KIT / "scripts/lib/fields.py", "apple-app",
                                            meta, "--app-root", self.app], text=True)

        self.assertIn("PASS\tprimary_first_sub_category:", validate())
        category = meta / "primary_first_sub_category.txt"
        for bad in ("line one\nline two", "\nleading blank line", "-----BEGIN PRIVATE KEY-----"):
            category.write_text(bad)
            out = validate()
            self.assertIn("FAIL\tprimary_first_sub_category:", out)
            self.assertNotIn(bad, out)

    def test_unversioned_plan(self):
        state = self.app / ".listing-kit"
        state.mkdir()
        (state / "listing.json").write_text(json.dumps({
            "app": {"ios": "wrong.apple", "android": "wrong.play"},
            "trees": {"apple": {"fastlaneDir": "wrong"}}, "targets": []}))
        meta = self.app / "ios/fastlane/metadata"
        meta.mkdir(parents=True)
        (meta / "copyright.txt").write_text("2026 Example")
        (self.base / "remote/play/metadata").mkdir(parents=True)
        for args in (("fastlane", "setup", "--store", "play", "--package-name", "chosen.play"),
                     ("pull", "--app-identifier", "chosen.apple")):
            rc, out = self.command(*args)
            self.assertEqual(rc, 0, out)
            self.assertEqual(out.count("unversioned plan (missing format)"), 1, out)
            self.assertIn(args[-1], out)
            self.assertNotIn("wrong", out)
        self.assertTrue((meta / "en-US/name.txt").is_file())
        rc, out = self.command("pull", "--store", "apple")
        self.assertNotEqual(rc, 0)
        self.assertIn("--app-identifier", out)


if __name__ == "__main__":
    unittest.main()
