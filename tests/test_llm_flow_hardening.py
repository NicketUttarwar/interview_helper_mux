from __future__ import annotations

import pytest

from interview_mux.llm_flow_hardening import (
    LLM_UPSTREAM_STAGE,
    complete_llm_stage_or_halt,
    flow_hardening_enabled,
    llm_stage_progress_ok,
    maybe_require_upstream_llm_progress,
    require_llm_stage_progress,
    require_spend_artifacts_complete,
)
from run_fixtures import isolated_run_ctx, patch_merged_config, seed_flow1_sound_spend_ready

def _minimal_speakers(**extra: object) -> dict:
    base = {
        "speakers": [
            {
                "speaker_id": "spk_1",
                "role": "interviewer",
                "label": "Host",
                "confidence": 0.9,
            }
        ],
    }
    base.update(extra)
    return base

def _cfg(*, enabled: bool = True, strict: bool = True, degraded: bool = False) -> dict:
    base = {
        "analysis": {
            "flow_hardening": {
                "enabled": enabled,
                "strict_critical_stages": strict,
                "halt_on_schema_errors_with_accept": True,
            },
            "llm_resilience": {
                "progression_mode": "degraded_continue" if degraded else "strict",
                "partial_persist_enabled": degraded,
            },
            "llm_null_policy": {"enabled": True, "hard_stop_on_critical_null": True},
        }
    }
    if degraded:
        base["analysis"]["llm_resilience"]["min_artifact_mass"] = {
            "content_context": ["thesis"],
            "speaker_roles": ["speakers"],
        }
    return base

def test_llm_stage_progress_ok_requires_complete_status(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "fh_ok")
    envelope = {"status": "blocked", "needs": []}
    assert llm_stage_progress_ok(ctx, "speaker_roles", envelope, cfg=_cfg()) is False
    envelope = {"status": "complete", "needs": []}
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening.artifact_status",
        lambda _rel, _ctx: "complete",
    )
    assert llm_stage_progress_ok(ctx, "transitions", envelope, cfg=_cfg()) is True

def test_llm_stage_progress_ok_rejects_schema_errors_with_accept(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "fh_schema")
    envelope = {"status": "complete", "needs": []}
    assert (
        llm_stage_progress_ok(
            ctx,
            "content_context",
            envelope,
            schema_errors=["thesis: too short"],
            arbiter_result={"verdict": "accept"},
            cfg=_cfg(),
        )
        is False
    )

def test_complete_llm_stage_or_halt_critical_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _cfg())
    ctx = isolated_run_ctx(tmp_path, "fh_halt")
    with pytest.raises(SystemExit, match="LLM stage gate"):
        complete_llm_stage_or_halt(
            ctx,
            "content_context",
            {"status": "blocked", "needs": [{"type": "rerun_stage", "blocking": True}]},
            cfg=_cfg(),
        )
    assert not ctx.is_done("content_context")

def test_complete_llm_stage_or_halt_soft_logs_without_halt(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _cfg())
    ctx = isolated_run_ctx(tmp_path, "fh_soft")
    with pytest.raises(SystemExit, match="LLM stage gate"):
        complete_llm_stage_or_halt(
            ctx,
            "transitions",
            {"status": "blocked", "needs": []},
            cfg=_cfg(),
        )
    assert not ctx.is_done("transitions")

def test_complete_llm_stage_or_halt_legacy_marks_done_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _cfg(enabled=False))
    ctx = isolated_run_ctx(tmp_path, "fh_legacy")
    from run_fixtures import minimal_content_brief

    ctx.write_json("understanding/content_brief.json", minimal_content_brief(), skip_handoff=True)
    assert flow_hardening_enabled(_cfg(enabled=False)) is False
    ok = complete_llm_stage_or_halt(
        ctx,
        "content_context",
        {"status": "blocked", "needs": []},
        cfg=_cfg(enabled=False),
    )
    assert ok is True
    assert ctx.is_done("content_context")

def test_require_llm_stage_progress_upstream_not_done(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _cfg())
    ctx = isolated_run_ctx(tmp_path, "fh_upstream_nd")
    with pytest.raises(SystemExit, match="Prerequisite stage speaker_roles"):
        require_llm_stage_progress(ctx, "speaker_roles")

def test_require_llm_stage_progress_upstream_artifact_partial(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _cfg())
    ctx = isolated_run_ctx(tmp_path, "fh_upstream_partial")
    ctx.mark_done("speaker_roles", force=True)
    ctx.write_json(
        "understanding/speakers.json",
        _minimal_speakers(_meta={"resilience": {"partial": True}}),
        skip_handoff=True,
    )
    with pytest.raises(SystemExit, match="Prerequisite artifact"):
        require_llm_stage_progress(ctx, "speaker_roles")

def test_maybe_require_upstream_llm_progress_noop_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _cfg(enabled=False))
    ctx = isolated_run_ctx(tmp_path, "fh_upstream_off")
    maybe_require_upstream_llm_progress(ctx, "content_context")

def test_llm_upstream_stage_maps_content_context(tmp_path):
    assert LLM_UPSTREAM_STAGE["content_context"] == "speaker_roles"
    assert LLM_UPSTREAM_STAGE["topic_coverage_audit"] == "delivery_brief_build"

def test_mix_gate_blocks_without_wavs(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "coverage_limits": {"soft_progression": {"enabled": False}},
                "flow_hardening": {
                    "enabled": True,
                    "block_mix_without_sfx_when_enabled": True,
                    "spend_block_stages": [
                        "sfx_prompt_craft",
                        "mmaudio_sfx",
                        "mix",
                    ],
                }
            }
        },
    )
    monkeypatch.setattr("interview_mux.coverage_limits.soft_progression_enabled", lambda cfg=None: False)
    ctx = isolated_run_ctx(tmp_path, "fh_mix_gate")
    seed_flow1_sound_spend_ready(ctx)
    (ctx.path("sound_design", "assets") / "bed_01.wav").unlink()
    with pytest.raises(SystemExit, match="Mix gate"):
        require_spend_artifacts_complete(ctx, "mix")
