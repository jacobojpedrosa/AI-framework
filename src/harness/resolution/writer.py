"""Explicitly approved configuration writes, with snapshots and backups."""

import os
import secrets
import stat
from contextlib import suppress
from pathlib import Path

from harness.config.loader import MAX_BYTES
from harness.errors import HarnessError
from harness.filesystem import open_directory


def _read_snapshot(directory: int, name: str) -> tuple[bytes, os.stat_result]:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise HarnessError("Update target must be a regular file")
        data = stream.read(MAX_BYTES + 1)
    return data, metadata


def _create(directory: int, name: str, payload: bytes, mode: int = 0o600) -> None:
    descriptor = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=directory
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        os.unlink(name, dir_fd=directory)
        raise


def write_configuration(path: Path, payload: bytes, expected: bytes | None = None) -> Path | None:
    """Create exclusively, or replace only a reviewed snapshot; return backup path.

    Lock serializes harness writers. External editors do not honor this lock;
    a final content/inode check detects changes before replacement, but cannot
    offer a filesystem-wide compare-and-swap against hostile concurrent writers.
    """
    if not path.name or path.name in (".", ".."):
        raise HarnessError("Output must name a configuration file")
    directory: int | None = None
    locked = False
    temporary: str | None = None
    lock_name = f".{path.name}.harness-lock"
    try:
        directory = open_directory(path.parent)
        lock_fd = os.open(
            lock_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        os.close(lock_fd)
        locked = True
        if expected is None:
            _create(directory, path.name, payload, 0o644)
            return None
        actual, metadata = _read_snapshot(directory, path.name)
        if actual != expected:
            raise HarnessError("Configuration changed after planning; review a fresh proposal")
        if actual == payload:
            return None
        backup_name = f"{path.name}.backup-{secrets.token_hex(8)}"
        _create(directory, backup_name, actual)
        pending_name = f".{path.name}.pending-{secrets.token_hex(8)}"
        _create(directory, pending_name, payload, stat.S_IMODE(metadata.st_mode))
        temporary = pending_name
        current, current_metadata = _read_snapshot(directory, path.name)
        if current != expected or current_metadata.st_ino != metadata.st_ino:
            raise HarnessError("Configuration changed during preparation; original left untouched")
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        temporary = None
        return path.with_name(backup_name)
    except FileExistsError:
        raise HarnessError("Output or write lock already exists; nothing was overwritten") from None
    except OSError:
        raise HarnessError(
            "Cannot write configuration; check permissions and symlink-free paths"
        ) from None
    finally:
        if directory is not None:
            try:
                if temporary is not None:
                    with suppress(OSError):
                        os.unlink(temporary, dir_fd=directory)
            finally:
                try:
                    if locked:
                        with suppress(OSError):
                            os.unlink(lock_name, dir_fd=directory)
                finally:
                    os.close(directory)
