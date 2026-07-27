"""Champion accept — noop guard, feasibility, rubric compare, promote, cascade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from interview_mux.refinement_accept import accept_gap_recompose
from interview_mux.refinement_cascade import load_cascade
from interview_mux.refinement_champion import load_champion
from interview_mux.refinement_flow_integrity import DRAFT_REL, FINAL_REL
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return isolated_run_ctx(tmp_path, "exec_accept_test")


def _line(line_id: str, target: str, *, text: str = "Hello", **extra: Any) -> dict[str, Any]:
    """Minimal interviewer_line satisfying gap_report.schema.json's required fields."""
    return {
        "line_id": line_id,
        "gap_type": "missing_setup",
        "text": text,
        "targets_segment_id": target,
        "placement": "before",
        "delivery": "record",
        **extra,
    }


def test_identical_candidate_is_noop_and_draft_stays_authoritative(ctx: RunContext) -> None:
    draft = {"interviewer_lines": [_line("vo_1", "seg_1")]}
    ctx.write_json(DRAFT_REL, draft)
    result = accept_gap_recompose(ctx, {"interviewer_lines": [_line("vo_1", "seg_1")]})
    assert result["accepted"] is False
    assert result["reason_code"] == "noop"
    assert ctx.read_json(FINAL_REL)["interviewer_lines"][0]["line_id"] == "vo_1"


def test_candidate_targeting_dropped_segment_is_rejected_as_orphan(ctx: RunContext) -> None:
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_1"]})
    result = accept_gap_recompose(ctx, {"interviewer_lines": [_line("vo_x", "seg_2")]})
    assert result["accepted"] is False
    assert result["reason_code"] == "feasibility_orphans"
    assert result["orphans"] == 1


def test_meaningful_candidate_accepted_and_champion_promoted(ctx: RunContext) -> None:
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_1"]})
    ctx.write_json(DRAFT_REL, {"interviewer_lines": [_line("vo_1", "seg_1", text="Hi")]})
    candidate = {"interviewer_lines": [_line("vo_1", "seg_1", text="Hi there, welcome back")]}

    result = accept_gap_recompose(ctx, candidate)

    assert result["accepted"] is True
    assert result["reason_code"] == "accepted"
    final = ctx.read_json(FINAL_REL)
    assert final["interviewer_lines"][0]["text"] == "Hi there, welcome back"
    champion = load_champion(ctx, "gap_vo")
    assert champion is not None
    assert champion["source"] == "gap_framing_recompose"
    cascade = load_cascade(ctx)
    assert cascade is not None
    assert "vo_1" in cascade["line_ids_changed"]
    assert cascade["remix_after_edl"] is True


def test_worse_candidate_rejected_by_rubric_and_draft_stays_authoritative(
    ctx: RunContext,
) -> None:
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_1"]})
    draft = {
        "interviewer_lines": [
            _line("vo_1", "seg_1", text="Hi there", line_category="episode_preface")
        ]
    }
    ctx.write_json(DRAFT_REL, draft)
    long_text = " ".join(["word"] * 200)
    candidate = {"interviewer_lines": [_line("vo_1", "seg_1", text=long_text)]}

    result = accept_gap_recompose(ctx, candidate)

    assert result["accepted"] is False
    assert result["reason_code"] == "rejected_rubric"
    assert ctx.read_json(FINAL_REL)["interviewer_lines"][0]["text"] == "Hi there"
    # Rejected candidate must not become the champion.
    assert load_champion(ctx, "gap_vo") is None


def test_operator_pinned_lines_survive_recompose(ctx: RunContext) -> None:
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_1", "seg_2"]})
    draft = {
        "interviewer_lines": [
            _line("vo_pin", "seg_2", text="Pinned operator line", origin="operator"),
            _line("vo_1", "seg_1", text="Hi"),
        ]
    }
    ctx.write_json(DRAFT_REL, draft)
    candidate = {"interviewer_lines": [_line("vo_1", "seg_1", text="Hi there now")]}

    result = accept_gap_recompose(ctx, candidate)

    assert result["accepted"] is True
    final_ids = {line["line_id"] for line in ctx.read_json(FINAL_REL)["interviewer_lines"]}
    assert "vo_pin" in final_ids
    assert "vo_1" in final_ids


def test_no_draft_and_no_ordering_defaults_to_empty_draft(ctx: RunContext) -> None:
    """No draft artifact and no selection — candidate with any line is meaningful and unconstrained."""
    result = accept_gap_recompose(ctx, {"interviewer_lines": [_line("vo_new", "seg_1")]})
    assert result["reason_code"] in ("accepted", "rejected_rubric")
