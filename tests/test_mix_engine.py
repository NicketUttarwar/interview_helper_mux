from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment
from pydub.generators import Sine

from interview_mux.run_context import RunContext
from interview_mux.sound_design import mix_flow1, mix_flow2
from interview_mux.stages.assembly_flow1 import build_flow1_edl


def _tone(freq: int, duration_ms: int, gain_db: float = 0.0) -> AudioSegment:
    seg = Sine(freq).to_audio_segment(duration=duration_ms)
    seg = seg.set_channels(1).set_frame_rate(48000)
    if gain_db:
        seg = seg.apply_gain(gain_db)
    return seg


def _write_wav(path: Path, seg: AudioSegment) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    seg.export(str(path), format="wav")


def test_mix_flow1_overlays_stinger_above_speech(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_mix_001", create=True)

    speech = _tone(440, 2000, gain_db=-6.0)
    sting = _tone(880, 400, gain_db=0.0)
    _write_wav(ctx.path("ingest", "normalized.wav"), speech)
    _write_wav(ctx.path("sound_design", "assets", "chapter_stinger_warm.wav"), sting)

    ctx.write_json(
        "segments/manifest.json",
        {"segments": [{"segment_id": "seg_a", "start_ms": 0, "end_ms": 2000}]},
    )
    ctx.write_json("flow_1_master/selection.json", {"ordered_segment_ids": ["seg_a"]})
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a"]},
        segments_by_id={"seg_a": {"segment_id": "seg_a", "start_ms": 0, "end_ms": 2000}},
    )
    ctx.write_json("flow_1_master/edl.json", edl)
    ctx.write_json(
        "understanding/sound_design_plan.json",
        {
            "version": 1,
            "assets": [
                {
                    "asset_id": "chapter_stinger_warm",
                    "role": "chapter_stinger",
                    "duration_seconds": 0.4,
                }
            ],
            "flow_plans": {
                "flow1": {
                    "profile": "podcast",
                    "cues": [
                        {
                            "cue_id": "sting_1",
                            "asset_id": "chapter_stinger_warm",
                            "placement": "before_segment",
                            "segment_id": "seg_a",
                            "level_db": 0.0,
                        }
                    ],
                }
            },
            "generated": {"chapter_stinger_warm": "sound_design/assets/chapter_stinger_warm.wav"},
        },
    )

    logs: list[str] = []
    orig_log = ctx.log

    def capture(message: str, *, level: str, stage: str, detail: str | None = None) -> None:
        logs.append(message)
        orig_log(message, level=level, stage=stage, detail=detail)

    ctx.log = capture  # type: ignore[method-assign]

    assembly = mix_flow1(ctx)
    assert assembly.is_file()
    assert ctx.is_done("mix_flow1")
    assert any("assembly.wav ready" in m for m in logs)

    mixed = AudioSegment.from_file(assembly)
    assert mixed.max > speech.max
    assert mixed.rms > speech.rms


def test_mix_flow1_under_segment_bed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_mix_002", create=True)

    speech = _tone(300, 1500, gain_db=-3.0)
    bed_src = _tone(120, 800, gain_db=-12.0)
    _write_wav(ctx.path("ingest", "normalized.wav"), speech)
    _write_wav(ctx.path("sound_design", "assets", "ambient_bed.wav"), bed_src)

    ctx.write_json(
        "segments/manifest.json",
        {"segments": [{"segment_id": "seg_a", "start_ms": 0, "end_ms": 1500}]},
    )
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a"]},
        segments_by_id={"seg_a": {"segment_id": "seg_a", "start_ms": 0, "end_ms": 1500}},
    )
    ctx.write_json("flow_1_master/edl.json", edl)
    ctx.write_json(
        "understanding/sound_design_plan.json",
        {
            "version": 1,
            "assets": [{"asset_id": "ambient_bed", "role": "ambient_bed", "duration_seconds": 2.0}],
            "flow_plans": {
                "flow1": {
                    "cues": [
                        {
                            "cue_id": "bed_1",
                            "asset_id": "ambient_bed",
                            "placement": "under_segment",
                            "segment_id": "seg_a",
                            "level_db": -20.0,
                            "duck_under_speech_db": 16.0,
                        }
                    ],
                }
            },
            "generated": {"ambient_bed": "sound_design/assets/ambient_bed.wav"},
        },
    )

    assembly = mix_flow1(ctx)
    mixed = AudioSegment.from_file(assembly)
    assert len(mixed) >= 1500
    from interview_mux.sound_design import build_flow1_overlays

    overlays, stats = build_flow1_overlays(
        ctx, segment_timing={"seg_a": (0, 1500)}, timeline_ms=1500
    )
    assert stats["beds"] == 1
    assert len(overlays) == 1
    assert mixed.max >= speech.max


