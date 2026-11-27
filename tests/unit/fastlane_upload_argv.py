"""Check the actual text-only child launched by the Python adapter."""
import json
import os
from pathlib import Path
import sys

calls = [json.loads(line) for line in Path(os.environ["STUB_LOG"]).read_text().splitlines()
         if line.startswith("[")]
if sys.argv[1] == "approval":
    record = json.loads(Path(sys.argv[2]).read_text())["stores"]["apple"]
    assert record["appleVersion"] == {"id": "version-id", "string": "1.2.3", "state": "PREPARE_FOR_SUBMISSION",
                                      "appInfoId": "info-id", "appInfoState": "DEVELOPER_REJECTED",
                                      "localizations": [["en-US", "version-localization", "info-localization"]]}
    assert all("review_information" not in key for key in record["files"])
elif sys.argv[1] == "apple":
    assert not any(args[:2] == ["deliver", "run"] for args in calls)
    assert any(Path(args[0]).name == "apple_text_upload.rb" and args[1] == "write" and Path(args[-1]).name == "apple-target.json" for args in calls)
else:
    args = [args for args in calls if args[:2] == ["supply", "run"]][-1]
    assert {"--skip_upload_screenshots", "--skip_upload_images"} <= set(args)
    assert args[args.index("--rescue_changes_not_sent_for_review") + 1] == "false"
    assert args[args.index("--changes_not_sent_for_review") + 1] == "true"
    assert "--validate_only" not in args
