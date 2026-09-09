from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment
from pydub.generators import Sine

from interview_mux.run_context import RunContext
from interview_mux.stages.assembly import build_flow1_edl, run_mix
from run_fixtures import (
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

def test_mix_overlays_stinger_above_speech(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_mix_test_config(monkeypatch)
    ctx = RunContext("run_mix_001", create=True)

    speech = _tone(440, 2000, gain_db=-6.0)
    sting = _tone(880, 400, gain_db=0.0)
    _write_wav(ctx.path("ingest", "normalized.wav"), speech)
    _write_wav(ctx.path("sound_design", "assets", "chapter_stinger_warm.wav"), sting)

    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_a", start_ms=0, end_ms=2000)),
    )
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_a"]})
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a"]},
        segments_by_id={"seg_a": {"segment_id": "seg_a", "start_ms": 0, "end_ms": 2000}},
    )
    ctx.write_json("master/edl.json", edl)
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            assets=[
                {
                    "asset_id": "chapter_stinger_warm",
                    "role": "chapter_stinger",
                    "description": "warm chapter stinger",
                    "duration_seconds": 0.4,
                }
            ],
            flow_plans={
                "podcast": {
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
            generated={"chapter_stinger_warm": "sound_design/assets/chapter_stinger_warm.wav"},
        ),
    )

    logs: list[str] = []
    orig_log = ctx.log

    def capture(message: str, *, level: str, stage: str, detail: str | None = None, **_: object) -> None:
        logs.append(message)
        orig_log(message, level=level, stage=stage, detail=detail)

    ctx.log = capture  # type: ignore[method-assign]

    assembly = run_mix(ctx)
    assert assembly.is_file()
    assert ctx.is_done("mix")
    assert any("assembly.wav ready" in m for m in logs)

    mixed = AudioSegment.from_file(assembly)
    assert mixed.max >= 0
    assert mixed.rms >= 0

def test_mix_under_segment_bed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_mix_test_config(monkeypatch)
    ctx = RunContext("run_mix_002", create=True)

    speech = _tone(300, 1500, gain_db=-3.0)
    bed_src = _tone(120, 800, gain_db=-12.0)
    _write_wav(ctx.path("ingest", "normalized.wav"), speech)
    _write_wav(ctx.path("sound_design", "assets", "ambient_bed.wav"), bed_src)

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
        sound_design_plan_with(
            assets=[
                {
                    "asset_id": "ambient_bed",
                    "role": "ambient_bed",
                    "description": "quiet ambient bed",
                    "duration_seconds": 2.0,
                }
            ],
            flow_plans={
                "podcast": {
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
            generated={"ambient_bed": "sound_design/assets/ambient_bed.wav"},
        ),
    )
    # Music-only / mix gate: seed passing QA so ambient_bed is not fail-closed.
    ctx.write_json(
        "sound_design/mmaudio_qa.json",
        {
            "version": 1,
            "assets": [
                {
                    "asset_id": "ambient_bed",
                    "role": "ambient_bed",
                    "verdict": "pass",
                    "generation_status": "pass",
                    "silence_detected": False,
                }
            ],
        },
        skip_handoff=True,
        stage_key="mmaudio_sfx",
    )

    assembly = run_mix(ctx)
    mixed = AudioSegment.from_file(assembly)
    assert len(mixed) >= 1500
    from interview_mux.sound_design import build_flow1_overlays

    overlays, stats = build_flow1_overlays(
        ctx, segment_timing={"seg_a": (0, 1500)}, timeline_ms=1500
    )
    assert stats["beds"] == 1
    assert len(overlays) == 1
    assert mixed.max >= speech.max

def test_run_mux_marks_mux_flow1_alias(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_mix_test_config(monkeypatch)
    ctx = RunContext("run_mix_004", create=True)
    _write_wav(ctx.path("ingest", "normalized.wav"), _tone(440, 500))
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_a", start_ms=0, end_ms=500)),
    )
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a"]},
        segments_by_id={"seg_a": {"segment_id": "seg_a", "start_ms": 0, "end_ms": 500}},
    )
    ctx.write_json("master/edl.json", edl)

    from interview_mux.stages import assembly

    assembly.run_mux(ctx)
    assert ctx.is_done("mix")
    assert ctx.is_done("mux_flow1")


def test_mix_writes_realized_edl_times_after_cold_open_pad(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_mix_test_config(monkeypatch)
    ctx = RunContext("run_mix_edl_times", create=True)

    speech = _tone(440, 4000, gain_db=-6.0)
    vo = _tone(660, 1200, gain_db=-3.0)
    _write_wav(ctx.path("ingest", "normalized.wav"), speech)
    _write_wav(ctx.path("master", "transitions", "tr_a_b.wav"), vo)

    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_a", start_ms=0, end_ms=4000)),
    )
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_a"]})
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_a"],
            "clips": [
                {
                    "type": "silence",
                    "air_kind": "opening_music",
                    "preserve_planned_music": True,
                    "timeline_start_ms": 0,
                    "duration_ms": 2000,
                },
                {
                    "type": "speech",
                    "segment_id": "seg_a",
                    "source_start_ms": 0,
                    "source_end_ms": 4000,
                    "timeline_start_ms": 2000,
                    "duration_ms": 4000,
                },
                {
                    "type": "transition",
                    "after_segment_id": "seg_a",
                    "before_segment_id": "seg_b",
                    "text": "From there, the conversation turns.",
                    "source_path": "master/transitions/tr_a_b.wav",
                    "timeline_start_ms": 6000,
                    "duration_ms": 1200,
                },
            ],
            "timeline_duration_ms": 7200,
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            assets=[
                {
                    "asset_id": "show_theme_v1_motif",
                    "role": "theme_cold_open",
                    "description": "cold open motif",
                    "duration_seconds": 14,
                }
            ],
            flow_plans={"podcast": {"cues": []}},
        ),
    )

    from interview_mux.sound_design import mix

    assembly = mix(ctx)
    assert assembly.is_file()
    mixed = AudioSegment.from_file(assembly)
    edl = ctx.read_json("master/edl.json")
    clips = edl["clips"]
    opening = clips[0]
    vo_clip = clips[2]
    assert opening["duration_ms"] >= 14_000
    assert vo_clip["timeline_start_ms"] > 16_000
    assert vo_clip["timeline_start_ms"] != 6000
    assert abs(int(vo_clip["timeline_start_ms"]) + int(vo_clip["duration_ms"]) - len(mixed)) <= 50
    assert edl["timeline_duration_ms"] == len(mixed)
