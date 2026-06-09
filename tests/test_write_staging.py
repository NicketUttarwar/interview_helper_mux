from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.write_staging import (
    approve_stage_writes,
    discard_stage_writes,
    enter_stage_staging,
    exit_stage_staging,
    flush_stage_writes,
    has_pending_writes,
    list_pending_paths,
    run_wrapped_stage,
    write_approval_enabled,
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
        lambda: {
            "journey_ui": {"require_write_approval_per_stage": True},
        },
    )
    rid = "exec_001_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def test_staging_redirect_and_flush(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("ingest")
    try:
        note = ctx.path("ingest/staging_note.txt")
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text("staged", encoding="utf-8")
    finally:
        exit_stage_staging()
    assert has_pending_writes(ctx, "ingest")
    assert not ctx.final_path("ingest", "staging_note.txt").is_file()
    flushed = flush_stage_writes(ctx, "ingest")
    assert "ingest/staging_note.txt" in flushed
    assert ctx.final_path("ingest", "staging_note.txt").is_file()


def test_approve_marks_stage_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("ingest")
    note = ctx.path("ingest/staging_note.txt")
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("staged", encoding="utf-8")
    exit_stage_staging()
    approve_stage_writes(ctx, "ingest")
    assert ctx.is_done("ingest")


def test_discard_removes_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("ingest")
    note = ctx.path("ingest/staging_note.txt")
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("staged", encoding="utf-8")
    exit_stage_staging()
    discard_stage_writes(ctx, "ingest")
    assert not list_pending_paths(ctx, "ingest")
