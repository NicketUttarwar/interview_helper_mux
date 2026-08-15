"""Unit + integration tests for per-speaker level match and sidechain ducking."""

from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment
from pydub.generators import Sine

from interview_mux.run_context import RunContext
from interview_mux.sidechain_duck import duck_bed_with_sidechain, envelope_duck, speech_window_usable
from interview_mux.sound_design import build_flow1_overlays, mix
from interview_mux.speaker_level_match import (
    apply_speaker_gain,
    build_speaker_gains,
    gain_db_for_speaker,
    measure_level_db,
)
from interview_mux.stages.assembly import build_flow1_edl
from run_fixtures import (
    init_run_meta_for_test,
    minimal_manifest,
    minimal_manifest_segment,
    patch_merged_config,
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


def test_build_speaker_gains_loud_vs_quiet(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "mix": {
                "per_speaker_level_match": {
                    "enabled": True,
                    "max_gain_db": 6.0,
                    "min_speech_sec": 5.0,
                }
            }
        },
    )
    ctx = RunContext("run_spk_levels", create=True)
    quiet = _tone(220, 6000, gain_db=-18.0)
    loud = _tone(330, 6000, gain_db=-3.0)
    source = quiet + loud
    _write_wav(ctx.path("ingest", "normalized.wav"), source)
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_quiet", start_ms=0, end_ms=6000, speaker_id="spk_quiet"),
            minimal_manifest_segment("seg_loud", start_ms=6000, end_ms=12000, speaker_id="spk_loud"),
        ),
    )

    gains = build_speaker_gains(ctx, source)
    quiet_gain = gain_db_for_speaker(gains, "spk_quiet")
    loud_gain = gain_db_for_speaker(gains, "spk_loud")
    assert quiet_gain > 0.5
    assert loud_gain < -0.5
    assert abs(quiet_gain) <= 6.0 + 1e-6
    assert abs(loud_gain) <= 6.0 + 1e-6

    matched_quiet = apply_speaker_gain(quiet, quiet_gain)
    matched_loud = apply_speaker_gain(loud, loud_gain)
    q_db = measure_level_db(matched_quiet)
    l_db = measure_level_db(matched_loud)
    assert q_db is not None and l_db is not None
    assert abs(q_db - l_db) < abs(measure_level_db(quiet) - measure_level_db(loud))  # type: ignore[operator]


def test_speaker_gains_fail_open_below_min_speech(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "mix": {
                "per_speaker_level_match": {
                    "enabled": True,
                    "max_gain_db": 6.0,
                    "min_speech_sec": 5.0,
                }
            }
        },
    )
    ctx = RunContext("run_spk_short", create=True)
    source = _tone(440, 2000, gain_db=-6.0) + _tone(550, 2000, gain_db=-20.0)
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_a", start_ms=0, end_ms=2000, speaker_id="spk_a"),
            minimal_manifest_segment("seg_b", start_ms=2000, end_ms=4000, speaker_id="spk_b"),
        ),
    )
    gains = build_speaker_gains(ctx, source)
    assert gain_db_for_speaker(gains, "spk_a") == 0.0
    assert gain_db_for_speaker(gains, "spk_b") == 0.0


