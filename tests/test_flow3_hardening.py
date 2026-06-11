"""Flow 3 hardening — analysis-only upstream for podcast_show_description."""

from __future__ import annotations

from interview_mux.gates import set_selected_flow
from interview_mux.llm_flow_hardening import resolve_llm_upstream_stage
from interview_mux.llm_preflight import run_preflight
from run_fixtures import isolated_run_ctx, seed_analysis_ready_artifacts


def test_podcast_show_description_upstream_flow3(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_flow3_up")
    set_selected_flow(ctx, "flow3")
    seed_analysis_ready_artifacts(ctx)
    ctx.mark_done("optimal_questions")

    assert resolve_llm_upstream_stage(ctx, "podcast_show_description") == "optimal_questions"


def test_podcast_show_description_upstream_flow1(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_flow1_up")
    set_selected_flow(ctx, "flow1")

    assert resolve_llm_upstream_stage(ctx, "podcast_show_description") == "full_master_ranking"


def test_podcast_show_description_preflight_flow3_analysis_only(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_flow3_pf")
    set_selected_flow(ctx, "flow3")
    seed_analysis_ready_artifacts(ctx)

    errors = run_preflight("podcast_show_description", ctx)
    assert errors == []


def test_podcast_show_description_preflight_flow3_missing_brief(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_flow3_miss")
    set_selected_flow(ctx, "flow3")

    errors = run_preflight("podcast_show_description", ctx)
    assert any("content_brief" in e for e in errors)


def test_elevenlabs_prompt_craft_upstream_by_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_el_up")
    set_selected_flow(ctx, "flow1")
    assert resolve_llm_upstream_stage(ctx, "elevenlabs_prompt_craft") == "sound_design_plan_flow1"

    set_selected_flow(ctx, "flow2")
    assert resolve_llm_upstream_stage(ctx, "elevenlabs_prompt_craft") == "sound_design_plan_flow2"
