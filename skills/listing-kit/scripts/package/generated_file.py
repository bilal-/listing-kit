"""Expose only complete generated files and honor exclusive creation."""
import os
from pathlib import Path
import tempfile


def write_generated(path, content, mode, overwrite):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content.encode("utf-8"))
            stream.flush()
            temporary.chmod(mode)
            if overwrite:
                os.replace(temporary, path)
            else:
                os.link(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