def test_mix_applies_speaker_gains_not_vo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    from interview_mux.config import merged_config

    base_cfg = merged_config()
    mix_cfg = dict(base_cfg.get("mix") or {})
    mix_cfg["per_speaker_level_match"] = {
        "enabled": True,
        "max_gain_db": 6.0,
        "min_speech_sec": 5.0,
    }
    mix_cfg["sidechain_duck"] = {"enabled": False}
    patch_merged_config(
        monkeypatch,
        {
            **base_cfg,
            "mix": mix_cfg,
            "soundscape": {**(base_cfg.get("soundscape") or {}), "enabled": False, "fail_closed": False},
            "sound_design": {**(base_cfg.get("sound_design") or {}), "enabled": False},
            "creative_delivery": {**(base_cfg.get("creative_delivery") or {}), "required": False},
        },
    )
    ctx = RunContext("run_mix_spk", create=True)
    init_run_meta_for_test(ctx)

    quiet = _tone(220, 6000, gain_db=-18.0)
    loud = _tone(330, 6000, gain_db=-3.0)
    source = quiet + loud
    _write_wav(ctx.path("ingest", "normalized.wav"), source)

    vo = _tone(500, 800, gain_db=-12.0)
    vo_path = ctx.path("vo_pickup", "line_vo.wav")
    _write_wav(vo_path, vo)

    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_quiet", start_ms=0, end_ms=6000, speaker_id="spk_quiet"),
            minimal_manifest_segment("seg_loud", start_ms=6000, end_ms=12000, speaker_id="spk_loud"),
        ),
    )
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_quiet", "seg_loud"]},
        segments_by_id={
            "seg_quiet": {"segment_id": "seg_quiet", "start_ms": 0, "end_ms": 6000},
            "seg_loud": {"segment_id": "seg_loud", "start_ms": 6000, "end_ms": 12000},
        },
    )
    # Inject VO before first speech without going through gap machinery
    edl["clips"] = [
        {
            "type": "vo_pickup",
            "line_id": "line_vo",
            "targets_segment_id": "seg_quiet",
            "placement": "before",
            "source_path": "vo_pickup/line_vo.wav",
            "duration_ms": 800,
            "timeline_start_ms": 0,
        },
        *edl["clips"],
    ]
    # Shift speech timeline starts after VO
    for clip in edl["clips"]:
        if clip.get("type") == "speech":
            clip["timeline_start_ms"] = int(clip.get("timeline_start_ms") or 0) + 800
    ctx.write_json("master/edl.json", edl)

    assembly = mix(ctx)
    mixed = AudioSegment.from_file(assembly)
    # VO should remain at original level (first 800 ms)
    vo_out = mixed[:800]
    assert abs(vo_out.dBFS - vo.dBFS) < 1.5
    # Speech halves should be closer after match than raw source halves
    out_quiet = mixed[800:6800]
    out_loud = mixed[6800:12800]
    assert abs(out_quiet.dBFS - out_loud.dBFS) < abs(quiet.dBFS - loud.dBFS) - 2.0


def test_envelope_duck_recovers_in_silence() -> None:
    bed = _tone(120, 2000, gain_db=-6.0)
    speech = _tone(440, 1000, gain_db=-6.0) + AudioSegment.silent(duration=1000, frame_rate=48000)
    ducked = envelope_duck(bed, speech, depth_db=16.0, attack_ms=40, release_ms=200, hop_ms=20)
    speech_half = ducked[:900]
    silence_half = ducked[1200:]
    assert speech_half.rms < silence_half.rms
    # Under speech should approach depth; silence should be materially louder (recovery)
    static_full = bed.apply_gain(-16.0)
    assert speech_half.rms <= static_full[:900].rms * 1.35
    assert silence_half.rms > speech_half.rms * 2.0


def test_envelope_duck_steady_under_amplitude_modulation() -> None:
    """Soft gate should not pump with syllable-like amplitude swings."""
    bed = _tone(120, 2000, gain_db=-6.0)
    loud = _tone(440, 200, gain_db=-3.0)
    quiet = _tone(440, 200, gain_db=-18.0)
    speech = (loud + quiet) * 5
    ducked = envelope_duck(bed, speech, depth_db=12.0, attack_ms=40, release_ms=900, hop_ms=20)
    # Mid-window under continuous speech should stay near full duck, not swing with loud/quiet.
    early = ducked[200:400]
    late = ducked[1400:1600]
    assert abs(early.dBFS - late.dBFS) < 2.5
    static = bed.apply_gain(-12.0)
    assert abs(early.dBFS - static[200:400].dBFS) < 2.0


def test_duck_bed_static_fallback_when_speech_unusable() -> None:
    bed = _tone(120, 800, gain_db=-6.0)
    silent = AudioSegment.silent(duration=800, frame_rate=48000)
    assert not speech_window_usable(silent)
    out = duck_bed_with_sidechain(
        bed,
        silent,
        level_db=-10.0,
        duck_db=16.0,
        cfg={"mix": {"sidechain_duck": {"enabled": True}}},
    )
    expected = bed.apply_gain(-10.0 - 16.0)
    assert abs(out.dBFS - expected.dBFS) < 0.75


