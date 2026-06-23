"""Regression tests for continue-after-checkpoint write approval API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interview_mux.run_context import RunContext
from interview_mux.web.runner import JobRunner
from interview_mux.write_staging import enter_stage_staging, exit_stage_staging, list_pending_paths


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
    rid = "exec_001_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def test_mark_write_approval_saving_sets_running_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    runner = JobRunner()
    paths = ["preclean/isolated.wav", "preclean/lineage.json"]
    runner.mark_write_approval_saving(ctx, "audio_preclean", paths)
    job = ctx.read_json("gui_job.json")
    assert job["status"] == "running"
    assert job["mode"] == "write_approval"
    assert "Saving 2 file" in job["message"]


def test_continue_after_checkpoint_flushes_and_starts_ingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.web.server import create_app

    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("audio_preclean")
    iso = ctx.path("preclean/isolated.wav")
    iso.parent.mkdir(parents=True, exist_ok=True)
    iso.write_bytes(b"wav")
    ctx.path("preclean/lineage.json").write_text("{}", encoding="utf-8")
    ctx.path("preclean/provider.json").write_text("{}", encoding="utf-8")
    exit_stage_staging()
    assert list_pending_paths(ctx, "audio_preclean")

    monkeypatch.setattr(
        "interview_mux.web.server.runner.start",
        lambda *a, **k: {"ok": True, "run_id": ctx.run_id, "mode": "stage", "stage": "ingest"},
    )

    client = TestClient(create_app())
    res = client.post(
        f"/api/runs/{ctx.run_id}/continue-after-checkpoint",
        json={"kind": "write_approval", "stage_id": "audio_preclean"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["started_stage"] == "ingest"
    assert not list_pending_paths(ctx, "audio_preclean")
    assert ctx.is_done("audio_preclean")
    assert ctx.final_path("preclean", "isolated.wav").is_file()
