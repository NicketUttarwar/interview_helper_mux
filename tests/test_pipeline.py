from __future__ import annotations

import pytest

from interview_mux import pipeline
from interview_mux.analysis_memory import default_analysis_state
from interview_mux.gates import set_selected_flow
from run_fixtures import ctx_from_fixture


def test_run_flow1_blocks_when_profile_unverified(tmp_path):
    ctx = ctx_from_fixture(tmp_path)
    state = default_analysis_state(ctx.run_id)
    state["meta"]["operator_verified"] = False
    ctx.write_json("understanding/analysis_state.json", state)
    with pytest.raises(SystemExit, match="Profile gate"):
        pipeline.run_flow1(ctx)


def test_run_single_stage_transcript_review_build_pauses_when_queue_exists(tmp_path, monkeypatch):
    ctx = ctx_from_fixture(tmp_path)
    monkeypatch.setattr(
        pipeline,
        "_analysis_stage_fns",
        lambda _ctx: {"transcript_review_build": lambda: None},
    )
    with pytest.raises(SystemExit, match="Transcript review required"):
        pipeline.run_single_stage(ctx, "transcript_review_build")


def _stub_stage(called: list[str], name: str):
    def _fn(*_args, **_kwargs):
        called.append(name)

    return _fn


def test_run_flow1_smoke_uses_fixture_run_dir_without_external_calls(tmp_path, monkeypatch):
    ctx = ctx_from_fixture(tmp_path)
    called: list[str] = []

    monkeypatch.setattr(
        pipeline.analysis_flow1_extended,
        "run_topic_coverage",
        _stub_stage(called, "topic_coverage_audit"),
    )
    monkeypatch.setattr(
        pipeline.analysis_flow1_extended,
        "run_narrative_arc",
        _stub_stage(called, "narrative_arc_plan"),
    )
    monkeypatch.setattr(
        pipeline.selection_flow1,
        "run_full_master_ranking",
        _stub_stage(called, "full_master_ranking"),
    )
    monkeypatch.setattr(
        pipeline.selection_flow1,
        "run_transitions",
        _stub_stage(called, "transitions"),
    )
    monkeypatch.setattr(
        pipeline.sound_design_stages,
        "run_sound_design_plan_flow1",
        _stub_stage(called, "sound_design_plan_flow1"),
    )
    monkeypatch.setattr(
        pipeline.assembly_flow1,
        "run_edl",
        _stub_stage(called, "edl_flow1"),
    )
    monkeypatch.setattr(
        pipeline.assembly_flow1,
        "run_preview",
        _stub_stage(called, "assembly_preview"),
    )
    monkeypatch.setattr(
        pipeline.sound_design_stages,
        "run_elevenlabs_prompt_craft",
        _stub_stage(called, "elevenlabs_prompt_craft"),
    )
    monkeypatch.setattr(
        pipeline.sfx_elevenlabs,
        "run_sfx_generation",
        lambda _ctx, profile: called.append(f"elevenlabs_sfx_{profile}"),
    )
    monkeypatch.setattr(
        pipeline.assembly_flow1,
        "run_mix_flow1",
        _stub_stage(called, "mix_flow1"),
    )
    monkeypatch.setattr(
        pipeline.mastering,
        "run_master_flow1",
        _stub_stage(called, "master_flow1"),
    )

    pipeline.run_flow1(ctx)

    assert called == [
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "transitions",
        "sound_design_plan_flow1",
        "edl_flow1",
        "assembly_preview",
        "elevenlabs_prompt_craft",
        "elevenlabs_sfx_podcast",
        "mix_flow1",
        "master_flow1",
    ]


def test_run_flow2_smoke_uses_fixture_run_dir_without_external_calls(tmp_path, monkeypatch):
    ctx = ctx_from_fixture(tmp_path, run_id="exec_flow2_smoke")
    set_selected_flow(ctx, "flow2")
    called: list[str] = []

    monkeypatch.setattr(
        pipeline.selection_flow2,
        "run_highlight_selection",
        _stub_stage(called, "highlight_selection"),
    )
    monkeypatch.setattr(
        pipeline.sound_design_stages,
        "run_sound_design_plan_flow2",
        _stub_stage(called, "sound_design_plan_flow2"),
    )
    monkeypatch.setattr(
        pipeline.sound_design_stages,
        "run_elevenlabs_prompt_craft",
        _stub_stage(called, "elevenlabs_prompt_craft"),
    )
    monkeypatch.setattr(
        pipeline.sfx_elevenlabs,
        "run_sfx_generation",
        lambda _ctx, profile: called.append(f"elevenlabs_sfx_{profile}"),
    )
    monkeypatch.setattr(
        pipeline.assembly_flow2,
        "run_mix_flow2",
        _stub_stage(called, "mix_flow2"),
    )
    monkeypatch.setattr(
        pipeline.mastering,
        "run_master_flow2",
        _stub_stage(called, "master_flow2"),
    )

    pipeline.run_flow2(ctx)

    assert called == [
        "highlight_selection",
        "sound_design_plan_flow2",
        "elevenlabs_prompt_craft",
        "elevenlabs_sfx_montage",
        "mix_flow2",
        "master_flow2",
    ]


def test_run_flow3_smoke_uses_fixture_run_dir_without_external_calls(tmp_path, monkeypatch):
    ctx = ctx_from_fixture(tmp_path, run_id="exec_flow3_smoke")
    called: list[str] = []

    monkeypatch.setattr(
        pipeline.publishing_flow3,
        "run_podcast_show_description",
        _stub_stage(called, "podcast_show_description"),
    )
    monkeypatch.setattr(
        pipeline.publishing_flow3,
        "run_export_show_description",
        _stub_stage(called, "export_show_description"),
    )
    monkeypatch.setattr(pipeline, "check_g1_vo", lambda _ctx: [])

    pipeline.run_flow3(ctx)

    assert called == ["podcast_show_description", "export_show_description"]


def test_run_analysis_smoke_uses_fixture_without_external_calls(tmp_path, monkeypatch):
    ctx = ctx_from_fixture(tmp_path, run_id="exec_analysis_smoke")
    called: list[str] = []

    stage_fns = {
        name: _stub_stage(called, name)
        for name in pipeline.ANALYSIS_ORDER
    }

    monkeypatch.setattr(pipeline, "_analysis_stage_fns", lambda _ctx: stage_fns)
    monkeypatch.setattr(pipeline, "pre_analysis_init", lambda _ctx: None)
    monkeypatch.setattr(
        pipeline,
        "post_analysis_finalize",
        lambda _ctx: {"analysis_ready": True, "blockers": []},
    )
    monkeypatch.setattr(pipeline, "drain_investigation_queue", lambda _ctx, _runners: None)
    monkeypatch.setattr(pipeline, "check_transcript_review_pending", lambda _ctx: False)
    monkeypatch.setattr(pipeline, "check_g1_vo", lambda _ctx: [])

    pipeline.run_analysis(ctx)

    assert called == list(pipeline.ANALYSIS_ORDER)
    assert ctx.artifact_exists("analysis_complete.json")
