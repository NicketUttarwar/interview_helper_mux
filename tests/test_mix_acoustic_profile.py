import wave
from pathlib import Path

from interview_mux.analysis_memory import default_sound_design_plan
from interview_mux.run_context import RunContext
from interview_mux.stages import understanding
from interview_mux.stages.sound_design_vo_finalize import run_sound_design_vo_finalize
from run_fixtures import minimal_gap_line, minimal_gap_report


def _write_test_wav(path: Path) -> None:
    rate = 48000
    frames = int(rate * 0.8)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * frames)


def test_mix_contract_skip_underscore_from_profile(tmp_path):
    ctx = RunContext("run_mix_prof", create=True)
    wav = ctx.path("ingest", "normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    _write_test_wav(wav)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "hello world",
            "words": [
                {"text": "hello", "start_ms": 0, "end_ms": 220, "speaker_id": "spk_0"},
                {"text": "world", "start_ms": 260, "end_ms": 450, "speaker_id": "spk_0"},
            ],
        },
    )
    understanding.run_source_acoustic_profile(ctx)
    profile = ctx.read_json("understanding/source_acoustic_profile.json")
    profile["mix_contract"] = {
        "underscore_policy": "skip",
        "duck_under_speech_db": 20,
        "stinger_max_per_minute": 2,
    }
    ctx.write_json("understanding/source_acoustic_profile.json", profile)

    from interview_mux.acoustic_profile import mix_contract

    contract = mix_contract(ctx)
    assert contract["underscore_policy"] == "skip"
    assert contract["duck_under_speech_db"] == 20.0
    assert contract["stinger_max_per_minute"] == 2


def test_vo_finalize_sets_measured_duration(tmp_path):
    ctx = RunContext("run_vo_fin", create=True)
    pickup = ctx.path("vo_pickup")
    pickup.mkdir(exist_ok=True)
    _write_test_wav(pickup / "line_001.wav")
    ctx.write_json(
        "understanding/gap_report.json",
        minimal_gap_report(
            minimal_gap_line(
                line_id="line_001",
                targets_segment_id="seg_001",
                delivery="record",
            )
        ),
    )
    plan = default_sound_design_plan()
    plan["assets"] = [
        {
            "asset_id": "vo_bridge_1",
            "role": "vo_bridge",
            "description": "Recorded VO bridge",
            "duration_seconds": 1.0,
        }
    ]
    plan["flow_plans"]["podcast"]["cues"] = [
        {
            "cue_id": "cue_vo_1",
            "asset_id": "vo_bridge_1",
            "line_id": "line_001",
            "placement": "before_segment",
        }
    ]
    ctx.write_json("understanding/sound_design_plan.json", plan)
    run_sound_design_vo_finalize(ctx)
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    cue = sdp["flow_plans"]["podcast"]["cues"][0]
    assert cue.get("measured_duration_ms") == 800
