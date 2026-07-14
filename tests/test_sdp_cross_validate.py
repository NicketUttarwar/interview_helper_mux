"""Tests for sdp_cross_validate pre-mix and plan checkpoints."""

from __future__ import annotations

from interview_mux.sdp_cross_validate import validate_post_sound_plan_flow2, validate_pre_mix
from run_fixtures import isolated_run_ctx, seed_analysis_ready_artifacts, sound_design_plan_with


def _sample_asset(asset_id: str = "bed_001") -> dict:
    return {
        "asset_id": asset_id,
        "role": "ambient_bed",
        "description": "Soft ambient bed",
        "duration_seconds": 30,
    }


def test_validate_pre_mix_missing_assets(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_sdp_mix")
    seed_analysis_ready_artifacts(ctx)
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(assets=[_sample_asset()]),
        skip_handoff=True,
    )
    errors = validate_pre_mix(ctx, "flow2")
    assert errors


def test_validate_post_sound_plan_flow2_over_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_sdp_mix_cap")
    assets = [_sample_asset(f"bed_{i}") for i in range(7)]
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(assets=assets),
        skip_handoff=True,
    )
    errors = validate_post_sound_plan_flow2(ctx)
    assert any("cap" in e for e in errors)