def test_sidechain_bed_under_speech_quieter_than_silence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    from interview_mux.config import merged_config

    base_cfg = merged_config()
    mix_cfg = dict(base_cfg.get("mix") or {})
    mix_cfg["sidechain_duck"] = {
        "enabled": True,
        "attack_ms": 20,
        "release_ms": 200,
        "hop_ms": 10,
    }
    mix_cfg["adaptive_level_from_sap"] = False
    patch_merged_config(
        monkeypatch,
        {
            **base_cfg,
            "mix": mix_cfg,
            "soundscape": {**(base_cfg.get("soundscape") or {}), "enabled": False},
            "creative_delivery": {**(base_cfg.get("creative_delivery") or {}), "required": False},
        },
    )
    ctx = RunContext("run_sidechain_bed", create=True)
    init_run_meta_for_test(ctx)

    speech = _tone(300, 1500, gain_db=-3.0) + AudioSegment.silent(duration=1500, frame_rate=48000)
    bed_src = _tone(120, 1000, gain_db=-6.0)
    _write_wav(ctx.path("ingest", "normalized.wav"), speech)
    _write_wav(ctx.path("sound_design", "assets", "ambient_bed.wav"), bed_src)
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_a", start_ms=0, end_ms=3000)),
    )
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
                            "level_db": -12.0,
                            "duck_under_speech_db": 16.0,
                            "fade_in_ms": 20,
                            "fade_out_ms": 20,
                            "crossfade_ms": 0,
                        }
                    ],
                }
            },
            generated={"ambient_bed": "sound_design/assets/ambient_bed.wav"},
        ),
    )

    overlays, stats = build_flow1_overlays(
        ctx,
        segment_timing={"seg_a": (0, 3000)},
        timeline_ms=3000,
        speech_stem=speech,
    )
    assert stats["beds"] == 1
    bed = overlays[0]["audio"]
    assert isinstance(bed, AudioSegment)
    assert bed[:1200].rms < bed[1800:].rms


def test_stingers_not_sidechain_ducked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    from interview_mux.config import merged_config

    base_cfg = merged_config()
    mix_cfg = dict(base_cfg.get("mix") or {})
    mix_cfg["sidechain_duck"] = {"enabled": True}
    mix_cfg["adaptive_level_from_sap"] = False
    patch_merged_config(
        monkeypatch,
        {
            **base_cfg,
            "mix": mix_cfg,
            "soundscape": {**(base_cfg.get("soundscape") or {}), "enabled": False},
            "creative_delivery": {**(base_cfg.get("creative_delivery") or {}), "required": False},
        },
    )
    ctx = RunContext("run_stinger_noduck", create=True)
    speech = _tone(300, 2000, gain_db=-3.0)
    sting = _tone(880, 400, gain_db=0.0)
    _write_wav(ctx.path("ingest", "normalized.wav"), speech)
    _write_wav(ctx.path("sound_design", "assets", "chapter_stinger_warm.wav"), sting)
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_a", start_ms=0, end_ms=2000)),
    )
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
    overlays, stats = build_flow1_overlays(
        ctx,
        segment_timing={"seg_a": (0, 2000)},
        timeline_ms=2000,
        speech_stem=speech,
    )
    assert stats["stingers"] + stats["bridges"] >= 1
    cue_audio = overlays[0]["audio"]
    assert isinstance(cue_audio, AudioSegment)
    # Stinger at level_db 0 should keep body loudness (no duck depth); organic
    # edge fades may trim tips but the mid-body stays near source.
    mid = cue_audio[len(cue_audio) // 3 : (2 * len(cue_audio)) // 3]
    src_mid = sting[len(sting) // 3 : (2 * len(sting)) // 3]
    assert abs(mid.dBFS - src_mid.dBFS) < 2.0
