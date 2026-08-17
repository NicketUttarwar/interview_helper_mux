"""Tests for sdp_cross_validate pre-mix and plan checkpoints."""

from __future__ import annotations

from interview_mux.sdp_cross_validate import (
    validate_post_sound_plan_flow2,
    validate_pre_mix,
    validate_pre_sfx_generation,
)
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
    """Unique-asset caps are soft by default — many role assets must not hard-fail."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_sdp_mix_cap")
    assets = [_sample_asset(f"bed_{i}") for i in range(9)]
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(assets=assets),
        skip_handoff=True,
    )
    errors = validate_post_sound_plan_flow2(ctx)
    assert not any("cap" in e for e in errors)


def test_validate_pre_sfx_allows_theme_emphasis_role_floor_bump(tmp_path, monkeypatch):
    """5s plan vs 6s craft for theme_emphasis is in-band — not a hard fail."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_sdp_dur_band")
    seed_analysis_ready_artifacts(ctx)
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            assets=[
                {
                    "asset_id": "show_theme_v1_stinger_01",
                    "role": "theme_emphasis",
                    "description": "Short emphasis sting.",
                    "duration_seconds": 5.0,
                }
            ]
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "sound_design/sfx_prompts.json",
        {
            "prompts": [
                {
                    "asset_id": "show_theme_v1_stinger_01",
                    "role": "theme_emphasis",
                    "duration_seconds": 6.0,
                    "sfx_prompt": "Warm piano sting, close-mic, no lyrics.",
                    "negative_prompt": "vocals speech lyrics choir talk",
                }
            ]
        },
        skip_handoff=True,
    )
    errors = validate_pre_sfx_generation(ctx)
    assert not any("duration" in e.lower() for e in errors)
