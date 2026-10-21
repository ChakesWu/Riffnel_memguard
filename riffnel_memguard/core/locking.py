"""A cross-process exclusive file lock (POSIX flock, Windows msvcrt) and an atomic file write."""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl  # POSIX
except ImportError:  # pragma: no cover - Windows
    fcntl = None
    import msvcrt


class LockTimeout(TimeoutError):
    """Another process held the workspace lock for too long."""


@contextmanager
def file_lock(path: str | Path, timeout: float = 60.0):
    """Hold an exclusive lock on `path` (created if missing). Not re-entrant: do not nest it in one process."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                if fcntl:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:  # pragma: no cover - Windows
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise LockTimeout(f"could not lock {path} within {timeout:g}s: another riffnel-memguard command is running")
                time.sleep(0.05)
        yield
    finally:
        try:
            if fcntl:
                fcntl.flock(fd, fcntl.LOCK_UN)
            else:  # pragma: no cover - Windows
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(fd)


def atomic_write(path: str | Path, data: str | bytes, mode: int = 0o600) -> None:
    """Write to a temporary file in the same directory, flush it to disk, then rename over the target.

    A crash leaves either the old file or the new one, never a half-written file.
    """
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    raw = data.encode("utf-8") if isinstance(data, str) else data
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
