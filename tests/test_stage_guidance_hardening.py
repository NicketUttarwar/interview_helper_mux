from __future__ import annotations

import json

from interview_mux.stage_guidance import build_stage_guidance
from run_fixtures import isolated_run_ctx, patch_merged_config


def test_guidance_shows_budget_exhaustion(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True, "max_primary_attempts_per_stage": 2}}},
    )
    ctx = isolated_run_ctx(tmp_path, "guidance_budget")
    ctx.write_json(
        "understanding/analysis_orchestration.json",
        {"primary_attempt_counts": {"missing_framing": 2}},
        skip_handoff=True,
    )
    guidance = build_stage_guidance(ctx, "missing_framing", status="pending")
    ids = [p["id"] for p in guidance["prerequisites"]]
    assert "llm_budget" in ids


def test_guidance_shows_lint_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "guidance_lint")
    base = ctx.path("understanding", "stage_runs", "content_context")
    base.mkdir(parents=True, exist_ok=True)
    (base / "attempt_001.json").write_text(
        json.dumps({"deterministic_lint_errors": ["thesis empty"]}),
        encoding="utf-8",
    )
    guidance = build_stage_guidance(ctx, "content_context", status="pending")
    ids = [p["id"] for p in guidance["prerequisites"]]
    assert "llm_lint" in ids


def test_guidance_shows_placement_qa_on_mix(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "guidance_pq")
    ctx.write_json(
        "sound_design/placement_adjustments.json",
        {"version": 1, "adjustments": []},
        skip_handoff=True,
    )
    guidance = build_stage_guidance(ctx, "mix_flow1", status="pending")
    ids = [p["id"] for p in guidance["prerequisites"]]
    assert "placement_qa" in ids


def test_guidance_shows_stage_reuse_offer(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "guidance_reuse")
    ctx.write_json(
        "gui_job.json",
        {"needs_stage_reuse": True, "stage": "missing_framing", "status": "needs_operator"},
        skip_handoff=True,
    )
    guidance = build_stage_guidance(ctx, "missing_framing", status="pending")
    ids = [p["id"] for p in guidance["prerequisites"]]
    assert "stage_reuse" in ids


def test_guidance_shows_post_listen_on_sfx(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "guidance_listen")
    guidance = build_stage_guidance(ctx, "elevenlabs_sfx_flow1", status="pending")
    ids = [p["id"] for p in guidance["prerequisites"]]
    assert "post_listen" in ids


def test_guidance_shows_qc_card_on_ranking(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "guidance_qc")
    guidance = build_stage_guidance(ctx, "full_master_ranking", status="pending")
    ids = [p["id"] for p in guidance["prerequisites"]]
    assert "qc_card" in ids


def test_guidance_elevenlabs_handoff_upstream(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True}}},
    )
    ctx = isolated_run_ctx(tmp_path, "guidance_el")
    ctx.write_json("run_meta.json", {"selected_flow": "flow1"}, skip_handoff=True)
    guidance = build_stage_guidance(ctx, "elevenlabs_prompt_craft", status="pending")
    ids = [p["id"] for p in guidance["prerequisites"]]
    assert "upstream_artifact" in ids
