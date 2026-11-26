"""Prepare manual review inputs when ignored or credential-named files need excluding."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan import PlanError, listing_roots
from project_files import project_files
from secret_scan import credential_file, file_secret, ignored_private_files, private_local, sensitive_name, tracked


def exclusions(root, trees):
    ignored = ignored_private_files(root, *trees)
    unsafe = set()
    passwords = set()
    for tree in trees:
        if (root / tree).is_symlink():
            continue
        for directory, dirs, files in os.walk(root / tree):
            rel = Path(directory).relative_to(root)
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
                            and any(root / t in resolved.parents for t in trees) and file_secret(source)):
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
    trees = listing_roots(root)
    if Path(script).name == "build-review.sh" and not any(
            (root / t).is_dir() for t in trees if t != Path(".listing-kit")):
        print(f"No fastlane/ tree under: {root} (run Assemble first).", file=sys.stderr)
        return 2
    ignored, unsafe, passwords = exclusions(root, trees)
    cmd = ["bash", script, ".", "--prepared", *args]
    env = os.environ.copy()
    env.setdefault("LK_REVIEW_DISPLAY_ROOT", str(root))
    if not ignored and not unsafe and not passwords:
        return subprocess.call(cmd, cwd=root, env=env)

    # Only these trees and device declarations are consumed by listing tools.
    # Hard links preserve working-tree contents and avoid copying screenshots.
    with tempfile.TemporaryDirectory() as tmp:
        view = Path(tmp) / "app"
        view.mkdir()
        skip = ignored | unsafe | passwords
        for tree in trees:
            if (root / tree).is_symlink() and Path(tree) not in skip:
                raise OSError(f"cannot prepare symlinked listing root: {tree}")
            if Path(tree) not in skip and (root / tree).is_dir():
                shutil.copytree(root / tree, view / tree, symlinks=True, copy_function=link_file,
                                ignore=lambda d, names: [n for n in names
                                    if (Path(d) / n).relative_to(root) in skip])
        for source in project_files(root):
            path = source.relative_to(root)
            if path in skip or any(t in path.parents for t in trees) or Path(tmp) in source.parents:
                continue
            (view / path.parent).mkdir(exist_ok=True, parents=True)
            link_file(source, view / path)
        env["GIT_CEILING_DIRECTORIES"] = str(view.parent)
        if shutil.which("git"):
            for key in subprocess.check_output(["git", "rev-parse", "--local-env-vars"]).decode().split():
                env.pop(key, None)
        env["LK_REVIEW_NAME_FAILURES"] = str(len(unsafe))
        env["LK_REVIEW_DEMO_FAILURES"] = str(len(passwords))
        rc = subprocess.call(cmd, cwd=view, env=env)
        if rc == 0 and Path(script).name == "build-review.sh":
            shutil.copyfile(view / "listing-review.html", root / "listing-review.html")
        return rc


if __name__ == "__main__":
    script, root = sys.argv[1], Path(sys.argv[2]).resolve()
    try:
        rc = run(script, root, sys.argv[3:])
    except PlanError as exc:
        print(f"listing.json invalid; platform overrides ignored: {exc}")
        sys.exit(1)
    except ValueError as exc:
        sys.exit(str(exc))
    if rc == 0 and Path(script).name == "build-review.sh":
        page = Path(os.environ.get("LK_REVIEW_DISPLAY_ROOT", root)) / "listing-review.html"
        print(f"Wrote {page}")
        print(f"Open it in a browser: {page}")
    sys.exit(rc)
