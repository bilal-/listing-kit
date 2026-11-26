"""Regression cases for private review inputs. All commands run in disposable apps."""
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[2] / "skills/listing-kit"
sys.path.insert(0, str(KIT / "scripts/lib"))
import fields


class ReviewPrivacy(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.temp = Path(tmp.name)
        self.app = self.temp / "review_information"  # An app name must not affect field privacy.
        self.meta = self.app / "fastlane/metadata"
        self.locale = self.meta / "en-US"
        self.locale.mkdir(parents=True)
        (self.locale / "name.txt").write_text("Example")
        self.tmpdir = self.temp / "tmp"
        self.tmpdir.mkdir(mode=0o700)
        key = self.temp / "key.json"
        key.write_text("{}")
        self.env = dict(os.environ, TMPDIR=str(self.tmpdir), GIT_CEILING_DIRECTORIES=str(self.temp),
                        APP_STORE_CONNECT_API_KEY_PATH=str(key),
                        PATH=str(self.temp) + os.pathsep + os.environ["PATH"])
        subprocess.run(["git", "init", "-q"], cwd=self.app, env=self.env, check=True)
        stub = self.temp / "fastlane"
        stub.write_text("""#!/usr/bin/env python3
import fcntl, os, stat, sys, time
from pathlib import Path
base = Path(__file__).parent
if sys.argv[1:] == ['--version']:
    sys.exit(0)
if sys.argv[2] == 'download_metadata':
    review = Path.cwd() / 'metadata/ReViEw_InFoRmAtIoN'
    review.mkdir(parents=True)
    for name in ('Demo_User.TXT', 'DEMO_PASSWORD.txt'):
        (review / name).write_text('private-fixture')
    print('private-fixture', flush=True)
    (base / 'mode').write_text(oct(stat.S_IMODE(Path.cwd().stat().st_mode)))
    if 'FAIL_DOWNLOAD' in os.environ:
        print('private-fixture', file=sys.stderr)
        sys.exit(1)
    if 'INTERRUPT' in os.environ:
        with (base / 'child-lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            os.kill(os.getppid(), int(os.environ['INTERRUPT']))
            time.sleep(3)
elif sys.argv[2] == 'download_screenshots':
    if list((Path.cwd() / 'metadata/ReViEw_InFoRmAtIoN').iterdir()):
        (base / 'retained').touch()
""")
        stub.chmod(0o755)

    def command(self, *args):
        return subprocess.run([str(KIT / "bin/listing-kit"), *args], cwd=self.app,
                              env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, timeout=20)

    def test_download_boundary(self):
        result = self.command("fastlane", "setup", "--store", "apple", "--app-identifier", "example.app")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("private-fixture", result.stdout)
        self.assertFalse((self.temp / "retained").exists(), "demo files remained at screenshot download")
        self.assertEqual((self.temp / "mode").read_text(), "0o700")
        self.assertEqual(list(self.tmpdir.iterdir()), [])

    def test_failed_download(self):
        self.env["FAIL_DOWNLOAD"] = "1"
        result = self.command("pull", "--store", "apple", "--app-identifier", "example.app")
        self.assertTrue((self.temp / "mode").is_file())
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("private-fixture", result.stdout)
        self.assertEqual(list(self.tmpdir.iterdir()), [])

    def test_interrupted_download(self):
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT):
            with self.subTest(signal=sig):
                self.env["INTERRUPT"] = str(int(sig))
                result = self.command("pull", "--store", "apple", "--app-identifier", "example.app")
                self.assertTrue((self.temp / "mode").exists())
                (self.temp / "mode").unlink()
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("private-fixture", result.stdout)
                with (self.temp / "child-lock").open() as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertEqual(list(self.tmpdir.iterdir()), [])

    def test_public_links(self):
        public = self.locale / "support_url.txt"
        for target in (self.meta / "review_information/email_address.txt",
                       self.app / "private/contact", self.app / "private/dangling"):
            target.parent.mkdir(exist_ok=True)
            if target.name != "dangling":
                target.write_text("private-fixture@example.org")
            public.symlink_to(os.path.relpath(target, public.parent))
            for args in (("validate",), ("review",), ("handoff",),
                         ("publish", "--store", "apple", "--app-identifier", "example.app")):
                with self.subTest(command=args[0], target=target.name):
                    result = self.command(*args)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn("private-fixture", result.stdout)
                    self.assertNotIn(str(target.relative_to(self.app)), result.stdout)
                    self.assertRegex(result.stdout, r"Unsafe listing (link|path): [^\n]*fastlane/metadata/en-US/support_url\.txt")
                    self.assertFalse((self.app / "listing-review.html").exists())
                    self.assertFalse((self.app / ".listing-kit/upload").exists())
            public.unlink()

    def test_review_output_link(self):
        target = self.temp / "sentinel"
        page = self.app / "listing-review.html"
        page.symlink_to(target)
        for filtered in (False, True):
            with self.subTest(filtered=filtered):
                if filtered:
                    target.write_text("keep this file")
                    (self.meta / "demo_user.txt").touch()
                result = self.command("review")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(page.name, result.stdout)
                self.assertTrue(page.is_symlink())
                if filtered:
                    self.assertEqual(target.read_text(), "keep this file")
                else:
                    self.assertFalse(target.exists())

    def test_hook_outside_selected_trees(self):
        def git(*args):
            return subprocess.run(["git", *args], cwd=self.app, env=self.env,
                                  check=True, capture_output=True)
        git("config", "user.name", "Fixture")
        git("config", "user.email", "test@example.org")
        app = self.app / "registered"
        app.mkdir()
        changed = app / "unrelated/DeMo_UsEr.TxT.orig"
        changed.parent.mkdir()
        changed.write_text("original")
        renamed = app / "rename-me"
        renamed.write_text("rename fixture")
        git("add", ".")
        git("commit", "-qm", "fixture")
        subprocess.run(["bash", str(KIT / "scripts/package/install-review-hook.sh"), str(app)],
                       cwd=self.app, env=self.env, check=True, capture_output=True)
        hook = self.app / ".git/hooks/pre-commit"
        for name, action in (("Demo_PassWord.TxT.bak", "add"), (changed.name, "modify"),
                             ("demo_user.txt~", "rename")):
            with self.subTest(action=action):
                path = changed.parent / name
                if action == "rename":
                    git("mv", str(renamed), str(path))
                else:
                    path.write_text("changed")
                    git("add", str(path))
                result = subprocess.run([str(hook)], cwd=self.app, env=self.env,
                                        capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(str(path.relative_to(self.app)), result.stderr)
                self.assertIn("delete it", result.stderr)
                self.assertIn("App Store Connect", result.stderr)
            git("reset", "-q", "--hard", "HEAD")
        git("rm", str(changed))
        sibling = self.app / "demo_password.txt"
        sibling.touch()
        git("add", str(sibling))
        subprocess.run([str(hook)], cwd=self.app, env=self.env, check=True, capture_output=True)

    def test_validation_names_each_demo_path(self):
        names = ["review_information/demo_user.txt", "en-US/DEMO_USER.txt", "demo_password.txt~"]
        for name in names:
            path = self.meta / name
            path.parent.mkdir(exist_ok=True)
            path.touch()
        result = self.command("validate")
        self.assertNotEqual(result.returncode, 0)
        for name in names:
            self.assertIn("fastlane/metadata/" + name, result.stdout)
        self.assertIn("delete it, even if empty", result.stdout)

    def test_store_formats(self):
        for value in ("https://example.org\\@www.youtube.com/watch", "https://name@youtu.be/x",
                      "https://youtu.be/x\\y"):
            with self.subTest(video=value):
                self.assertEqual(fields.check(dict(stem="video", value=value, unit="YouTube URL"))[0], "FAIL")
        unknown = "private phone fixture"
        row = dict(stem="phone_number", value=unknown, unit="phone", limit=None, count=len(unknown))
        status, message = fields.check(row)
        self.assertEqual(status, "WARN")
        self.assertIn("App Store Connect", message)
        self.assertNotIn(unknown, message)
        for value in ("+33\u202f1\u00a023 45 67 89", "+49 (0)30/123456 x22", "+1 415-555-0100 ext. 22"):
            with self.subTest(phone=value):
                row = dict(stem="phone_number", value=value, unit="phone", limit=None, store="apple-review", count=len(value))
                status, message = fields.check(row)
                self.assertEqual(status, "PASS")
                self.assertNotIn(value, message)


if __name__ == "__main__":
    unittest.main()
