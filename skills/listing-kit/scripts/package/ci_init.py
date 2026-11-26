"""Generate a store listing pipeline at the app's repository root."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generated_file import write_generated

KIT = Path(__file__).resolve().parents[2]


def repository(app):
    result = subprocess.run(["git", "-C", str(app), "rev-parse", "--show-toplevel"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return Path(os.fsdecode(result.stdout.rstrip(b"\n"))).resolve() if not result.returncode else app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("github", "gitlab"), required=True)
    parser.add_argument("--app-root", type=Path, default=Path("."))
    parser.add_argument("--kit-ref", default="v" + (KIT / "VERSION").read_text().strip())
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    app = args.app_root.resolve()
    if not app.is_dir():
        parser.error("app root must be an existing directory")
    repo = repository(app)
    relative = app.relative_to(repo).as_posix()
    # Paths are literals in both the CI expression language and glob filters.
    if not relative.isprintable() or any(char in relative for char in "*?[]!+{}$\\"):
        parser.error("app path contains CI expression or glob characters")
    ref = args.kit_ref
    if (ref.startswith(("-", "+")) or "$" in ref or not ref.isprintable()
            or subprocess.run(["git", "check-ref-format", "refs/tags/" + ref]).returncode):
        parser.error("expected a literal kit tag, branch name or commit SHA")
    include = False
    if args.provider == "github":
        path = repo / ".github/workflows/listing.yml"
    else:
        path = repo / ".gitlab-ci.yml"
        if os.path.lexists(path):
            include = True
            path = repo / "listing-kit.gitlab-ci.yml"
    if path.parent != path.parent.resolve():
        parser.error("refusing to write through a symlinked workflow directory")
    template = (KIT / "templates/ci" / (args.provider + ".yml")).read_text()
    values = {"APP_PREFIX": "" if relative == "." else relative + "/",
              "APP_ROOT": "./" + relative if relative.startswith("-") else relative, "KIT_REF": ref}
    content = re.sub(r"__(APP_PREFIX|APP_ROOT|KIT_REF)__", lambda m: values[m[1]].replace("'", "''"), template)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        write_generated(path, content, 0o644, args.force)
    except FileExistsError:
        parser.exit(1, f"{path} already exists (use --force)\n")
    print(f"Wrote {path}")
    if include:
        print("include: [{local: 'listing-kit.gitlab-ci.yml'}]")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        sys.exit(str(exc))
