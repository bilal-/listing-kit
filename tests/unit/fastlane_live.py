"""Exercise live-download shapes and process cleanup against fastlane.test.sh's stub."""
import json
import os
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

    def test_supply_error_diagnostics(self):
        body = '{"description":"[!] private listing copy"}'
        category = "listing-kit: supply action failed for example.play (exit 17)"
        version_fix = "listing-kit: supply version code required or unknown for example.play (exit 17); rerun with --version-code <code>"
        track_fix = "listing-kit: supply track not found for example.play (exit 17); rerun with --track <track>"
        google = "Google Api Error: Invalid request - Edit expired"
        ambiguous = "More than one release found in this track. Please specify with the :version_code option to select a release."
        missing = "Unable to find the requested track - 'beta'"
        capped = "[!] " + "échec " * 70
        cases = [
            ("[!] earlier\n" + body + "\n\x1b[31m[12:34:56]: \x1b[1m[!] " +
             google.replace(" - ", "\t-  ") + "\x1b[0m\r\n" + body, category, "[!] " + google),
            (body + "\n [!] indented\ntrace\r[!] carriage return", category, None),
            ("[!] first\n[!] ", category, None),
            ("[!] -----BEGIN PRIVATE KEY----- short key material", category, "[!] [redacted]"),
            ('[!] invalid "private_key": "short value"', category, "[!] [redacted]"),
            ("[!] Authorization: Bearer " + "a" * 24, category, "[!] [redacted]"),
            ("[!] bad Bearer a.b~c==", category, "[!] bad [redacted]"),
            ("[!] invalid token=Abcdefgh123456", category, "[!] [redacted]"),
            ("[!] denied for first.last+play@example.org", category, "[!] denied for [redacted]"),
            ('[!] denied for "two words"@example.org', category, "[!] denied for [redacted]"),
            ("[!] opaque " + "ab" * 10 + " YWJjZGVmZ2hpamtsbW4= aaaaaa.bbbbbb.cccccc",
             category, "[!] opaque [redacted] [redacted] [redacted]"),
            (capped, category, capped[:300]),
            ("[!] " + "a " * 138 + "token = abcdefghijkl in prose", category, None),
            ("[!] " + ambiguous, version_fix, "[!] " + ambiguous),
            ("[!] " + missing, track_fix, "[!] " + missing),
            ("[!] Google Api Error: Invalid request - Track not found: beta", track_fix,
             "[!] Google Api Error: Invalid request - Track not found: beta"),
            ("[!] Could not find release for version code '43' to update changelog", version_fix,
             "[!] Could not find release for version code '43' to update changelog"),
            ("[!] Cannot find changelog because no version code given - please specify :version_code", version_fix,
             "[!] Cannot find changelog because no version code given - please specify :version_code"),
            ('{"description":"[!] ' + ambiguous + '"}', category, None),
        ]
        for output, first, detail in cases:
            with self.subTest(output=output):
                (self.base / "supply-error").write_bytes(output.encode())
                result = subprocess.run([KIT / "bin/listing-kit", "pull", "--store", "play",
                                         "--package-name", "example.play"], cwd=self.app, env=self.env,
                                        capture_output=True, text=True, timeout=20)
                expected = [first]
                if detail:
                    expected.append("listing-kit: fastlane said: " + detail)
                self.assertEqual(result.returncode, 1)
                errors = [line for line in result.stderr.splitlines() if line != "Spaceship API logs removed: 0"]
                self.assertEqual(errors, expected)
                self.assertNotIn("[!]", result.stdout)
                self.assertNotIn("private listing copy", result.stdout)

    def test_pinned_download_uses_read_only_describe(self):
        sys.path.insert(0, str(KIT / "scripts/fastlane"))
        self.addCleanup(sys.path.pop, 0)
        import lk_fastlane as lk

        store = lk.Store("apple", "example.apple", self.app, {"fastlaneDir": self.app},
                         lk.specs.load(), {}, {}, "", None, FIXTURE / "apple.json")
        store.scratch = self.base
        with patch.dict(os.environ, self.env, LK_APPLE_WRITE_SECRET="inherited"):
            remote = lk.download(store, self.base / "before", pin_apple=True)
            self.assertEqual(remote.apple_version, {"id": "version-id", "string": "1.2.3",
                                                    "state": "PREPARE_FOR_SUBMISSION", "appInfoId": "info-id",
                                              "appInfoState": "DEVELOPER_REJECTED",
                                              "localizations": [["en-US", "version-localization", "info-localization"]]})
            # Apple receipt baselines from before version pinning only hashed files.
            self.assertEqual(remote.snapshot_hash(), lk.fingerprint(dict(files=remote.hashes(), locales=[])))
            for marker in ("info-race", "version-locale-race", "info-locale-race"):
                with self.subTest(marker=marker):
                    flag = self.base / marker
                    flag.touch()
                    with self.assertRaisesRegex(ValueError, "changed during download"):
                        lk.download(store, self.base / (marker + "-download"), pin_apple=True)
                    flag.unlink()
            (self.base / "bad-description").touch()
            with self.assertRaisesRegex(ValueError, "^Invalid Apple version description$"):
                lk.download(store, self.base / "recheck", pin_apple=True)
        self.assertFalse((self.base / "sent").exists())

    def check_logs(self, mode, code, calls):
        home, parent = self.base / "home", self.base / "temp"
        home.mkdir()
        parent.mkdir()
        self.env.update(HOME=str(home), TMPDIR=str(parent), FL_LOG_MODE=mode)
        rc, out = self.command("pull", "--store", "apple", "--app-identifier", "example.apple")
        self.assertEqual(rc, code, out)
        records = list(map(json.loads, (self.base / "log-runs").read_text().splitlines()))
        self.assertEqual(len(records), calls)
        for tmp, permissions, verbose, umask, stale in records:
            self.assertEqual(Path(tmp).parent, parent)
            self.assertEqual(permissions, 0o700)
            with self.subTest(setting="VERBOSE"):
                self.assertEqual(verbose, "1")
            with self.subTest(setting="umask"):
                self.assertEqual(umask, 0o077)
            self.assertFalse(stale, "a log survived until the next fastlane call")
        self.assertEqual(out.count("Spaceship API logs removed: 1"), calls)
        self.assertNotIn("private-response-marker", out)

    def test_success(self):
        self.check_logs("success", 0, 3)

    def test_nonzero(self):
        self.check_logs("error", 1, 2)

    def test_sigterm(self):
        self.check_logs("term", 130, 2)

    def test_setup_and_pull_with_unreadable_home(self):
        # A non-directory HOME fails listing even when tests run as root.
        home = self.base / "inaccessible-home"
        home.touch()
        self.env["HOME"] = str(home)
        for args in (("fastlane", "setup"), ("pull",)):
            rc, out = self.command(*args, "--store", "apple", "--app-identifier", "chosen.apple")
            self.assertEqual(rc, 0, out)
            self.assertNotIn(str(home), out)

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
