"""Open app-local resources through pinned directory descriptors."""
from contextlib import contextmanager, ExitStack
import os
from pathlib import Path
import stat

if __package__:
    from . import specs
else:
    import specs


@contextmanager
def directory(root, relative, create=False):
    """Pin each parent while walking from the app root. Never follow symlinks."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as stack:
        fd = os.open(root, flags)
        stack.callback(os.close, fd)
        for part in Path(relative).parts:
            if not specs.component(part):
                raise ValueError("invalid directory: %s" % relative)
            if create:
                try:
                    os.mkdir(part, dir_fd=fd)
                except FileExistsError:
                    pass
            fd = os.open(part, flags, dir_fd=fd)
            stack.callback(os.close, fd)
        yield fd


@contextmanager
def open_regular(root, relative):
    path = Path(relative)
    with directory(root, path.parent) as parent:
        # Avoid opening devices at all. Recheck the descriptor after open in case
        # the leaf was replaced since stat, and use NONBLOCK for a swapped FIFO.
        if not stat.S_ISREG(os.stat(path.name, dir_fd=parent, follow_symlinks=False).st_mode):
            raise ValueError(f"{relative}: expected regular file")
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOCTTY
        fd = os.open(path.name, flags, dir_fd=parent)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError(f"{relative}: expected a regular file")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                yield stream
        finally:
            os.close(fd)


def read_regular(root, relative, limit):
    if limit < 0:
        raise ValueError(f"{relative}: byte limit exhausted")
    with open_regular(root, relative) as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{relative}: exceeds {limit} byte limit")
    return data
