from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.arbiter_expectations import build_stage_expectations, rubric_for_stage
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS

_RUBRIC_DIR = Path(__file__).resolve().parents[1] / "docs" / "prompts" / "_shared" / "arbiter-rubrics"

_REMOVED_RUBRIC_STEMS = frozenset(
    {
        "highlight_selection",
        "podcast_show_description",
        "sound_design_plan_flow2",
        "sfx_brief",
    }
)


def _active_rubric_stems() -> list[str]:
    stems: list[str] = []
    for path in sorted(_RUBRIC_DIR.glob("*.json")):
        if path.stem in _REMOVED_RUBRIC_STEMS:
            continue
        rubric = rubric_for_stage(path.stem)
        if rubric is None:
            continue
        stage_key = str(rubric.get("stage_key") or path.stem)
        if stage_key.startswith("REMOVED_"):
            continue
        stems.append(path.stem)
    return stems


@pytest.mark.parametrize("stage_key", _active_rubric_stems())
def test_rubric_json_loads_for_each_file(stage_key: str):
    rubric = rubric_for_stage(stage_key)
    assert rubric is not None
    assert rubric.get("stage_key") == stage_key or rubric.get("stage_key") == "sound_design_plan"


def test_all_schema_stages_have_rubric_or_legacy():
    for stage_key in STAGE_ARTIFACT_SCHEMAS:
        if stage_key in ("podcast_sfx_brief", "sfx_brief"):
            continue
        rubric = rubric_for_stage(stage_key)
        if rubric is None:
            rubric = rubric_for_stage("sound_design_plan_flow1")
        assert rubric is not None, stage_key


def test_rubric_loads_for_known_stage():
    rubric = rubric_for_stage("content_context")
    assert rubric is not None
    assert rubric.get("stage_key") == "content_context"
    assert len(rubric.get("accept_criteria") or []) >= 3


def test_build_stage_expectations_includes_rubric_fields():
    exp = build_stage_expectations("sound_design_plan")
    assert "accept_criteria" in exp
    assert "reject_patterns" in exp
    assert exp.get("decompose_eligible") is False


def test_transitions_rubric_rejects_stub_bridges():
    """Plan 5: bridges/transitions must not be generic filler stubs."""
    rubric = rubric_for_stage("transitions")
    assert rubric is not None
    patterns = " ".join(rubric.get("reject_patterns") or [])
    assert "stub bridge" in patterns.lower() or "filler bridge" in patterns.lower()


def test_arbiter_system_prompt_rejects_stub_bridges_and_thin_montage():
    system_path = (
        Path(__file__).resolve().parents[1] / "docs" / "prompts" / "_shared" / "arbiter.system.txt"
    )
    text = system_path.read_text(encoding="utf-8").lower()
    assert "stub placeholders" in text
    assert "thin `hook_montage`" in text or "thin hook_montage" in text


def test_decompose_never_eligible():
    """v2 dropped shard/collate decomposition — no stage may opt back in."""
    for stage_key in ("content_context", "segment_classification", "sound_design_plan"):
        exp = build_stage_expectations(stage_key)
        assert exp.get("decompose_eligible") is False, stage_key
