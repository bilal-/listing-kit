"""Prepare manual review inputs when ignored or credential-named files need excluding."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from secret_scan import credential_file, file_secret, git_files, private_local, sensitive_name, tracked

TREES = ("fastlane", "store-assets", ".listing-kit")
DEVICE_SPECS = (":(glob)app.config.*", "app.json", ":(glob)**/*.pbxproj", ":(glob)**/Info.plist")


def exclusions(root):
    ignored = git_files(root, "--others", "--ignored", "--exclude-standard", "--directory",
                        "--", *TREES, *DEVICE_SPECS)
    unsafe = set()
    passwords = set()
    for tree in TREES:
        if (root / tree).is_symlink():
            continue
        for directory, dirs, files in os.walk(root / tree):
            rel = Path(directory).relative_to(root)
            if rel in ignored:
                dirs.clear()
                continue
            for name in dirs + files:
                path = rel / name
                if path in ignored:
                    continue
                if sensitive_name(path) or credential_file(path):
                    unsafe.add(path)
                elif name == "demo_password.txt":
                    source = root / path
                    resolved = source.resolve()
                    if (source.is_file() and root in resolved.parents
                            and resolved.relative_to(root).parts[0] in TREES and file_secret(source)):
                        passwords.add(path)
                elif private_local(path):
                    if tracked(root / path):
                        unsafe.add(path)
                    else:
                        ignored.add(path)
            dirs[:] = [name for name in dirs if rel / name not in ignored and rel / name not in unsafe]
    return ignored, unsafe, passwords


def link_file(source, dest):
    try:
        os.link(source, dest)
    except OSError:
        shutil.copyfile(source, dest)


def run(script, root, args):
    ignored, unsafe, passwords = exclusions(root)
    cmd = ["bash", script]
    if not ignored and not unsafe and not passwords:
        os.execvp("bash", cmd + [str(root), "--prepared", *args])

    # Only these trees and device declarations are consumed by listing tools.
    # Hard links preserve working-tree contents and avoid copying screenshots.
    with tempfile.TemporaryDirectory() as tmp:
        view = Path(tmp) / "app"
        view.mkdir()
        skip = ignored | unsafe | passwords
        for tree in TREES:
            if (root / tree).is_symlink() and Path(tree) not in skip:
                raise OSError(f"cannot prepare symlinked listing root: {tree}")
            if Path(tree) not in skip and (root / tree).is_dir():
                shutil.copytree(root / tree, view / tree, symlinks=True, copy_function=link_file,
                                ignore=lambda d, names: [n for n in names
                                    if (Path(d) / n).relative_to(root) in skip])
        for directory, dirs, files in os.walk(root):
            rel = Path(directory).relative_to(root)
            dirs[:] = [d for d in dirs if d not in (".git", "Pods", "node_modules", "build",
                       "DerivedData", ".expo", "dist", ".dart_tool")
                       and rel / d not in skip and (rel / d).parts[0] not in TREES
                       and Path(directory) / d != Path(tmp)]
            for name in files:
                path = rel / name
                if path in skip:
                    continue
                if ((rel == Path(".") and (name == "app.json" or name.startswith("app.config.")))
                        or name.endswith(".pbxproj") or name == "Info.plist"):
                    (view / rel).mkdir(exist_ok=True, parents=True)
                    link_file(root / path, view / path)
        env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(view.parent))
        if shutil.which("git"):
            for key in subprocess.check_output(["git", "rev-parse", "--local-env-vars"]).decode().split():
                env.pop(key, None)
        env["LK_REVIEW_NAME_FAILURES"] = str(len(unsafe))
        env["LK_REVIEW_DEMO_FAILURES"] = str(len(passwords))
        rc = subprocess.call(cmd + [str(view), "--prepared", *args], env=env)
        if rc == 0 and Path(script).name == "build-review.sh":
            shutil.copyfile(view / "listing-review.html", root / "listing-review.html")
        return rc


if __name__ == "__main__":
    sys.exit(run(sys.argv[1], Path(sys.argv[2]).resolve(), sys.argv[3:]))
