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
    from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

    assert "bed_001" in missing_sdp_asset_wavs(ctx)


def test_missing_sdp_wavs_ignores_unreferenced_lazy_slots(tmp_path, monkeypatch):
    """Lazy E3 still skips unreferenced underscore; speech-free bookends stay required."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_sdp_lazy")
    seed_analysis_ready_artifacts(ctx)
    plan = sound_design_plan_with(
        assets=[
            {
                "asset_id": "theme_used",
                "role": "theme_cold_open",
                "description": "Used motif",
                "duration_seconds": 8,
            },
            {
                "asset_id": "theme_outro_required",
                "role": "theme_outro",
                "description": "Preferred outro (required even if not yet cued)",
                "duration_seconds": 10,
            },
            {
                "asset_id": "theme_lazy_underscore",
                "role": "theme_underscore",
                "description": "Unreferenced loop — must not block",
                "duration_seconds": 12,
            },
        ]
    )
    flow = (plan.get("flow_plans") or {}).setdefault("podcast", {})
    flow["cues"] = [
        {
            "cue_id": "c_used",
            "asset_id": "theme_used",
            "role": "theme_cold_open",
            "placement": "before_segment",
            "description": "open",
            "duration_seconds": 8,
        }
    ]
    ctx.write_json("understanding/sound_design_plan.json", plan, skip_handoff=True)
    assets = ctx.final_path("sound_design", "assets")
    assets.mkdir(parents=True, exist_ok=True)
    from pydub.generators import Sine

    for aid in ("theme_used", "theme_outro_required"):
        Sine(220).to_audio_segment(duration=800, volume=-12).set_frame_rate(16000).export(
            str(assets / f"{aid}.wav"), format="wav"
        )
    from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

    # Unreferenced underscore is ignored; bookends with audible WAVs are complete.
    assert missing_sdp_asset_wavs(ctx) == []
    (assets / "theme_outro_required.wav").unlink()
    assert missing_sdp_asset_wavs(ctx) == ["theme_outro_required"]


def test_missing_sdp_wavs_respects_music_limbo_omit(tmp_path, monkeypatch):
    """Limbo-omitted theme beds must not clear mmaudio / block mix as missing WAV."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_sdp_omit")
    seed_analysis_ready_artifacts(ctx)
    plan = sound_design_plan_with(
        assets=[
            {
                "asset_id": "theme_keep",
                "role": "theme_underscore",
                "description": "keep",
                "duration_seconds": 8,
            },
            {
                "asset_id": "theme_omitted",
                "role": "theme_outro",
                "description": "omitted bed",
                "duration_seconds": 10,
            },
        ]
    )
    flow = (plan.get("flow_plans") or {}).setdefault("podcast", {})
    flow["cues"] = [
        {
            "cue_id": "c_keep",
            "asset_id": "theme_keep",
            "role": "theme_underscore",
            "placement": "under_segment",
            "description": "bed",
            "duration_seconds": 8,
        },
        {
            "cue_id": "c_omit",
            "asset_id": "theme_omitted",
            "role": "theme_outro",
            "placement": "after_segment",
            "description": "close",
            "duration_seconds": 10,
        },
    ]
    ctx.write_json("understanding/sound_design_plan.json", plan, skip_handoff=True)
    assets = ctx.final_path("sound_design", "assets")
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "theme_keep.wav").write_bytes(b"RIFF")
    ctx.write_json(
        "operator/music_omitted.json",
        {
            "omitted": [
                {"asset_id": "theme_omitted", "reason": "music_limbo_omit"},
            ]
        },
        skip_handoff=True,
    )
    from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

    assert missing_sdp_asset_wavs(ctx) == []


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
