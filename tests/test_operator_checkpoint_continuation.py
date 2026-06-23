"""Regression tests for checkpoint continuation API."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
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


def test_preclean_approve_clears_pending_and_marks_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.write_staging import approve_stage_writes

    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("audio_preclean")
    iso = ctx.path("preclean/isolated.wav")
    iso.parent.mkdir(parents=True, exist_ok=True)
    iso.write_bytes(b"wav")
    ctx.path("preclean/lineage.json").write_text("{}", encoding="utf-8")
    ctx.path("preclean/provider.json").write_text("{}", encoding="utf-8")
    exit_stage_staging()
    assert list_pending_paths(ctx, "audio_preclean")
    flushed = approve_stage_writes(ctx, "audio_preclean")
    assert len(flushed) == 3
    assert not list_pending_paths(ctx, "audio_preclean")
    assert ctx.is_done("audio_preclean")
    assert ctx.final_path("preclean", "isolated.wav").is_file()
