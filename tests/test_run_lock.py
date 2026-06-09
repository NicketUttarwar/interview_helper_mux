from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.run_lock import RunDirectoryLock


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    root = tmp_path / "repo"
    (root / "ASSETS" / "executions").mkdir(parents=True)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: root)
    monkeypatch.setattr(
        "interview_mux.run_context.merged_config",
        lambda: {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
        },
    )
    rid = "exec_001_20260101T000000Z"
    return RunContext(rid, create=True)


def test_run_directory_lock_acquire_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    lock = RunDirectoryLock(ctx.run_id)
    assert lock.acquire(blocking=False)
    assert not RunDirectoryLock(ctx.run_id).acquire(blocking=False)
    lock.release()
    assert RunDirectoryLock(ctx.run_id).acquire(blocking=False)
