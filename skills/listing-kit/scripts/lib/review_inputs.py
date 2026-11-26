"""Prepare manual review inputs when ignored or credential-named files need excluding."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan
import specs
from plan import PlanError, listing_roots
from project_files import project_files
from secret_scan import credential_file, file_secret, ignored_private_files, private_local, scan, sensitive_name, tracked


def exclusions(root, trees):
    ignored = ignored_private_files(root, *trees)
    unsafe = set()
    passwords = set()
    for tree in trees:
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


def write_view_plan(view, trees, data, preserve_errors=False):
    """Pin layout and platform inputs for review in a disposable Git-free view."""
    config = {store: {key: str(tree[key]) for key in ("fastlaneDir", "metadata")}
              for store, tree in trees.items()}
    config["apple"]["screenshots"] = str(trees["apple"]["screenshots"])
    config["storeAssets"] = str(trees["apple"]["storeAssets"].parent)
    projected = dict(format=plan.FORMAT, app="listing-review", locales=["en-US"], targets=[], screens=[],
                     platforms=data.get("platforms", {}), trees=config)
    if preserve_errors:
        projected = dict(data, trees=config)
    path = view / plan.LISTING
    path.parent.mkdir(exist_ok=True, parents=True)
    # The filtered view may contain a hard link to the real plan.
    path.unlink(missing_ok=True)
    path.write_text(json.dumps(projected), encoding="utf-8")


def prepare_view(view, trees, source, coverage_path, repo_root=None):
    """Keep coverage before replacing the source plan with its Git-free layout."""
    data = {}
    coverage = None
    if (source / plan.LISTING).is_file():
        data = plan.read_listing(source)
        try:
            rules = specs.load(source)
            manifest = plan.manifest(data, rules, source, repo_root=repo_root)
            coverage = plan.coverage(data, rules, manifest["outputs"])
        except (PlanError, specs.SpecsError):
            write_view_plan(view, trees, data, preserve_errors=True)
            return []
    write_view_plan(view, trees, data)
    coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
    return ["--coverage-view", str(coverage_path)]


def run(script, root, args):
    config = Path(".listing-kit")
    plan._inside(root, root / config)
    ignored, unsafe, passwords = exclusions(root, [config])
    if (root / config).exists():
        status = set(scan(root / config, root, ignored | unsafe | passwords, [root], follow_root=True))
        if status:
            return (3 if 1 in status else 2) if Path(script).name == "build-review.sh" else 1
    resolved = plan.listing_trees(root)
    trees = listing_roots(root, resolved)
    if Path(script).name == "build-review.sh" and not plan.has_listing_directory(root, resolved):
        print(f"No listing directories under: {root} (run Assemble first).", file=sys.stderr)
        return 2
    ignored, unsafe, passwords = exclusions(root, trees)
    cmd = ["bash", script, ".", "--prepared", *args]
    env = os.environ.copy()
    env.setdefault("LK_REVIEW_DISPLAY_ROOT", str(root))
    if not (ignored or unsafe or passwords or any((root / tree).is_symlink() for tree in trees)):
        return subprocess.call(cmd, cwd=root, env=env)

    # Only these trees and device declarations are consumed by listing tools.
    # Hard links preserve working-tree contents and avoid copying screenshots.
    with tempfile.TemporaryDirectory() as tmp:
        view = Path(tmp) / "app"
        view.mkdir()
        skip = ignored | unsafe | passwords
        for tree in trees:
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
        if "--coverage-view" not in args:
            cmd.extend(prepare_view(view, resolved, root, Path(tmp) / "coverage.json"))
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
    except (ValueError, OSError) as exc:
        sys.exit(str(exc))
    if rc == 0 and Path(script).name == "build-review.sh":
        page = Path(os.environ.get("LK_REVIEW_DISPLAY_ROOT", root)) / "listing-review.html"
        print(f"Wrote {page}")
        print(f"Open it in a browser: {page}")
    sys.exit(rc)
