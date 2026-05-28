"""BUILD-060 — Sound Design Plan schema + empty plan init."""

from interview_mux.analysis_memory import (
    SOUND_DESIGN_PLAN_PATH,
    default_sound_design_plan,
    ensure_analysis_workspace,
)
from interview_mux.prompt_validation import validate_sound_design_plan
from interview_mux.run_context import RunContext


def test_default_sound_design_plan_validates_against_schema():
    plan = default_sound_design_plan()
    assert validate_sound_design_plan(plan) == []


def test_ensure_analysis_workspace_initializes_sound_design_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_001", create=True)
    ensure_analysis_workspace(ctx)
    assert ctx.artifact_exists(SOUND_DESIGN_PLAN_PATH)
    plan = ctx.read_json(SOUND_DESIGN_PLAN_PATH)
    assert plan["version"] == 1
    assert plan["palettes"] == []
    assert plan["assets"] == []
    assert plan["flow_plans"]["flow1"]["cues"] == []
    assert validate_sound_design_plan(plan) == []
