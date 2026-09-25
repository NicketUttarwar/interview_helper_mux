from __future__ import annotations

import pytest

from interview_mux import pipeline
from interview_mux.analysis_memory import default_analysis_state
from run_fixtures import ctx_from_fixture, plant_primary_and_stamp

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
    from interview_mux.llm_simple import StageError
    from interview_mux.stages import analysis_stage
    from run_fixtures import isolated_run_ctx, patch_merged_config

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True, "strict_critical_stages": True}}},
    )
    ctx = isolated_run_ctx(tmp_path, "blocked_stage")

    def _failing_prompt(*_a, **_k):
        return {"status": "partial", "artifacts": {}, "needs": [{"type": "rerun_stage", "blocking": True}]}

    monkeypatch.setattr(
        "interview_mux.llm_simple.run_prompt_envelope",
        _failing_prompt,
    )
    monkeypatch.setattr(
        "interview_mux.llm_simple.validate_stage_artifacts",
        lambda *_a, **_k: ["schema validation failed"],
    )

    with pytest.raises(StageError):
        analysis_stage.run_analysis_llm_stage(
            ctx,
            "content_context",
            "understanding/content-context.system.txt",
            lambda _c: {},
            lambda _c, _a: None,
        )
    assert not ctx.is_done("content_context")

def test_run_delivery_blocks_when_profile_unverified(tmp_path):
    from interview_mux.v2.config import v2_enabled
    from run_fixtures import seed_analysis_ready_artifacts

    ctx = ctx_from_fixture(tmp_path)
    seed_analysis_ready_artifacts(ctx, verified=False)
    if v2_enabled():
        # Profile gate cut in v2 — delivery proceeds past analysis readiness checks.
        # Incomplete stage inputs still block (boundaries / shared analysis).
        from interview_mux.stage_input_checks import StageInputError

        with pytest.raises(StageInputError):
            pipeline.run_delivery(ctx)
        return
    with pytest.raises(SystemExit, match="Profile gate"):
        pipeline.run_delivery(ctx)

def test_run_single_stage_transcript_review_build_pauses_when_queue_exists(tmp_path, monkeypatch):
    ctx = ctx_from_fixture(tmp_path)
    plant_primary_and_stamp(ctx, "audio_preclean")
    plant_primary_and_stamp(ctx, "ingest")
    plant_primary_and_stamp(ctx, "audio_probe_build")
    _bypass_stage_input_checks(monkeypatch)
    _bypass_upstream_llm_checks(monkeypatch)
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


def test_delivery_stage_fns_invoke_without_ctx_argument(tmp_path, monkeypatch):
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "delivery_fn_wrappers")
    seen: list[str] = []

    monkeypatch.setattr(
        pipeline.analysis_extended,
        "run_topic_coverage",
        _stub_stage(seen, "topic_coverage_audit"),
    )
    monkeypatch.setattr(
        pipeline.assembly,
        "run_edl",
        _stub_stage(seen, "edl"),
    )

    pipeline._delivery_stage_fns(ctx)["topic_coverage_audit"]()
    pipeline._delivery_stage_fns(ctx)["edl"]()

    assert seen == ["topic_coverage_audit", "edl"]

def test_run_delivery_smoke_uses_fixture_run_dir_without_external_calls(tmp_path, monkeypatch):
    from interview_mux.v2.config import DELIVERY_ORDER

    ctx = ctx_from_fixture(tmp_path)
    called: list[str] = []

    monkeypatch.setattr("interview_mux.gates.require_analysis_artifacts_complete", lambda _ctx: None)
    monkeypatch.setattr("interview_mux.gates.require_g1_clear", lambda _ctx: None)
    monkeypatch.setattr("interview_mux.gates.require_delivery_gates", lambda _ctx, **_: None)
    monkeypatch.setattr("interview_mux.progression_readiness.assert_delivery_ready", lambda *_a, **_k: None)
    _bypass_stage_input_checks(monkeypatch)
    _bypass_upstream_llm_checks(monkeypatch)

    stubbed = {name: _stub_stage(called, name) for name in DELIVERY_ORDER}
    monkeypatch.setattr(
        pipeline,
        "_delivery_stage_fns",
        lambda _ctx: stubbed,
    )

    pipeline.run_delivery(ctx)

    # Production no longer pre-seals gap_report_sanitize before the delivery walk.
    assert called == list(DELIVERY_ORDER)

def test_sound_design_disabled_skips_spend_stages(tmp_path, monkeypatch):
    from interview_mux.stages import sound_design_stages
    from run_fixtures import isolated_run_ctx, patch_merged_config, seed_analysis_ready_artifacts

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"sound_design": {"enabled": False}})
    ctx = isolated_run_ctx(tmp_path, "pipeline_sd_off")
    seed_analysis_ready_artifacts(ctx)

    sound_design_stages.run_sound_design_palettes(ctx)
    sound_design_stages.run_sfx_prompt_craft(ctx)

    # Disabled sound design skips spend but heal_or_refuse refuses hollow marks.
    assert not ctx.is_done("sound_design_palettes")
    assert not ctx.is_done("sfx_prompt_craft")

def test_run_analysis_smoke_uses_fixture_without_external_calls(tmp_path, monkeypatch):
    ctx = ctx_from_fixture(tmp_path, run_id="exec_analysis_smoke")
    called: list[str] = []

    stage_fns = {
        name: _stub_stage(called, name)
        for name in pipeline.ANALYSIS_ORDER
    }

    monkeypatch.setattr(pipeline, "_analysis_stage_fns", lambda _ctx: stage_fns)
    monkeypatch.setattr(
        "interview_mux.artifact_cross_validate.maybe_cross_validate_after_stage",
        lambda _ctx, _name: None,
    )
    monkeypatch.setattr(pipeline, "check_transcript_review_pending", lambda _ctx: False)
    monkeypatch.setattr(pipeline, "check_g1_vo", lambda _ctx: [])
    monkeypatch.setattr(
        "interview_mux.analysis_memory.update_completion_from_analysis",
        lambda _ctx: {"analysis_ready": True, "blockers": []},
    )
    _bypass_stage_input_checks(monkeypatch)
    _bypass_upstream_llm_checks(monkeypatch)
    monkeypatch.setattr(
        "interview_mux.write_staging.run_wrapped_stage",
        lambda _ctx, _name, fn: fn(),
    )

    pipeline.run_analysis(ctx)

    assert called == list(pipeline.ANALYSIS_ORDER)
    assert ctx.artifact_exists("analysis_complete.json")
