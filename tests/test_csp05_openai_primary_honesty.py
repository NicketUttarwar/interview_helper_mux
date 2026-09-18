"""CSP-05 pins: hollow OpenAI primary → incomplete/refuse (no soft-success heal-done)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.openai_primary_honesty import (
    coverage_audit_hollow_incompleteness,
    gap_compose_zero_lines_while_framing,
    hollow_openai_reason,
    research_routing_llm_failed_incompleteness,
    shape_agenda_rubric_llm_failed_incompleteness,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import stage_artifact_incompleteness
from run_fixtures import patch_executions_root


def test_csp05_helper_reason_stable() -> None:
    assert "hollow/invalid OpenAI primary" in hollow_openai_reason("x", "detail")


def test_csp05_mrr_llm_failed_doc_incomplete() -> None:
    reason = research_routing_llm_failed_incompleteness(
        {"llm_failed": True, "skipped": "llm_failed", "fail_reason": "boom"}
    )
    assert reason and "mastering_research_routing" in reason


def test_csp05_msa_rubric_failed_doc_incomplete() -> None:
    reason = shape_agenda_rubric_llm_failed_incompleteness(
        {"source": "llm"},
        {"notes": ["rubric_llm_failed"], "llm_failed": True, "criteria": []},
    )
    assert reason and "rubric_llm_failed" in reason


def test_csp05_tca_hollow_coverage_incomplete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext(create=True)
    # Schema requires coverage_score; hollow = score present but no mappings/findings body
    # is still accepted by schema — incompleteness uses helper on empty mappings + no score.
    hollow = coverage_audit_hollow_incompleteness(
        {"topic_mappings": [], "missing_coverage": []}
    )
    assert hollow and "topic_coverage_audit" in hollow
    # Persist a schema-valid but semantically empty-ish audit missing mappings:
    # coverage_score alone with empty missing_coverage is OK for completeness helper.
    path = ctx.final_path("master", "coverage_audit.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"topic_mappings": [], "missing_coverage": [], "_meta": {"producer_stage": "topic_coverage_audit"}}\n'
    )
    reason = stage_artifact_incompleteness(ctx, "topic_coverage_audit")
    assert reason and "topic_coverage_audit" in reason
    assert "hollow" in reason.lower() or "OpenAI primary" in reason


def test_csp05_tca_scored_coverage_complete() -> None:
    assert (
        coverage_audit_hollow_incompleteness(
            {"coverage_score": 0.8, "missing_coverage": [], "topic_mappings": []}
        )
        is None
    )


def test_csp05_gfc_zero_lines_allowed_q6b() -> None:
    """Q6B: framing Yes + zero compose lines no longer incompleteness."""
    assert (
        gap_compose_zero_lines_while_framing(
            {
                "interviewer_lines": [],
                "_meta": {"producer": "gap_framing_compose"},
            },
            framing_enabled=True,
        )
        is None
    )
    assert (
        gap_compose_zero_lines_while_framing(
            {
                "interviewer_lines": [{"line_id": "a", "text": "hello"}],
                "_meta": {"producer": "gap_framing_compose"},
            },
            framing_enabled=True,
        )
        is None
    )
