"""Pipeline worker must own run locks so write-approval save can acquire after execute."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.web.runner import JobRunner, RunBusyError
from interview_mux.write_staging import (
    WriteApprovalPending,
    enter_stage_staging,
    exit_stage_staging,
    list_pending_paths,
)
from run_fixtures import minimal_preclean_lineage, minimal_preclean_provider


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
    rid = "exec_handoff_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def _wait_until(predicate, *, timeout_s: float = 3.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not met before timeout")


def test_execute_write_approval_then_save_releases_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    runner = JobRunner()

    def _raise_write_approval(run_ctx: RunContext, stage: str, from_stage: str | None) -> None:
        enter_stage_staging(stage)
        wav = run_ctx.path("preclean/isolated.wav")
        wav.parent.mkdir(parents=True, exist_ok=True)
        wav.write_bytes(b"wav")
        run_ctx.write_json("preclean/lineage.json", minimal_preclean_lineage())
        run_ctx.write_json("preclean/provider.json", minimal_preclean_provider())
        exit_stage_staging()
        raise WriteApprovalPending(stage, list_pending_paths(run_ctx, stage))

    monkeypatch.setattr(runner, "_execute_single_stage", _raise_write_approval)

    result = runner.start(
        ctx.run_id,
        mode="stage",
        stage="audio_preclean",
        api_consents={},
    )
    assert result.get("ok") is True

    _wait_until(lambda: not runner.lock_held(ctx.run_id) and not runner.is_running(ctx.run_id))

    job = ctx.read_json("gui_job.json")
    assert job["status"] in ("awaiting_write_approval", "complete")
    if job["status"] == "awaiting_write_approval":
        assert job["pending_write_stage"] == "audio_preclean"
        save = runner.approve_write_and_continue(ctx.run_id, "audio_preclean")
        assert save["ok"] is True
        assert not list_pending_paths(ctx, "audio_preclean")


def test_orphaned_lock_without_holder_tid_recovers_for_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("audio_preclean")
    iso = ctx.path("preclean/isolated.wav")
    iso.parent.mkdir(parents=True, exist_ok=True)
    iso.write_bytes(b"wav")
    exit_stage_staging()
    ctx.write_json(
        "gui_job.json",
        {
            "status": "awaiting_write_approval",
            "mode": "stage",
            "stage": "audio_preclean",
            "pending_write_stage": "audio_preclean",
            "pending_write_paths": ["preclean/isolated.wav"],
            "awaiting_write_approval": True,
        },
    )
    runner = JobRunner()
    lock = runner._lock_for(ctx.run_id)
    assert lock.acquire(blocking=False)
    # Simulate HTTP-thread leak: lock held but holder metadata cleared.
    try:
        result = runner.approve_write_and_continue(ctx.run_id, "audio_preclean")
    finally:
        if lock.locked():
            lock.release()
    assert result["ok"] is True
