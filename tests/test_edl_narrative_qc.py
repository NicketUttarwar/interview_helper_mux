from __future__ import annotations

import pytest

from interview_mux.edl_narrative_qc import validate_flow1_edl_narrative
from interview_mux.gates import check_edl_narrative_qc
from interview_mux.operator_quality import qc_summary
from interview_mux.run_context import RunContext
from run_fixtures import minimal_gap_line, minimal_gap_report


def _write_story_artifacts(ctx: RunContext) -> None:
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_a", "seg_b", "seg_c"],
            "chapters": [
                {"title": "Setup", "segment_ids": ["seg_a", "seg_b"]},
                {"title": "Payoff", "segment_ids": ["seg_c"]},
            ],
            "excluded_segment_ids": [{"segment_id": "seg_x", "reason": "aside"}],
        },
    )
    ctx.write_json(
        "master/coverage_audit.json",
        {
            "coverage_score": 1.0,
            "topic_mappings": [
                {"topic": "Origins", "covered": True, "segment_ids": ["seg_a"]},
                {"topic": "Breakthrough", "covered": True, "segment_ids": ["seg_c"]},
            ],
            "claim_mappings": [
                {"claim": "The launch changed the team", "covered": True, "segment_ids": ["seg_c"]}
            ],
            "missing_coverage": [],
        },
    )
    ctx.write_json(
        "master/narrative_plan.json",
        {
            "arc_summary": "Setup before payoff.",
            "chapters": [
                {"chapter_id": "ch_01", "title": "Setup", "suggested_open_segment_id": "seg_a"},
                {"chapter_id": "ch_02", "title": "Payoff", "suggested_open_segment_id": "seg_c"},
            ],
            "ordering_constraints": [
                {"before_segment_id": "seg_a", "after_segment_id": "seg_c", "reason": "setup before payoff"}
            ],
        },
    )
    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "after_segment_id": "seg_b",
                    "before_segment_id": "seg_c",
                    "text": "That set up the turning point.",
                    "type": "chapter",
                }
            ]
        },
    )
    ctx.write_json(
        "understanding/gap_report.json",
        minimal_gap_report(
            minimal_gap_line(
                line_id="line_001",
                targets_segment_id="seg_b",
                placement="before",
                delivery="record",
            )
        ),
    )
    ctx.write_json(
        "master/edl_narrative_audit.json",
        {
            "verdict": "pass",
            "blocking_issues": [],
            "warnings": [],
            "recommended_actions": [],
            "reasoning_summary": "Pass.",
        },
    )


def _good_edl() -> dict:
    return {
        "version": 1,
        "ordered_segment_ids": ["seg_a", "seg_b", "seg_c"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_a",
                "source_start_ms": 0,
                "source_end_ms": 1000,
                "timeline_start_ms": 0,
                "duration_ms": 1000,
            },
            {
                "type": "vo_pickup",
                "line_id": "line_001",
                "targets_segment_id": "seg_b",
                "placement": "before",
                "timeline_start_ms": 1000,
                "duration_ms": 0,
            },
            {
                "type": "speech",
                "segment_id": "seg_b",
                "source_start_ms": 1000,
                "source_end_ms": 2000,
                "timeline_start_ms": 1000,
                "duration_ms": 1000,
            },
            {
                "type": "transition",
                "after_segment_id": "seg_b",
                "before_segment_id": "seg_c",
                "text": "That set up the turning point.",
                "transition_type": "chapter",
                "timeline_start_ms": 2000,
                "duration_ms": 0,
            },
            {
                "type": "speech",
                "segment_id": "seg_c",
                "source_start_ms": 2000,
                "source_end_ms": 3000,
                "timeline_start_ms": 2000,
                "duration_ms": 1000,
            },
        ],
        "gap_placements": [
            {"line_id": "line_001", "targets_segment_id": "seg_b", "placement": "before", "timeline_start_ms": 1000}
        ],
        "timeline_duration_ms": 3000,
        "warnings": {"missing_vo_files": ["line_001"], "gap_targets_not_in_selection": []},
    }


def test_validate_flow1_edl_narrative_passes() -> None:
    ctx = RunContext("run_edl_narrative_ok", create=True)
    _write_story_artifacts(ctx)
    assert validate_flow1_edl_narrative(ctx, _good_edl()) == []


def test_validate_flow1_edl_narrative_catches_coverage_loss() -> None:
    ctx = RunContext("run_edl_narrative_coverage_loss", create=True)
    _write_story_artifacts(ctx)
    edl = _good_edl()
    edl["ordered_segment_ids"] = ["seg_a", "seg_b"]
    edl["clips"] = [c for c in edl["clips"] if c.get("segment_id") != "seg_c"]
    errors = validate_flow1_edl_narrative(ctx, edl)
    assert any("covered topic" in e and "Breakthrough" in e for e in errors)


def test_validate_flow1_edl_narrative_catches_ordering_constraint() -> None:
    ctx = RunContext("run_edl_narrative_ordering", create=True)
    _write_story_artifacts(ctx)
    edl = _good_edl()
    edl["ordered_segment_ids"] = ["seg_c", "seg_a", "seg_b"]
    for idx, sid in enumerate(["seg_c", "seg_a", "seg_b"]):
        speech = [c for c in edl["clips"] if c.get("type") == "speech"][idx]
        speech["segment_id"] = sid
    errors = validate_flow1_edl_narrative(ctx, edl)
    assert any("ordering constraint violated" in e for e in errors)


def test_check_edl_narrative_qc_records_summary(monkeypatch) -> None:
    ctx = RunContext("run_edl_narrative_summary", create=True)
    _write_story_artifacts(ctx)
    monkeypatch.setattr(
        "interview_mux.gates.merged_config",
        lambda: {"edl_narrative_qc": {"strict": True}},
    )
    check_edl_narrative_qc(ctx, stage="edl", edl=_good_edl())
    summary = qc_summary(ctx.read_json("run_meta.json"), "edl_narrative_qc")
    assert summary is not None
    assert summary["passed"] is True
    assert summary["at_stage"] == "edl"


def test_check_edl_narrative_qc_strict_raises(monkeypatch) -> None:
    ctx = RunContext("run_edl_narrative_strict", create=True)
    _write_story_artifacts(ctx)
    monkeypatch.setattr(
        "interview_mux.gates.merged_config",
        lambda: {"edl_narrative_qc": {"strict": True}},
    )
    edl = _good_edl()
    edl["clips"] = [c for c in edl["clips"] if c.get("segment_id") != "seg_c"]
    with pytest.raises(SystemExit, match="edl_narrative_qc strict"):
        check_edl_narrative_qc(ctx, stage="edl", edl=edl)
