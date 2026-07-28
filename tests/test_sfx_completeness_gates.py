"""SFX generation collects all SDP assets; soft progression does not bypass creative mix gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.llm_flow_hardening import require_spend_artifacts_complete
from interview_mux.mmaudio_asset_qa import analyze_asset_wav
from interview_mux.run_context import RunContext
from interview_mux.stages import sfx_mmaudio
from run_fixtures import isolated_run_ctx, patch_merged_config, seed_flow1_sound_spend_ready


def test_collect_generation_items_includes_uncued_assets(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_sfx_all", create=True)
    ctx.write_json(
        "understanding/sound_design_plan.json",
        {
            "version": 1,
            "coherence": {"sonic_identity": "", "primary_mood": "", "density": ""},
            "palettes": [],
            "assets": [
                {"asset_id": "bed_a", "role": "ambient_bed", "description": "Bed", "duration_seconds": 6.0},
                {"asset_id": "sting_b", "role": "chapter_stinger", "description": "Sting", "duration_seconds": 1.4},
                {"asset_id": "foley_c", "role": "accent_foley", "description": "Foley", "duration_seconds": 2.0},
            ],
            "flow_plans": {
                "podcast": {
                    "profile": "podcast",
                    "cues": [
                        {"cue_id": "c1", "asset_id": "bed_a", "placement": "under_segment"},
                    ],
                },
                "flow2": {"profile": "montage", "cues": []},
            },
            "generated": {},
        },
    )
    items = sfx_mmaudio._collect_generation_items(ctx=ctx, profile="podcast", fallback_cues=[])
    assert [row["asset_id"] for row in items] == ["bed_a", "sting_b", "foley_c"]


def test_mix_gate_enforced_under_soft_progression_when_creative(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "creative_delivery": {"required": True},
            "analysis": {
                "coverage_limits": {"soft_progression": {"enabled": True}},
                "flow_hardening": {
                    "enabled": True,
                    "block_mix_without_sfx_when_enabled": True,
                    "spend_block_stages": ["mix", "mmaudio_sfx"],
                },
            },
            "sound_design": {"block_mix_on_mmaudio_qa_fail": False},
        },
    )
    monkeypatch.setattr("interview_mux.coverage_limits.soft_progression_enabled", lambda cfg=None: True)
    monkeypatch.setattr("interview_mux.creative_delivery.creative_delivery_required", lambda cfg=None: True)
    ctx = isolated_run_ctx(tmp_path, "fh_soft_creative")
    seed_flow1_sound_spend_ready(ctx)
    (ctx.path("sound_design", "assets") / "bed_01.wav").unlink(missing_ok=True)
    with pytest.raises(SystemExit, match="Mix gate"):
        require_spend_artifacts_complete(ctx, "mix")


def test_analyze_asset_wav_rejects_inaudible_stinger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import math
    import struct
    import wave

    patch_merged_config(
        monkeypatch,
        {
            "mmaudio": {
                "silence_rms_threshold": 0.001,
                "min_audible_peak_dbfs": -28.0,
                "min_stinger_peak_dbfs": -24.0,
                "min_audible_rms_dbfs": -40.0,
            }
        },
    )
    path = tmp_path / "quiet.wav"
    rate = 48000
    # ~−35 dBFS peak sine — below stinger floor
    amp = 10 ** (-35 / 20)
    frames = [int(max(-1.0, min(1.0, amp * math.sin(2 * math.pi * 440 * i / rate))) * 32767) for i in range(rate)]
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{len(frames)}h", *frames))
    row = analyze_asset_wav(
        asset_id="warm_wood_stinger",
        path=path,
        plan_row={"role": "chapter_stinger", "duration_seconds": 1.0},
    )
    assert row["verdict"] == "fail"
    assert "inaudible_level" in row["reasons"]
