"""Read the kit's local store sync state and verify operation manifests."""

import hashlib
import json


def read_json(path, fallback):
    try:
        with path.open(encoding="utf-8") as stream:
            obj = json.load(stream)
    except FileNotFoundError:
        return fallback
    if not isinstance(obj, dict):
        raise ValueError("Expected a JSON object in %s" % path)
    return obj


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(files):
    return sha(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())


def read_state(path):
    try:
        obj = read_json(path, {"format": 2, "stores": {}})
        if type(obj.get("format")) is not int or obj["format"] != 2:
            raise ValueError
        for name, entry in obj["stores"].items():
            if name not in ("apple", "play") or not isinstance(entry["identity"], dict):
                raise ValueError
            if path.name == "remote.lock.json":
                maps = ("files", "ancestors", "workingBytes", "galleries", "remoteGalleries")
                if not all(isinstance(entry[k], dict) for k in maps) or not isinstance(entry["appliedOperations"], list):
                    raise ValueError
            elif path.name == "publish.receipt.json":
                if not isinstance(entry["operations"], list):
                    raise ValueError
                for op in entry["operations"]:
                    if (op["store"] != name or op["identity"] != entry["identity"] or not op["operation"]
                            or op["status"] not in ("pending", "done", "resolved", "failed")
                            or op["manifestHash"] != fingerprint(dict(files=op["files"], galleries=op["galleries"]))):
                        raise ValueError
        return obj
    except (ValueError, TypeError, KeyError, AttributeError):
        pass
    raise ValueError("Unrecognized state format: delete %s and pull again" % path)
