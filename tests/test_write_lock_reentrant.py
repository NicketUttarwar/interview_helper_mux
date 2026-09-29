"""The shared directory write lock must be reentrant within a process.

filelock builds a fresh instance per call and, since 3.13, raises Deadlock when
a second instance for the same path is acquired while another is held by the
same thread. On a real 6-minute run a run-root lock instance leaked inside the
traversal process and every later write, and every gate sign-off, failed with:

    Deadlock: lock ".write.lock" is already held by a different FileLock instance

write_lock uses is_singleton=True, the library's documented remedy.
"""

from __future__ import annotations

from interview_mux.file_store import read_json, write_json, write_lock


def test_nested_same_path_lock_in_one_thread_does_not_deadlock(tmp_path) -> None:
    target = tmp_path / "run_meta.json"
    with write_lock(target):
        with write_lock(target):  # a second instance for the same path
            write_json(target, {"ok": 1})  # and a third, inside the helper
    assert read_json(target) == {"ok": 1}


def test_stale_held_handle_does_not_wedge_later_writes(tmp_path) -> None:
    """A handle acquired and never released must not block the same thread."""
    target = tmp_path / "doc.json"
    stale = write_lock(target)
    stale.acquire()
    try:
        write_json(target, {"after": "stale"})
        assert read_json(target) == {"after": "stale"}
    finally:
        stale.release()


def test_lock_is_still_per_directory(tmp_path) -> None:
    a = write_lock(tmp_path / "x" / "a.json")
    b = write_lock(tmp_path / "y" / "b.json")
    assert a.lock_file != b.lock_file
    assert write_lock(tmp_path / "x" / "c.json") is a, "one instance per directory lock"