def test_mix_flow2_shared_transition_between_clips(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_mix_003", create=True)

    speech = _tone(500, 1000, gain_db=-6.0)
    transition = _tone(1200, 300, gain_db=0.0)
    cold_open = _tone(200, 250, gain_db=-3.0)
    _write_wav(ctx.path("ingest", "normalized.wav"), speech + speech)
    _write_wav(ctx.path("sound_design", "assets", "montage_transition_glue.wav"), transition)
    _write_wav(ctx.path("sound_design", "assets", "cold_open_pulse.wav"), cold_open)

    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {"segment_id": "seg_a", "start_ms": 0, "end_ms": 1000},
                {"segment_id": "seg_b", "start_ms": 1000, "end_ms": 2000},
            ]
        },
    )
    ctx.write_json(
        "flow_2_highlights/selection.json",
        {
            "highlights": [
                {"segment_id": "seg_a", "rank": 1, "start_ms": 0, "end_ms": 1000},
                {"segment_id": "seg_b", "rank": 2, "start_ms": 1000, "end_ms": 2000},
            ]
        },
    )
    ctx.write_json(
        "understanding/sound_design_plan.json",
        {
            "version": 1,
            "assets": [
                {"asset_id": "montage_transition_glue", "role": "transition_stinger", "duration_seconds": 0.3},
                {"asset_id": "cold_open_pulse", "role": "cold_open", "duration_seconds": 0.25},
            ],
            "flow_plans": {
                "flow2": {
                    "cues": [
                        {"cue_id": "open", "asset_id": "cold_open_pulse", "placement": "before_timeline"},
                        {
                            "cue_id": "t12",
                            "asset_id": "montage_transition_glue",
                            "placement": "between_clips",
                            "from_clip_rank": 1,
                            "to_clip_rank": 2,
                        },
                    ],
                }
            },
            "generated": {
                "montage_transition_glue": "sound_design/assets/montage_transition_glue.wav",
                "cold_open_pulse": "sound_design/assets/cold_open_pulse.wav",
            },
        },
    )

    assembly = mix_flow2(ctx)
    assert assembly.is_file()
    assert ctx.is_done("mix_flow2")
    mixed = AudioSegment.from_file(assembly)
    # cold open + 2 clips + 1 transition
    assert len(mixed) > 2000 + 250


def test_run_mux_marks_mux_flow1_alias(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_mix_004", create=True)
    _write_wav(ctx.path("ingest", "normalized.wav"), _tone(440, 500))
    ctx.write_json(
        "segments/manifest.json",
        {"segments": [{"segment_id": "seg_a", "start_ms": 0, "end_ms": 500}]},
    )
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a"]},
        segments_by_id={"seg_a": {"segment_id": "seg_a", "start_ms": 0, "end_ms": 500}},
    )
    ctx.write_json("flow_1_master/edl.json", edl)

    from interview_mux.stages import assembly_flow1

    assembly_flow1.run_mux(ctx)
    assert ctx.is_done("mix_flow1")
    assert ctx.is_done("mux_flow1")
