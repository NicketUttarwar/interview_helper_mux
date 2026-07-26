"""Regression tests for write-approval flush + continue after preclean checkpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interview_mux.run_context import RunContext
from interview_mux.web.runner import JobRunner
from interview_mux.write_staging import (
    approve_stage_writes,
    enter_stage_staging,
    exit_stage_staging,
    list_pending_paths,
)
from run_fixtures import minimal_preclean_lineage, minimal_preclean_provider, patch_write_approval_enabled


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
    patch_write_approval_enabled(monkeypatch, enabled=True)
    rid = "exec_001_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def test_approve_stage_writes_under_run_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    runner = JobRunner()
    enter_stage_staging("audio_preclean")
    iso = ctx.path("preclean/isolated.wav")
    iso.parent.mkdir(parents=True, exist_ok=True)
    iso.write_bytes(b"wav")
    ctx.write_json("preclean/lineage.json", minimal_preclean_lineage())
    ctx.write_json("preclean/provider.json", minimal_preclean_provider())
    exit_stage_staging()
    paths = list_pending_paths(ctx, "audio_preclean")
    assert len(paths) == 3

    with runner.run_guard(ctx.run_id):
        flushed = approve_stage_writes(ctx, "audio_preclean")

    assert len(flushed) == 3
    assert ctx.final_path("preclean/isolated.wav").is_file()
    assert not list_pending_paths(ctx, "audio_preclean")


def test_flush_preclean_and_start_ingest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.web.server import create_app

    ctx = _ctx(tmp_path, monkeypatch)
    runner = JobRunner()
    enter_stage_staging("audio_preclean")
    iso = ctx.path("preclean/isolated.wav")
    iso.parent.mkdir(parents=True, exist_ok=True)
    iso.write_bytes(b"wav")
    ctx.write_json("preclean/lineage.json", minimal_preclean_lineage())
    ctx.write_json("preclean/provider.json", minimal_preclean_provider())
    exit_stage_staging()
    assert list_pending_paths(ctx, "audio_preclean")

    with runner.run_guard(ctx.run_id):
        approve_stage_writes(ctx, "audio_preclean")

    monkeypatch.setattr(
        "interview_mux.web.server.runner.start",
        lambda *a, **k: {"ok": True, "run_id": ctx.run_id, "mode": "stage", "stage": "ingest"},
    )

    client = TestClient(create_app())
    res = client.post(f"/api/runs/{ctx.run_id}/execute", json={"mode": "stage", "stage": "ingest"})
    assert res.status_code == 200, res.text
    assert not list_pending_paths(ctx, "audio_preclean")
    assert ctx.is_done("audio_preclean")
    assert ctx.final_path("preclean/isolated.wav").is_file()
