"""Child lifecycle tests. All filesystem locations are supplied by the fixture."""
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills/listing-kit/scripts/fastlane"))
import lk_fastlane as lk


class SpaceshipLogs(unittest.TestCase):
    def setUp(self):
        case = tempfile.TemporaryDirectory(dir=os.environ["FL_FIXTURE"])
        self.addCleanup(case.cleanup)
        self.base = Path(case.name)
        self.logs = self.base / "logs"
        self.logs.mkdir(mode=0o700)
        self.stderr = io.StringIO()
        self.mask = {signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT}
        for sig in self.mask:
            self.addCleanup(signal.signal, sig, signal.signal(sig, signal.default_int_handler))

    def invoke(self, program, *directories):
        with redirect_stderr(self.stderr):
            return lk.run_child([sys.executable, "-c", "import os, time\n" + program],
                                cwd=self.logs, log_dirs=directories or (self.logs,))

    def test_identity_and_snapshot(self):
        # Reserve a real child PID so a pre-existing log can have that exact PID.
        program = """
from pathlib import Path
while not Path('go').exists(): time.sleep(.01)
prefix = f'spaceship123_{os.getpid()}_'
Path(prefix + '1.log').write_text('modified')
Path(prefix + '2.log').touch()
Path(prefix + '3.log').symlink_to('target')
Path('spaceship-notes.log').touch()
"""
        with subprocess.Popen([sys.executable, "-c", "import os, time\n" + program],
                              cwd=self.logs, start_new_session=True) as child:
            prefix = f"spaceship123_{child.pid}_"
            old = self.logs / (prefix + "1.log")
            old.touch()
            (self.logs / "target").write_text("untouched")

            def launch(*args, **kwargs):
                # The still-running parent creates its own log after the snapshot.
                (self.logs / f"spaceship123_{os.getpid()}_4.log").touch()
                (self.logs / "go").touch()
                return child

            try:
                with patch.object(subprocess, "Popen", launch):
                    self.invoke("pass")
            finally:
                child.kill()
        self.assertEqual(old.read_text(), "modified")
        self.assertFalse((self.logs / (prefix + "2.log")).exists())
        self.assertTrue((self.logs / (prefix + "3.log")).is_symlink())
        self.assertEqual((self.logs / "target").read_text(), "untouched")
        self.assertTrue((self.logs / f"spaceship123_{os.getpid()}_4.log").exists())
        self.assertTrue((self.logs / "spaceship-notes.log").exists())

    def test_signals_during_spawn_and_cleanup(self):
        popen, unlink = subprocess.Popen, os.unlink
        children, unlinked = [], []
        def launch(*args, **kwargs):
            child = popen(*args, **kwargs)
            children.append(child)
            deadline = time.monotonic() + 3
            while not (self.logs / "ready").exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue((self.logs / "ready").exists())
            os.kill(os.getpid(), signal.SIGTERM)
            self.assertTrue(self.mask <= signal.pthread_sigmask(signal.SIG_BLOCK, []))
            return child

        def interrupt_unlink(name, *, dir_fd):
            self.assertIsNotNone(children[0].poll())
            self.assertTrue(self.mask <= signal.pthread_sigmask(signal.SIG_BLOCK, []))
            if not unlinked:
                os.kill(os.getpid(), signal.SIGQUIT)
            unlink(name, dir_fd=dir_fd)
            unlinked.append(name)

        try:
            with patch.object(subprocess, "Popen", launch), patch.object(os, "unlink", interrupt_unlink):
                with self.assertRaises(KeyboardInterrupt):
                    self.invoke("""
import signal
assert not (signal.pthread_sigmask(signal.SIG_BLOCK, []) & {signal.SIGTERM, signal.SIGINT})
for thread in (1, 2): open(f'spaceship1_{os.getpid()}_{thread}.log', 'w').close()
open('ready', 'w').close()
time.sleep(10)
""")
            self.assertEqual(len(unlinked), 2)
            self.assertFalse(list(self.logs.glob("*.log")))
        finally:
            for child in children:
                child.kill()
                child.wait()

    def test_inaccessible_directory_and_entry(self):
        denied = self.base / "private-location"
        denied.mkdir()
        original_open = os.open

        def checked_open(path, *args, **kwargs):
            if path == denied or str(path).endswith("_2.log"):
                raise PermissionError("sensitive path")
            return original_open(path, *args, **kwargs)

        with patch.object(os, "open", checked_open):
            result = self.invoke("""
for thread in (1, 2, 3): open(f'spaceship1_{os.getpid()}_{thread}.log', 'w').close()
raise SystemExit(17)
""", denied, self.logs)
            self.assertEqual(result.returncode, 17)
            with self.assertRaises(FileNotFoundError):
                with redirect_stderr(self.stderr):
                    lk.run_child([str(self.base / "missing-fastlane")], log_dirs=(denied,))
        self.assertEqual(len(list(self.logs.glob("*.log"))), 1)
        self.assertIn("could not check 2 locations", self.stderr.getvalue())
        self.assertIn("could not check 1 locations", self.stderr.getvalue())
        self.assertNotIn("sensitive", self.stderr.getvalue())
        self.assertNotIn(str(self.base), self.stderr.getvalue())

    def test_late_directory_failure_and_interrupt_preserve_exit_code(self):
        inaccessible = self.base / "before-only"
        inaccessible.mkdir()
        listdir, unlink = os.listdir, os.unlink
        snapshots = []

        def deny_rescan(fd):
            if os.path.samestat(os.fstat(fd), inaccessible.stat()):
                if snapshots:
                    raise PermissionError("sensitive rescan path")
                snapshots.append(fd)
            return listdir(fd)

        def interrupted_unlink(name, *, dir_fd):
            os.kill(os.getpid(), signal.SIGHUP)
            unlink(name, dir_fd=dir_fd)

        for status, exception in ((3, subprocess.CalledProcessError), (0, KeyboardInterrupt)):
            snapshots.clear()
            with self.subTest(status=status), patch.object(os, "listdir", deny_rescan), \
                    patch.object(os, "unlink", interrupted_unlink), redirect_stderr(self.stderr):
                with self.assertRaises(exception) as caught:
                    lk.run_child([sys.executable, "-c",
                                  "import os; open(f'spaceship1_{os.getpid()}_2.log', 'w').close(); "
                                  f"raise SystemExit({status})"], cwd=self.logs,
                                 log_dirs=(inaccessible, self.logs), check=True)
                if status:
                    self.assertEqual(caught.exception.returncode, status)
            self.assertFalse(list(self.logs.glob("*.log")))
        self.assertEqual(self.stderr.getvalue().count("could not check 1 locations"), 2)
        self.assertNotIn("sensitive", self.stderr.getvalue())

    def test_directory_close_error_preserves_missing_executable(self):
        close = os.close
        directory = self.logs.stat()
        def failed_close(fd):
            matches = os.path.samestat(os.fstat(fd), directory)
            close(fd)
            if matches:
                raise OSError("sensitive close error")

        with patch.object(os, "close", failed_close), redirect_stderr(self.stderr):
            with self.assertRaises(FileNotFoundError):
                lk.run_child([str(self.base / "missing-fastlane")], log_dirs=(self.logs,))
        self.assertIn("could not check 1 locations", self.stderr.getvalue())
        self.assertNotIn("sensitive", self.stderr.getvalue())

    def test_regular_file_swapped_before_open(self):
        original_open = os.open
        def swap(name, flags, **options):
            if str(name).endswith(".log"):
                os.replace("foreign", name, src_dir_fd=options["dir_fd"], dst_dir_fd=options["dir_fd"])
            return original_open(name, flags, **options)

        (self.logs / "foreign").write_text("keep")
        with patch.object(os, "open", swap):
            self.invoke("open(f'spaceship1_{os.getpid()}_2.log', 'w').close()")
        self.assertEqual(next(self.logs.glob("*.log")).read_text(), "keep")

    def test_entry_swapped_after_open(self):
        rename = os.rename
        def swap(name, dest, *, src_dir_fd, dst_dir_fd):
            if str(name).endswith(".log"):
                os.unlink(name, dir_fd=src_dir_fd)
                os.symlink("foreign", name, dir_fd=src_dir_fd)
            rename(name, dest, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)

        (self.logs / "foreign").write_text("keep")
        with patch.object(os, "rename", swap):
            self.invoke("open(f'spaceship1_{os.getpid()}_2.log', 'w').close()")
        self.assertTrue(next(self.logs.glob("*.log")).is_symlink())
        self.assertEqual((self.logs / "foreign").read_text(), "keep")

    def test_directory_replaced_by_symlink(self):
        other = self.base / "other"
        other.mkdir()
        self.invoke("""
from pathlib import Path
name = f'spaceship1_{os.getpid()}_2.log'
Path(name).touch()
Path('../other', name).write_text('foreign')
Path('../logs').rename('../original')
Path('../logs').symlink_to('other')
""")
        self.assertFalse(list((self.base / "original").glob("*.log")))
        self.assertEqual(next(other.glob("*.log")).read_text(), "foreign")


if __name__ == "__main__":
    unittest.main()
