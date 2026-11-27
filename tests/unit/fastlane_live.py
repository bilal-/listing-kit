"""Exercise live-download shapes and process cleanup against fastlane.test.sh's stub."""
import json
import os
import shutil
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

    def check_diagnostic(self, command, output, reason, message, remedy="", publish=False):
        play = command == "supply"
        store, flag = ("play", "--package-name") if play else ("apple", "--app-identifier")
        app = "example." + store
        args = ["publish" if publish else "pull", "--store", store, flag, app]
        if publish:
            args.append("--yes")
        else:
            (self.base / (command + "-error")).write_text(output)
        result = subprocess.run([KIT / "bin/listing-kit", *args], cwd=self.app, env=self.env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 1, result.stderr)
        category = f"listing-kit: {command} {reason} for {app} (exit {1 if publish else 17}){remedy}"
        expected = [category, "listing-kit: " + message]
        errors = [line for line in result.stderr.splitlines() if line != "Spaceship API logs removed: 0"]
        self.assertEqual(errors, expected)
        # Any copied run of six or more characters contains a six-character window.
        allowed = "\n".join(expected + ["Spaceship API logs removed: 0"])
        for start in range(len(output) - 5):
            window = output[start:start + 6]
            if window not in allowed:
                self.assertNotIn(window, result.stderr)
        self.assertNotIn("[!]", result.stdout)
        self.assertNotIn("willow", result.stdout)
        self.assertNotIn("7391", result.stdout)

    def test_store_failure_diagnostics(self):
        track = "Use the Play Console track name with --track <track>."
        version = "Select the intended Play release with --version-code <code>."
        expired = "The Play edit is no longer current. Rerun the command."
        permission = "Google Play denied access. Check the service account's Play Console permissions."
        editable = "Apple has no editable version. Prepare an editable version in App Store Connect."
        key = "App Store Connect rejected the API key. Check the key ID, issuer ID and private key."
        unknown = ("fastlane failed with an error listing-kit does not recognise; "
                   "rerun locally with the same command to see fastlane's own output")
        missing = "track not found"
        code = "version code required or unknown"
        google = "Google Api Error: Invalid request - "
        cases = [
            ("supply", "Unable to find the requested track - 'secret-track'", missing, track),
            ("supply", google + "Track not found: secret-track", missing, track),
            ("supply", "More than one release found in this track. Please specify with the :version_code "
             "option to select a release.", code, version),
            ("supply", "Could not find release for version code '725441' to update changelog", code, version),
            ("supply", "Cannot find changelog because no version code given - please specify :version_code", code, version),
            ("supply", google + "The caller does not have permission", "action failed", permission),
            ("supply", google + "forbidden", "forbidden", permission),
            ("supply", google + "Unauthorized", "unauthorized", permission),
            ("supply", "HTTP 401", "action failed", permission),
            ("supply", "HTTP 403", "action failed", permission),
            ("supply", google + "Package not found: com.acme.secret", "not found",
             "Google Play could not find the app. Check --package-name."),
            ("supply", google + "The edit has expired.", "action failed", expired),
            ("supply", google + "This edit has been deleted.", "action failed", expired),
            ("supply", google + "This edit has been invalidated by a subsequent edit.", "action failed", expired),
            ("supply", google + "Conflicting edit", "action failed", expired),
            ("supply", google + "Only releases with status draft may be created on draft app.", "action failed",
             "Google Play requires a draft release for this app. Set the release status to draft in Play Console."),
            ("deliver", "Could not find an edit version on App Store Connect. Try using '--use_live_version true'",
             "action failed", editable),
            ("deliver", "Cannot find edit app store version", "action failed", editable),
            ("deliver", "Cannot update languages - could not find an editable version for 'IOS'", "action failed", editable),
            ("deliver", "Spaceship::UnauthorizedAccessError", "unauthorized", key),
            ("deliver", "Authentication credentials are missing or invalid", "action failed", key),
            ("deliver", "Token has expired, issued-at-time is in the future, or has been revoked! Trying to refresh...",
             "action failed", key),
            ("deliver", "HTTP 401", "action failed", key),
            ("supply", "unexpected private response for edit 794019403", "action failed", unknown),
        ]
        noise = 'DEBUG response body: {"password":"willow/Mint-42","notes":"private listing copy"}'
        for command, error, reason, message in cases:
            with self.subTest(command=command, error=error):
                fixture = f"{noise}\n\x1b[31m[!] {error}\x1b[0m\n[12:34:56]: [!] private login willow / Mint-42"
                remedy = {missing: "; rerun with --track <track>", code: "; rerun with --version-code <code>"}
                self.check_diagnostic(command, fixture, reason, message, remedy.get(reason, ""))

        for probe, message in [
            ("[12:34:56]: [!] review login willow / Mint-42\n"
             "client.rb:138:in 'call_google_api': [!] Edit expired (FastlaneCore::Interface::FastlaneError)", expired),
            ("[!] Google Api Error: Invalid request - edit 4172 com.acme.secret: demo willow / Mint-42", unknown),
            ("[!] GET https://example.test/r?access_token=abc%2Fdef&pin=7391", unknown),
        ]:
            with self.subTest(probe=probe):
                self.check_diagnostic("supply", probe, "action failed", message)

    def test_held_play_publish_failure(self):
        shutil.copytree(FIXTURE / "example-fastlane/metadata/android", self.base / "remote/play/metadata")
        self.assertEqual(self.command("pull", "--store", "play", "--package-name", "example.play")[0], 0)
        local = self.app / "fastlane/metadata/android/en-US"
        shutil.copytree(FIXTURE / "example-fastlane/metadata/android/en-US/images", local / "images", dirs_exist_ok=True)
        (local / "title.txt").write_text("New title")
        output = "VERBOSE review login willow / Mint-42\n[!] The query parameter changesNotSentForReview must not be set"
        (self.base / "auto-review").write_text(output)
        self.env["LK_PUBLISH_UNVERIFIED"] = "play:example.play"
        self.check_diagnostic("supply", output, "action failed",
                              "this app sends changes for review automatically; rerun with --send-for-review to accept that",
                              publish=True)

    def test_version_probe_keeps_child_digits_private(self):
        self.env["FL_VERSION_OUTPUT"] = "fastlane 73917391.123456"
        rc, out = self.command("pull", "--store", "apple", "--app-identifier", "example.apple")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("73917391", out)

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
