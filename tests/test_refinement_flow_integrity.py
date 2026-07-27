"""Flow integrity — skip-copy guarantees the delivery pipeline never dead-ends."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.refinement_flow_integrity import (
    DRAFT_REL,
    FINAL_REL,
    SKIP_COPY_REL,
    dual_write_draft_from_compose,
    ensure_gap_report_authoritative,
    g1_reachable,
    skip_copy_draft_to_final,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return isolated_run_ctx(tmp_path, "exec_flow_integrity_test")


def _line(line_id: str) -> dict[str, str]:
    """Minimal interviewer_line satisfying gap_report.schema.json's required fields."""
    return {
        "line_id": line_id,
        "gap_type": "missing_setup",
        "text": "Sample framing line.",
        "targets_segment_id": "seg_001",
        "placement": "before",
        "delivery": "record",
    }


def test_skip_copy_writes_empty_valid_report_when_nothing_exists(ctx: RunContext) -> None:
    report = skip_copy_draft_to_final(ctx, reason="pass2_skipped")
    assert report["interviewer_lines"] == []
    assert ctx.artifact_exists(FINAL_REL)
    assert ctx.artifact_exists(DRAFT_REL)
    assert ctx.artifact_exists(SKIP_COPY_REL)
    marker = ctx.read_json(SKIP_COPY_REL)
    assert marker["reason"] == "pass2_skipped"


def test_skip_copy_promotes_draft_to_final(ctx: RunContext) -> None:
    ctx.write_json(DRAFT_REL, {"interviewer_lines": [_line("vo_1")]})
    report = skip_copy_draft_to_final(ctx)
    assert report["interviewer_lines"][0]["line_id"] == "vo_1"
    on_disk = ctx.read_json(FINAL_REL)
    assert on_disk["interviewer_lines"][0]["line_id"] == "vo_1"


def test_ensure_gap_report_authoritative_prefers_existing_final(ctx: RunContext) -> None:
    ctx.write_json(FINAL_REL, {"interviewer_lines": [_line("vo_final")]})
    doc = ensure_gap_report_authoritative(ctx)
    assert doc["interviewer_lines"][0]["line_id"] == "vo_final"
    # No skip-copy marker needed — final already existed.
    assert not ctx.artifact_exists(SKIP_COPY_REL)


def test_ensure_gap_report_authoritative_falls_back_to_skip_copy(ctx: RunContext) -> None:
    assert not ctx.artifact_exists(FINAL_REL)
    doc = ensure_gap_report_authoritative(ctx)
    assert doc["interviewer_lines"] == []
    assert ctx.artifact_exists(FINAL_REL)
    assert ctx.artifact_exists(SKIP_COPY_REL)


def test_g1_reachable_is_always_true_even_with_no_artifacts(ctx: RunContext) -> None:
    assert g1_reachable(ctx) is True
    assert ctx.artifact_exists(FINAL_REL)


def test_g1_reachable_true_when_lines_already_exist(ctx: RunContext) -> None:
    ctx.write_json(FINAL_REL, {"interviewer_lines": [_line("vo_1")]})
    assert g1_reachable(ctx) is True
    doc = ctx.read_json(FINAL_REL)
    assert len(doc["interviewer_lines"]) == 1


def test_dual_write_draft_from_compose_snapshots_final_as_draft(ctx: RunContext) -> None:
    ctx.write_json(FINAL_REL, {"interviewer_lines": [_line("vo_c")]})
    assert not ctx.artifact_exists(DRAFT_REL)
    dual_write_draft_from_compose(ctx)
    assert ctx.artifact_exists(DRAFT_REL)
    assert ctx.read_json(DRAFT_REL)["interviewer_lines"][0]["line_id"] == "vo_c"
