"""gui_job reconcile restores awaiting_write_approval after interrupted saves."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.gui_job_reconcile import reconcile_job_if_stale
from interview_mux.run_context import RunContext
from interview_mux.write_staging import enter_stage_staging, exit_stage_staging


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
        },
    )
    monkeypatch.setattr(
        "interview_mux.write_staging.merged_config",
        lambda: {"journey_ui": {"require_write_approval_per_stage": True}},
    )
    rid = "exec_reconcile_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    return ctx


def test_reconcile_write_approval_running_to_awaiting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
            "message": "Saving…",
        },
    )
    job = reconcile_job_if_stale(ctx.run_id, lock_held=False)
    assert job["status"] == "awaiting_write_approval"
    assert job.get("pending_write_stage") == "audio_preclean"
    assert job.get("mode") == "stage"
