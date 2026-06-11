from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.arbiter_expectations import build_stage_expectations, rubric_for_stage
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS

_RUBRIC_DIR = Path(__file__).resolve().parents[1] / "docs" / "prompts" / "_shared" / "arbiter-rubrics"


@pytest.mark.parametrize(
    "stage_key",
    sorted(p.stem for p in _RUBRIC_DIR.glob("*.json")),
)
def test_rubric_json_loads_for_each_file(stage_key: str):
    rubric = rubric_for_stage(stage_key)
    assert rubric is not None
    assert rubric.get("stage_key") == stage_key


def test_all_schema_stages_have_rubric_or_legacy():
    for stage_key in STAGE_ARTIFACT_SCHEMAS:
        if stage_key in ("podcast_sfx_brief", "sfx_brief"):
            continue
        assert rubric_for_stage(stage_key) is not None, stage_key


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
