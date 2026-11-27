"""Check the last text-only upload against the stub's argv and directory contract."""
import json
import os
from pathlib import Path
import sys

store = sys.argv[1]
action = {"apple": "deliver", "play": "supply"}[store]
calls = [json.loads(line) for line in Path(os.environ["STUB_LOG"]).read_text().splitlines()
         if line.startswith("[")]
uploads = [args for args in calls if args[0] == action and
           ("--skip_binary_upload" in args or "--skip_upload_apk" in args)]
args = uploads[-1]
assert args[:2] == [action, "run"]
assert "--screenshots_path" not in args and "--overwrite_screenshots" not in args
if store == "apple":
    assert {"--skip_screenshots", "--skip_binary_upload", "--skip_app_version_update"} <= set(args)
    for flag in ("--submit_for_review", "--run_precheck_before_submit"):
        assert args[args.index(flag) + 1] == "false"
    assert set(args).isdisjoint({"--automatic_release", "--auto_release_date", "--phased_release"})
else:
    assert {"--skip_upload_screenshots", "--skip_upload_images"} <= set(args)
    assert "--rescue_changes_not_sent_for_review" not in args
    assert args[args.index("--changes_not_sent_for_review") + 1] == "true"
    assert "--validate_only" not in args
