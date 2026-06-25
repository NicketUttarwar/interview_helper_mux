"""Regression tests for run_guard directory lock recovery during write approval."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

import pytest

from interview_mux.run_context import RunContext
from interview_mux.web.runner import JobRunner, RunBusyError
from interview_mux.write_staging import (
    enter_stage_staging,
    exit_stage_staging,
    list_pending_paths,
)


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    root = tmp_path / "repo"
    executions = root / "ASSETS" / "executions"
    executions.mkdir(parents=True)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: root)
    monkeypatch.setattr(
        "interview_mux.run_context.merged_config",
        lambda: {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
            "journey_ui": {"require_write_approval_per_stage": True},
        },
    )
    monkeypatch.setattr(
        "interview_mux.write_staging.merged_config",
        lambda: {"journey_ui": {"require_write_approval_per_stage": True}},
    )
    rid = "exec_guard_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def test_run_guard_acquires_when_caller_holds_thread_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stale .run.lock must not block run_guard when only the caller holds thread_lock."""
    ctx = _ctx(tmp_path, monkeypatch)
    runner = JobRunner()
    lock = runner._lock_for(ctx.run_id)
    assert lock.acquire(blocking=False)
    try:
        from interview_mux.run_lock import RunDirectoryLock

        dir_lock = RunDirectoryLock(ctx.run_id)
        ctx.run_dir.joinpath(".run.lock").touch()
        assert runner._try_acquire_dir_lock(ctx.run_id, dir_lock, thread_lock=lock)
        dir_lock.release()
    finally:
        lock.release()


def test_run_guard_busy_when_other_thread_holds_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    runner = JobRunner()
    assert runner._acquire_thread_lock(ctx.run_id)
    lock = runner._lock_for(ctx.run_id)
    try:
        with pytest.raises(RunBusyError):
            with runner.run_guard(ctx.run_id):
                pass
    finally:
        runner._release_thread_lock(ctx.run_id, lock)


def test_large_wav_flush_under_run_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    runner = JobRunner()
    enter_stage_staging("audio_preclean")
    wav = ctx.path("preclean/isolated.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"\x00" * (10 << 20))
    ctx.path("preclean/lineage.json").write_text("{}", encoding="utf-8")
    exit_stage_staging()

    with runner.run_guard(ctx.run_id):
        paths = list_pending_paths(ctx, "audio_preclean")
        runner.mark_write_approval_saving(ctx, "audio_preclean", paths)
        from interview_mux.write_staging import approve_stage_writes

        flushed = approve_stage_writes(ctx, "audio_preclean")
    assert "preclean/isolated.wav" in flushed
    assert ctx.final_path("preclean/isolated.wav").is_file()
    assert not list_pending_paths(ctx, "audio_preclean")


def test_recovers_orphaned_thread_lock_when_holder_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stale in-process lock must not block save after pipeline thread exited without release."""
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.write_json(
        "gui_job.json",
        {
            "status": "awaiting_write_approval",
            "mode": "stage",
            "stage": "audio_preclean",
            "pending_write_stage": "audio_preclean",
            "pending_write_paths": ["preclean/lineage.json"],
        },
    )
    runner = JobRunner()
    lock = runner._lock_for(ctx.run_id)
    assert lock.acquire(blocking=False)
    runner._lock_holder_tid[ctx.run_id] = 0
    assert runner._recover_orphaned_thread_lock(ctx.run_id) is True
    with runner.operator_guard(ctx.run_id):
        pass
