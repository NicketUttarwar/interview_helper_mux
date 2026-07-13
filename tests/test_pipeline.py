from __future__ import annotations

import pytest

from interview_mux import pipeline
from interview_mux.analysis_memory import default_analysis_state
from run_fixtures import ctx_from_fixture

def _bypass_upstream_llm_checks(monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening.maybe_require_upstream_llm_progress",
        lambda _ctx, _name: None,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_cross_validate.maybe_cross_validate_after_stage",
        lambda _ctx, _name: None,
    )
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening.require_spend_artifacts_complete",
        lambda *_a, **_k: None,
    )


def _bypass_stage_input_checks(monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.stage_input_checks.require_stage_inputs",
        lambda _ctx, _name: None,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_lifecycle.run_phase_checks",
        lambda _ctx, _stage, _phase: [],
    )
    monkeypatch.setattr(
        "interview_mux.write_staging.after_stage_write_check",
        lambda _ctx, _name: None,
    )

def test_blocked_llm_stage_does_not_mark_done(tmp_path, monkeypatch):
    from interview_mux.stages import analysis_stage
    from run_fixtures import isolated_run_ctx, patch_merged_config

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True, "strict_critical_stages": True}}},
    )
    ctx = isolated_run_ctx(tmp_path, "blocked_stage")
    blocked = {"status": "blocked", "needs": [{"type": "rerun_stage", "blocking": True}]}

    monkeypatch.setattr(
        analysis_stage,
        "run_llm_stage_with_routing",
        lambda *_a, **_k: (blocked, [], {"verdict": "enqueue_investigation"}, [], 0, None),
    )
    monkeypatch.setattr(analysis_stage, "finalize_stage_attempt", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "interview_mux.analysis_orchestrator.max_iterations_for_stage",
        lambda _c: 1,
    )

    with pytest.raises(SystemExit):
        analysis_stage.run_analysis_llm_stage(
            ctx,
            "content_context",
            "understanding/content-context.system.txt",
            lambda _c: {},
            lambda _c, _a: None,
        )
    assert not ctx.is_done("content_context")

def test_run_delivery_blocks_when_profile_unverified(tmp_path):
    from run_fixtures import seed_analysis_ready_artifacts

    ctx = ctx_from_fixture(tmp_path)
    seed_analysis_ready_artifacts(ctx, verified=False)
    with pytest.raises(SystemExit, match="Profile gate"):
        pipeline.run_delivery(ctx)

def test_run_single_stage_transcript_review_build_pauses_when_queue_exists(tmp_path, monkeypatch):
    ctx = ctx_from_fixture(tmp_path)
    _bypass_stage_input_checks(monkeypatch)
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

def test_run_delivery_smoke_uses_fixture_run_dir_without_external_calls(tmp_path, monkeypatch):
    ctx = ctx_from_fixture(tmp_path)
    called: list[str] = []

    monkeypatch.setattr("interview_mux.gates.require_analysis_artifacts_complete", lambda _ctx: None)
    monkeypatch.setattr("interview_mux.gates.require_g1_clear", lambda _ctx: None)
    monkeypatch.setattr("interview_mux.gates.require_delivery_gates", lambda _ctx, **_: None)
    monkeypatch.setattr("interview_mux.progression_readiness.assert_delivery_ready", lambda *_a, **_k: None)
    _bypass_stage_input_checks(monkeypatch)
    _bypass_upstream_llm_checks(monkeypatch)
    monkeypatch.setattr(
        pipeline.analysis_extended,
        "run_topic_coverage",
        _stub_stage(called, "topic_coverage_audit"),
    )
    monkeypatch.setattr(
        pipeline.analysis_extended,
        "run_narrative_arc",
        _stub_stage(called, "narrative_arc_plan"),
    )
    monkeypatch.setattr(
        pipeline.selection,
        "run_full_master_ranking",
        _stub_stage(called, "full_master_ranking"),
    )
    monkeypatch.setattr(
        pipeline.selection,
        "run_transitions",
        _stub_stage(called, "transitions"),
    )
    monkeypatch.setattr(
        pipeline.sound_design_stages,
        "run_sound_design_plan",
        _stub_stage(called, "sound_design_plan"),
    )
    monkeypatch.setattr(
        pipeline.sound_design_vo_finalize,
        "run_sound_design_vo_finalize",
        _stub_stage(called, "sound_design_vo_finalize"),
    )
    monkeypatch.setattr(
        pipeline.edl_narrative_audit,
        "run_edl_narrative_audit",
        _stub_stage(called, "edl_narrative_audit"),
    )
    monkeypatch.setattr(
        pipeline.assembly,
        "run_edl",
        _stub_stage(called, "edl"),
    )
    monkeypatch.setattr(
        pipeline.assembly,
        "run_preview",
        _stub_stage(called, "assembly_preview"),
    )
    monkeypatch.setattr(
        pipeline.sound_design_stages,
        "run_sfx_prompt_craft",
        _stub_stage(called, "sfx_prompt_craft"),
    )
    monkeypatch.setattr(
        pipeline.sfx_mmaudio,
        "run_sfx_generation",
        lambda _ctx, profile: called.append(f"mmaudio_sfx_{profile}"),
    )
    monkeypatch.setattr(
        pipeline.assembly,
        "run_mix",
        _stub_stage(called, "mix"),
    )
    monkeypatch.setattr(
        pipeline.mastering,
        "run_master_finalize",
        _stub_stage(called, "master_finalize"),
    )

    pipeline.run_delivery(ctx)

    assert called == [
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "transitions",
        "sound_design_plan",
        "sound_design_vo_finalize",
        "edl_narrative_audit",
        "edl",
        "assembly_preview",
        "sfx_prompt_craft",
        "mmaudio_sfx_podcast",
        "mix",
        "master_finalize",
    ]

def test_sound_design_disabled_skips_spend_stages(tmp_path, monkeypatch):
    from interview_mux.stages import sound_design_stages
    from run_fixtures import isolated_run_ctx, patch_merged_config, seed_analysis_ready_artifacts

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"sound_design": {"enabled": False}})
    ctx = isolated_run_ctx(tmp_path, "pipeline_sd_off")
    seed_analysis_ready_artifacts(ctx)

    sound_design_stages.run_sound_design_palettes(ctx)
    sound_design_stages.run_sfx_prompt_craft(ctx)

    assert ctx.is_done("sound_design_palettes")
    assert ctx.is_done("sfx_prompt_craft")

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
    monkeypatch.setattr(
        "interview_mux.artifact_cross_validate.maybe_cross_validate_after_stage",
        lambda _ctx, _name: None,
    )
    monkeypatch.setattr(pipeline, "check_transcript_review_pending", lambda _ctx: False)
    monkeypatch.setattr(pipeline, "check_g1_vo", lambda _ctx: [])
    _bypass_stage_input_checks(monkeypatch)
    _bypass_upstream_llm_checks(monkeypatch)
    monkeypatch.setattr(
        "interview_mux.write_staging.run_wrapped_stage",
        lambda _ctx, _name, fn: fn(),
    )

    pipeline.run_analysis(ctx)

    assert called == list(pipeline.ANALYSIS_ORDER)
    assert ctx.artifact_exists("analysis_complete.json")
