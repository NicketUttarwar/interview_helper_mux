"""Tests for talking-points-first deterministic coverage + narrative."""

from __future__ import annotations

from interview_mux.talking_points_authority import (
    coverage_from_talking_points,
    narrative_from_talking_points,
)


def test_coverage_from_talking_points_scores_must_keeps():
    tp = {
        "strategy_summary": "Test",
        "through_line": "Line",
        "talking_points": [
            {
                "talking_point_id": "tp_1",
                "title": "Must A",
                "importance": "must_keep",
                "why_it_matters": "x",
            },
            {
                "talking_point_id": "tp_2",
                "title": "Must B",
                "importance": "must_keep",
                "why_it_matters": "y",
            },
            {
                "talking_point_id": "tp_3",
                "title": "Optional",
                "importance": "optional",
                "why_it_matters": "z",
            },
        ],
    }
    mat = {
        "cuts": [
            {
                "cut_id": "c1",
                "talking_point_id": "tp_1",
                "segment_id": "seg_001",
                "start_ms": 0,
                "end_ms": 3000,
            }
        ]
    }
    cov = coverage_from_talking_points(tp, mat)
    assert cov["coverage_score"] == 0.5
    assert any(m["topic"] == "Must A" and m["covered"] for m in cov["topic_mappings"])
    assert any(m["topic"] == "Must B" and not m["covered"] for m in cov["topic_mappings"])
    assert any(m["item"] == "Must B" for m in cov["missing_coverage"])


def test_narrative_from_talking_points_builds_chapters():
    tp = {
        "strategy_summary": "Story",
        "through_line": "Through",
        "talking_points": [
            {
                "talking_point_id": "tp_1",
                "title": "Open",
                "importance": "must_keep",
                "why_it_matters": "x",
            },
            {
                "talking_point_id": "tp_2",
                "title": "Payoff",
                "importance": "should_keep",
                "why_it_matters": "y",
            },
        ],
    }
    mat = {
        "cuts": [
            {
                "cut_id": "c1",
                "talking_point_id": "tp_1",
                "segment_id": "seg_001",
                "start_ms": 100,
                "end_ms": 2000,
            },
            {
                "cut_id": "c2",
                "talking_point_id": "tp_2",
                "segment_id": "seg_002",
                "start_ms": 5000,
                "end_ms": 8000,
            },
        ]
    }
    plan = narrative_from_talking_points(
        tp,
        mat,
        mastering_plan={"narrative_mode": "guide_summary", "ordered_segment_ids": ["seg_001", "seg_002"]},
    )
    assert len(plan["chapters"]) == 2
    assert plan["chapters"][0]["suggested_open_segment_id"] == "seg_001"
    assert plan["ordering_constraints"]
    assert "guide_summary" in plan["arc_summary"]


def test_manifest_from_ideal_cuts_types_by_speaker_role(tmp_path):
    from interview_mux.run_context import RunContext
    from interview_mux.talking_points_authority import manifest_from_ideal_cuts
    from run_fixtures import isolated_run_ctx, patch_executions_root
    import pytest

    # Use a simple fake ctx via isolated fixture pattern
    monkeypatch = pytest.MonkeyPatch()
    patch_executions_root(monkeypatch, tmp_path)
    ctx = isolated_run_ctx(tmp_path, "exec_class_det")
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9, "evidence": ["q"]},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9, "evidence": ["a"]},
            ]
        },
        skip_handoff=True,
    )
    boundaries = {
        "boundaries": [
            {"segment_id": "seg_001", "start_ms": 0, "end_ms": 3000, "speaker_id": "spk_1"},
            {"segment_id": "seg_002", "start_ms": 4000, "end_ms": 7000, "speaker_id": "spk_0"},
        ]
    }
    tp = {
        "talking_points": [
            {
                "talking_point_id": "tp_1",
                "title": "Claim",
                "importance": "must_keep",
                "why_it_matters": "x",
            }
        ]
    }
    mat = {
        "cuts": [
            {
                "cut_id": "c1",
                "talking_point_id": "tp_1",
                "segment_id": "seg_001",
                "priority": "must_keep",
                "speaker_id": "spk_1",
                "start_ms": 0,
                "end_ms": 3000,
            }
        ]
    }
    man = manifest_from_ideal_cuts(ctx, boundaries=boundaries, talking_points=tp, materialized=mat)
    by_id = {s["segment_id"]: s for s in man["segments"]}
    assert by_id["seg_001"]["type"] == "interviewee_answer"
    assert by_id["seg_001"]["speaker_role"] == "interviewee"
    assert by_id["seg_002"]["type"] in {"interviewer_question", "interviewer_reaction"}
    monkeypatch.undo()
