"""BUILD-060 — Sound Design Plan schema + empty plan init."""

import pytest

from interview_mux.analysis_memory import (
    SOUND_DESIGN_PLAN_PATH,
    default_sound_design_plan,
    ensure_analysis_workspace,
)
from interview_mux.prompt_validation import validate_sound_design_plan
from run_fixtures import isolated_run_ctx


def test_default_sound_design_plan_validates_against_schema():
    plan = default_sound_design_plan()
    assert validate_sound_design_plan(plan) == []


def test_ensure_analysis_workspace_initializes_sound_design_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_sdp_init")
    ensure_analysis_workspace(ctx)
    assert ctx.artifact_exists(SOUND_DESIGN_PLAN_PATH)
    plan = ctx.read_json(SOUND_DESIGN_PLAN_PATH)
    assert plan["version"] == 1
    assert plan["palettes"] == []
    assert plan["assets"] == []
    assert plan["flow_plans"]["podcast"]["cues"] == []
    assert validate_sound_design_plan(plan) == []


def test_write_json_rejects_invalid_sound_design_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_sdp_reject")
    with pytest.raises(ValueError, match="schema validation failed"):
        ctx.write_json("understanding/sound_design_plan.json", {"version": 999})
