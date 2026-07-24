"""Contract tests for multi-critic + arbiter schema outputs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from interview_mux.config import repo_root
from interview_mux.mastering_critics import (
    ALL_CRITICS,
    BLOCKING_CRITICS,
    build_critic_packets,
    merge_panel,
    validate_critic_report,
)
from interview_mux.mastering_pareto import build_frontier
from interview_mux.schema_nullability import with_nullable_optional_leaves

SCHEMAS = repo_root() / "docs" / "cross-cutting" / "json-schemas" / "artifacts"


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
    return Draft202012Validator(with_nullable_optional_leaves(schema))


def _valid_review(candidate_id: str, *, blocking: bool = False) -> dict:
    return {
        "candidate_id": candidate_id,
        "scores": {"arc_coherence": 0.7, "hook_strength": 0.6},
        "verdict": "kill" if blocking else "promote",
        "blocking": blocking,
        "issues": ["fabricated exchange"] if blocking else [],
        "strengths": [] if blocking else ["clear opening"],
        "evidence_refs": [f"mastering/auditions/{candidate_id}/manifest.json"],
        "confidence": 0.8,
    }


def test_critic_report_schema_accepts_each_role():
    validator = _validator("mastering_critic_report.schema.json")
    for critic_id in ALL_CRITICS:
        report = {
            "version": 1,
            "critic_id": critic_id,
            "candidate_reviews": [_valid_review("cand_1")],
            "generated_at": "2026-07-24T00:00:00Z",
        }
        errors = sorted(validator.iter_errors(report), key=lambda e: e.path)
        assert not errors, f"{critic_id}: {[e.message for e in errors]}"


def test_validate_critic_report_rejects_non_integrity_blocking():
    report = {
        "version": 1,
        "critic_id": "engagement_listener",
        "candidate_reviews": [_valid_review("cand_1", blocking=True)],
        "generated_at": "2026-07-24T00:00:00Z",
    }
    errors = validate_critic_report(report)
    assert any("only integrity" in e for e in errors)


def test_integrity_may_block_with_evidence():
    report = {
        "version": 1,
        "critic_id": "integrity",
        "candidate_reviews": [_valid_review("cand_1", blocking=True)],
        "generated_at": "2026-07-24T00:00:00Z",
    }
    assert "integrity" in BLOCKING_CRITICS
    assert not validate_critic_report(report)


def test_merge_panel_kills_on_integrity_and_survives_schema():
    reports = [
        {
            "version": 1,
            "critic_id": "narrative_editor",
            "candidate_reviews": [_valid_review("cand_1"), _valid_review("cand_2")],
            "generated_at": "2026-07-24T00:00:00Z",
        },
        {
            "version": 1,
            "critic_id": "integrity",
            "candidate_reviews": [
                _valid_review("cand_1", blocking=True),
                _valid_review("cand_2"),
            ],
            "generated_at": "2026-07-24T00:00:00Z",
        },
    ]
    merged = merge_panel(reports, candidate_ids=["cand_1", "cand_2"])
    assert [k["candidate_id"] for k in merged["killed"]] == ["cand_1"]
    assert [s["candidate_id"] for s in merged["ranked_survivors"]] == ["cand_2"]

    errors = sorted(
        _validator("mastering_cross_critique.schema.json").iter_errors(merged),
        key=lambda e: e.path,
    )
    assert not errors, [e.message for e in errors]


def test_critic_packets_are_lane_specific():
    packets = build_critic_packets(
        candidates=[{"candidate_id": "cand_1", "ordered_segment_ids": ["s1"]}],
        rubric={"criteria": [{"criterion_id": "arc", "description": "x", "weight": 1.0}]},
        auditions={"cand_1": {"version": 1, "candidate_id": "cand_1", "windows": [], "total_duration_ms": 0, "generated_at": "2026-07-24T00:00:00Z"}},
        semantic_integrity={"version": 1, "candidates": [], "generated_at": "2026-07-24T00:00:00Z"},
    )
    assert set(packets) == set(ALL_CRITICS)
    integrity_refs = {i["ref"] for i in packets["integrity"]["items"]}
    style_refs = {i["ref"] for i in packets["style_fit"]["items"]}
    assert any("semantic_integrity" in r for r in integrity_refs)
    assert any("eval_rubric" in r for r in style_refs)
    assert not any("semantic_integrity" in r for r in style_refs)


def test_pareto_frontier_schema_accepts_panel_output():
    reports = [
        {
            "version": 1,
            "critic_id": "style_fit",
            "candidate_reviews": [
                {
                    "candidate_id": "a",
                    "scores": {"arc": 0.9, "hook": 0.4},
                    "verdict": "promote",
                    "confidence": 0.7,
                    "evidence_refs": ["x"],
                },
                {
                    "candidate_id": "b",
                    "scores": {"arc": 0.4, "hook": 0.9},
                    "verdict": "keep",
                    "confidence": 0.7,
                    "evidence_refs": ["x"],
                },
            ],
            "generated_at": "2026-07-24T00:00:00Z",
        }
    ]
    merged = merge_panel(reports, candidate_ids=["a", "b"])
    frontier = build_frontier(
        [
            {"candidate_id": s["candidate_id"], "dimension_scores": s["dimension_scores"]}
            for s in merged["ranked_survivors"]
        ]
    )
    errors = sorted(
        _validator("mastering_pareto_frontier.schema.json").iter_errors(frontier),
        key=lambda e: e.path,
    )
    assert not errors, [e.message for e in errors]
    assert {m["candidate_id"] for m in frontier["frontier"]} == {"a", "b"}


@pytest.mark.parametrize(
    "schema_name",
    [
        "mastering_research_routing.schema.json",
        "mastering_evidence_packet.schema.json",
        "mastering_diversity_report.schema.json",
        "mastering_feasibility.schema.json",
        "mastering_semantic_integrity.schema.json",
        "mastering_eval_rubric.schema.json",
        "mastering_audition_manifest.schema.json",
        "mastering_critic_report.schema.json",
        "mastering_cross_critique.schema.json",
        "mastering_pareto_frontier.schema.json",
        "mastering_voice_clone_audit.schema.json",
        "mastering_polish_audit.schema.json",
    ],
)
def test_hardening_schemas_are_valid_draft2020(schema_name: str):
    path = SCHEMAS / schema_name
    assert path.is_file()
    Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))
