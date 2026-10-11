"""POSIX directory traversal for safe configuration writes."""

import os
from pathlib import Path

from harness.errors import HarnessError


def open_directory(path: Path) -> int:
    if os.name != "posix":
        raise HarnessError("Configuration writes currently support macOS and Linux only")
    if ".." in path.parts:
        raise HarnessError("Parent traversal is not allowed in the destination")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(path.anchor or ".", flags)
    try:
        for part in path.parts:
            if part in (path.anchor, "."):
                continue
            try:
                os.mkdir(part, mode=0o755, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise
