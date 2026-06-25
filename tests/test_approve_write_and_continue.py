"""Regression tests for atomic write approval + pipeline continue."""

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
    rid = "exec_atomic_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def test_approve_write_and_continue_flushes_without_auto_starting_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    runner = JobRunner()
    enter_stage_staging("audio_preclean")
    iso = ctx.path("preclean/isolated.wav")
    iso.parent.mkdir(parents=True, exist_ok=True)
    iso.write_bytes(b"wav")
    ctx.path("preclean/lineage.json").write_text("{}", encoding="utf-8")
    exit_stage_staging()

    spawned: list[str] = []
    original_spawn = runner._spawn_pipeline_thread

    def _track_spawn(run_id: str, **kwargs: object) -> None:
        spawned.append(str(kwargs.get("stage")))
        original_spawn(run_id, **kwargs)

    monkeypatch.setattr(runner, "_spawn_pipeline_thread", _track_spawn)

    result = runner.approve_write_and_continue(ctx.run_id, "audio_preclean")
    assert result["ok"] is True
    assert result["started_stage"] == "ingest"
    assert not list_pending_paths(ctx, "audio_preclean")
    assert ctx.is_done("audio_preclean")
    assert spawned == []


def test_approve_write_and_continue_busy_when_lock_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    runner = JobRunner()
    lock = runner._lock_for(ctx.run_id)
    assert runner._acquire_thread_lock(ctx.run_id)
    try:
        with pytest.raises(RunBusyError):
            runner.approve_write_and_continue(ctx.run_id, "audio_preclean")
    finally:
        runner._release_thread_lock(ctx.run_id, lock)
