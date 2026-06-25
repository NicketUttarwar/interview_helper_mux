"""GUI operator actions recover stale locks and wait for pause handoff."""

from __future__ import annotations

from pathlib import Path
from threading import Lock, Thread
import time

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
    rid = "exec_operator_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def test_operator_guard_recovers_stale_write_approval_running_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("audio_preclean")
    wav = ctx.path("preclean/isolated.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"wav")
    exit_stage_staging()
    ctx.write_json(
        "gui_job.json",
        {
            "status": "running",
            "mode": "write_approval",
            "stage": "audio_preclean",
            "pending_write_stage": "audio_preclean",
            "pending_write_paths": ["preclean/isolated.wav"],
        },
    )
    runner = JobRunner()
    lock = runner._lock_for(ctx.run_id)
    assert lock.acquire(blocking=False)
    runner._lock_holder_tid[ctx.run_id] = 0
    try:
        with runner.operator_guard(ctx.run_id):
            pass
    finally:
        if lock.locked():
            lock.release()
    job = ctx.read_json("gui_job.json")
    assert job["status"] == "awaiting_write_approval"


def test_approve_write_after_orphaned_lock_with_awaiting_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("audio_preclean")
    iso = ctx.path("preclean/isolated.wav")
    iso.parent.mkdir(parents=True, exist_ok=True)
    iso.write_bytes(b"wav")
    ctx.path("preclean/lineage.json").write_text("{}", encoding="utf-8")
    exit_stage_staging()
    ctx.write_json(
        "gui_job.json",
        {
            "status": "awaiting_write_approval",
            "mode": "stage",
            "stage": "audio_preclean",
            "pending_write_stage": "audio_preclean",
            "pending_write_paths": ["preclean/isolated.wav", "preclean/lineage.json"],
            "awaiting_write_approval": True,
        },
    )
    runner = JobRunner()
    lock = runner._lock_for(ctx.run_id)
    assert lock.acquire(blocking=False)
    runner._lock_holder_tid[ctx.run_id] = 0
    try:
        result = runner.approve_write_and_continue(ctx.run_id, "audio_preclean")
    finally:
        if lock.locked():
            lock.release()
    assert result["ok"] is True
    assert not list_pending_paths(ctx, "audio_preclean")


def test_operator_guard_waits_for_pause_lock_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    runner = JobRunner()
    lock = runner._lock_for(ctx.run_id)
    assert lock.acquire(blocking=False)
    runner._record_lock_holder(ctx.run_id)
    ctx.write_json(
        "gui_job.json",
        {
            "status": "awaiting_write_approval",
            "stage": "audio_preclean",
            "awaiting_write_approval": True,
        },
    )
    released: list[bool] = []

    def _release_later() -> None:
        time.sleep(0.15)
        runner._release_thread_lock(ctx.run_id, lock)
        released.append(True)

    Thread(target=_release_later, daemon=True).start()
    with runner.operator_guard(ctx.run_id):
        pass
    assert released


def test_run_guard_still_busy_for_live_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    runner = JobRunner()
    lock = runner._lock_for(ctx.run_id)
    assert lock.acquire(blocking=False)
    runner._record_lock_holder(ctx.run_id)
    ctx.write_json(
        "gui_job.json",
        {"status": "running", "stage": "ingest", "mode": "stage", "message": "Running ingest…"},
    )
    try:
        with pytest.raises(RunBusyError):
            with runner.run_guard(ctx.run_id, operator_priority=True):
                pass
    finally:
        runner._release_thread_lock(ctx.run_id, lock)
