from __future__ import annotations

import os

from interview_mux.process_cleanup import track_worker_pid, untrack_worker_pid, worker_pid_alive


def test_worker_pid_alive_current_process() -> None:
    assert worker_pid_alive(os.getpid()) is True


def test_worker_pid_alive_missing() -> None:
    assert worker_pid_alive(None) is False
    assert worker_pid_alive(999_999_999) is False


def test_track_worker_pid_round_trip() -> None:
    pid = os.getpid()
    track_worker_pid(pid)
    try:
        assert worker_pid_alive(pid) is True
    finally:
        untrack_worker_pid(pid)
