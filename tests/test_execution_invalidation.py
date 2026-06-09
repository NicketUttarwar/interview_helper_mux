from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.pipeline import ANALYSIS_ORDER
from interview_mux.run_context import RunContext
from interview_mux.write_staging import (
    check_write_approval_before_execute,
    enter_stage_staging,
    exit_stage_staging,
)


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


def test_clear_from_archives_and_clears_pending_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    checksums = ctx.path("ingest/checksums.json")
    checksums.parent.mkdir(parents=True, exist_ok=True)
    checksums.write_text("{}", encoding="utf-8")
    ctx.mark_done("ingest", force=True)
    boundaries = ctx.final_path("segments/boundaries.json")
    boundaries.parent.mkdir(parents=True, exist_ok=True)
    boundaries.write_text("{}", encoding="utf-8")
    ctx.mark_done("boundary_detection", force=True)
    enter_stage_staging("segment_classification")
    manifest = ctx.path("segments/manifest.json")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("{}", encoding="utf-8")
    exit_stage_staging()
    assert check_write_approval_before_execute(ctx) is not None

    ctx.clear_from("boundary_detection", ANALYSIS_ORDER)

    assert not ctx.final_path("segments/boundaries.json").is_file()
    assert check_write_approval_before_execute(ctx) is None
    assert list(ctx.run_dir.glob(".archived/*"))


def test_discard_on_invalidate_unblocks_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("ingest")
    note = ctx.path("ingest/note.txt")
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("x", encoding="utf-8")
    exit_stage_staging()
    assert check_write_approval_before_execute(ctx) is not None
    ctx.clear_from("ingest", ANALYSIS_ORDER)
    assert check_write_approval_before_execute(ctx) is None
