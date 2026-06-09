"""Cross-process mutex for a single execution directory."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from filelock import FileLock, Timeout

from interview_mux.run_context import RunContext


class RunDirectoryLock:
    """FileLock on {run_dir}/.run.lock — serializes CLI, GUI jobs, and mutating API calls."""

    def __init__(self, run_id: str, *, create: bool = False) -> None:
        self._ctx = RunContext(run_id, create=create)
        self._lock_path = self._ctx.run_dir / ".run.lock"
        self._lock = FileLock(str(self._lock_path), timeout=-1)

    @property
    def run_dir(self) -> Path:
        return self._ctx.run_dir

    def acquire(self, *, blocking: bool = True) -> bool:
        try:
            if blocking:
                self._lock.acquire()
            else:
                return bool(self._lock.acquire(blocking=False))
            return True
        except Timeout:
            return False

    def release(self) -> None:
        if self._lock.is_locked:
            self._lock.release()

    def __enter__(self) -> RunDirectoryLock:
        self.acquire(blocking=True)
        return self

    def __exit__(self, *args: object) -> None:
        self.release()


@contextmanager
def run_directory_lock(
    run_id: str,
    *,
    create: bool = False,
    blocking: bool = True,
) -> Iterator[RunDirectoryLock]:
    lock = RunDirectoryLock(run_id, create=create)
    if not lock.acquire(blocking=blocking):
        raise Timeout(f"Run {run_id} is busy")
    try:
        yield lock
    finally:
        lock.release()
