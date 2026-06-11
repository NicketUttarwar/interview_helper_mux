from __future__ import annotations

from interview_mux.arbiter_expectations import build_stage_expectations, rubric_for_stage


def test_rubric_loads_for_known_stage():
    rubric = rubric_for_stage("content_context")
    assert rubric is not None
    assert rubric.get("stage_key") == "content_context"
    assert len(rubric.get("accept_criteria") or []) >= 3


def test_build_stage_expectations_includes_rubric_fields():
    exp = build_stage_expectations("sound_design_plan_flow1")
    assert "accept_criteria" in exp
    assert "reject_patterns" in exp
    assert exp.get("decompose_eligible") is False


def test_decompose_eligible_stages():
    exp = build_stage_expectations("content_context")
    assert exp.get("decompose_eligible") is True
