from __future__ import annotations

import math
from pathlib import Path

from pydub import AudioSegment
from pydub.generators import Sine

from interview_mux.run_context import RunContext
from interview_mux.sound_design import _check_bed_presence_band
from interview_mux.underbed_ab_qc import (
    analyze_underbed_ab_qc,
    apply_underbed_eq,
    underbed_eq_settings,
)
from run_fixtures import init_run_meta_for_test, patch_merged_config


def _tone(frequency: int, *, duration_ms: int = 2000, volume: float = -12.0) -> AudioSegment:
    return (
        Sine(frequency)
        .to_audio_segment(duration=duration_ms, volume=volume)
        .set_channels(1)
        .set_frame_rate(48_000)
    )


def _band_db(segment: AudioSegment, low_hz: int, high_hz: int) -> float:
    filtered = segment.high_pass_filter(low_hz).low_pass_filter(high_hz)
    return 20.0 * math.log10(max(1, filtered.rms))


def test_underbed_eq_reduces_speech_band_without_broad_level_cut() -> None:
    speech_band = _tone(2500)
    low_band = _tone(300)
    settings = underbed_eq_settings(
        {"underbed_eq": {"enabled": True, "low_hz": 1500, "high_hz": 4000, "depth_db": 3}}
    )

    carved_speech_band = apply_underbed_eq(speech_band, settings)
    carved_low_band = apply_underbed_eq(low_band, settings)

    speech_reduction_db = _band_db(carved_speech_band, 1800, 3500) - _band_db(
        speech_band, 1800, 3500
    )
    low_reduction_db = _band_db(carved_low_band, 150, 600) - _band_db(
        low_band, 150, 600
    )
    assert speech_reduction_db < -2.0
    assert low_reduction_db > -1.0


def test_ab_qc_classifies_and_lifts_ghost_bed_without_removal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    cfg = {
        "assets_root": "ASSETS",
        "executions_root": "ASSETS/executions",
        "data_root": "data",
        "mix": {
            "underbed_eq": {"enabled": True, "depth_db": 3.0},
            "bed_presence_qc": {
                "enabled": True,
                "fail_closed": True,
                "min_rendered_bed_dbfs": -62.0,
                "bed_lift_step_db": 2.0,
            },
            "intelligibility_qc": {"max_remux_cycles": 2},
        },
    }
    patch_merged_config(monkeypatch, cfg)
    ctx = RunContext("run_underbed_ghost", create=True)
    init_run_meta_for_test(ctx)
    speech = _tone(700, volume=-10.0)
    ghost = _tone(180, volume=-80.0)
    overlays = [
        {
            "audio": ghost,
            "position_ms": 0,
            "role": "bed",
            "music_role": "theme_underscore",
            "asset_id": "valid_bed",
            "cue_id": "bed_1",
            "segment_ids": ["seg_a"],
        }
    ]

    report = analyze_underbed_ab_qc(speech, overlays, mix_cfg=cfg["mix"])
    assert report["verdict"] == "remux_lift"
    assert report["windows"][0]["verdict"] == "inaudible"

    verdict = _check_bed_presence_band(
        ctx,
        assembly_path=ctx.path("master", "assembly.wav"),
        speech_stem=speech,
        segment_timing={"seg_a": (0, 2000)},
        contract={"duck_under_speech_db": 16.0},
        remux_cycle=0,
        overlays=overlays,
    )

    assert verdict == "remux_lift"
    assert len(overlays) == 1
    assert overlays[0]["asset_id"] == "valid_bed"
    assert ctx.read_json("run_meta.json")["mix_underbed_lift_db"] == 2.0
    artifact = ctx.read_json("master/underbed_ab_qc.json")
    assert artifact["automated"] is True
    assert artifact["windows"][0]["rendered_bed_residual_dbfs"] < -62.0
