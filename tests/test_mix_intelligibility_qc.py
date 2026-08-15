from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment
from pydub.generators import Sine

from interview_mux import master_qc
from interview_mux.run_context import RunContext
from interview_mux.sound_design import mix
from interview_mux.stages.assembly import build_flow1_edl
from run_fixtures import (
    init_run_meta_for_test,
    minimal_manifest,
    minimal_manifest_segment,
    patch_mix_test_config,
    sound_design_plan_with,
)


def _tone(freq: int, duration_ms: int, gain_db: float = 0.0) -> AudioSegment:
    seg = Sine(freq).to_audio_segment(duration=duration_ms)
    seg = seg.set_channels(1).set_frame_rate(48000)
    if gain_db:
        seg = seg.apply_gain(gain_db)
    return seg


def _write_wav(path: Path, seg: AudioSegment) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    seg.export(str(path), format="wav")


def _bed_plan(*, segment_id: str, level_db: float, duck_db: float) -> dict:
    return sound_design_plan_with(
        assets=[
            {
                "asset_id": "speech_band_bed",
                "role": "ambient_bed",
                "description": "speech-band test bed",
                "duration_seconds": 2.0,
            }
        ],
        flow_plans={
            "podcast": {
                "cues": [
                    {
                        "cue_id": "bed_1",
                        "asset_id": "speech_band_bed",
                        "placement": "under_segment",
                        "segment_id": segment_id,
                        "level_db": level_db,
                        "duck_under_speech_db": duck_db,
                    }
                ],
            }
        },
        generated={"speech_band_bed": "sound_design/assets/speech_band_bed.wav"},
    )


def test_analyze_mix_intelligibility_fails_on_silent_speech_and_loud_bed() -> None:
    speech = AudioSegment.silent(duration=1500, frame_rate=48000)
    loud_bed = _tone(2000, 1500, gain_db=-3.0)
    mix = speech.overlay(loud_bed)
    window = master_qc.BedSpeechWindow(
        segment_id="seg_a",
        start_ms=0,
        end_ms=1500,
        duck_under_speech_db=6.0,
    )
    result = master_qc.analyze_mix_intelligibility(
        mix,
        speech,
        [window],
        flow="podcast",
        source=Path("/tmp/assembly.wav"),
        duck_under_speech_db=16.0,
        qc_cfg={"silent_speech_mix_ceiling_dbfs": -32},
    )
    assert result.ok is False
    assert result.flagged_segment_ids == ["seg_a"]


def test_analyze_mix_intelligibility_passes_when_bed_is_heavily_ducked() -> None:
    speech = AudioSegment.silent(duration=1500, frame_rate=48000)
    quiet_bed = _tone(2000, 1500, gain_db=-40.0)
    mix = speech.overlay(quiet_bed)
    window = master_qc.BedSpeechWindow(
        segment_id="seg_a",
        start_ms=0,
        end_ms=1500,
        duck_under_speech_db=24.0,
    )
    result = master_qc.analyze_mix_intelligibility(
        mix,
        speech,
        [window],
        flow="podcast",
        source=Path("/tmp/assembly.wav"),
        duck_under_speech_db=16.0,
        qc_cfg={"silent_speech_mix_ceiling_dbfs": -32},
    )
    assert result.ok is True
    assert result.flagged_segment_ids == []


def test_mix_intelligibility_warn_on_masking_bed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_mix_test_config(monkeypatch)
    monkeypatch.setattr(
        master_qc,
        "intelligibility_qc_config",
        lambda: {"enabled": True, "silent_speech_mix_ceiling_dbfs": -32},
    )
    ctx = RunContext("run_intelligibility_fail", create=True)
    init_run_meta_for_test(ctx)

    speech = AudioSegment.silent(duration=1500, frame_rate=48000)
    # Loud enough that even MIN_DUCK_DB (12) still exceeds silent speech ceiling.
    bed = _tone(2000, 800, gain_db=12.0)
    _write_wav(ctx.path("ingest", "normalized.wav"), speech)
    _write_wav(ctx.path("sound_design", "assets", "speech_band_bed.wav"), bed)

    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_a", start_ms=0, end_ms=1500)),
    )
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a"]},
        segments_by_id={"seg_a": {"segment_id": "seg_a", "start_ms": 0, "end_ms": 1500}},
    )
    ctx.write_json("master/edl.json", edl)
    ctx.write_json(
        "understanding/sound_design_plan.json",
        _bed_plan(segment_id="seg_a", level_db=0.0, duck_db=4.0),
    )

    details: list[object] = []
    orig_log = ctx.log

    def capture(message: str, **kwargs: object) -> None:
        details.append(kwargs.get("detail"))
        orig_log(message, **kwargs)

    monkeypatch.setattr(ctx, "log", capture)
    mix(ctx)

    meta = ctx.read_json("run_meta.json")
    qc = meta.get("qc_summaries", {}).get("mix_intelligibility", {})
    assert qc.get("passed") is False
    assert "seg_a" in qc.get("flagged_segment_ids", [])
    assert any("intelligibility" in str(d).lower() for d in details if d is not None)


def test_mix_intelligibility_qc_skipped_when_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_mix_test_config(monkeypatch)
    monkeypatch.setattr(master_qc, "intelligibility_qc_config", lambda: {"enabled": False})
    ctx = RunContext("run_intelligibility_skip", create=True)
    init_run_meta_for_test(ctx)

    speech = AudioSegment.silent(duration=1500, frame_rate=48000)
    bed = _tone(2000, 800, gain_db=0.0)
    _write_wav(ctx.path("ingest", "normalized.wav"), speech)
    _write_wav(ctx.path("sound_design", "assets", "speech_band_bed.wav"), bed)

    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_a", start_ms=0, end_ms=1500)),
    )
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a"]},
        segments_by_id={"seg_a": {"segment_id": "seg_a", "start_ms": 0, "end_ms": 1500}},
    )
    ctx.write_json("master/edl.json", edl)
    ctx.write_json(
        "understanding/sound_design_plan.json",
        _bed_plan(segment_id="seg_a", level_db=-6.0, duck_db=4.0),
    )

    mix(ctx)
    meta = ctx.read_json("run_meta.json")
    assert "mix_intelligibility" not in (meta.get("qc_summaries") or {})
