from pydub import AudioSegment

from interview_mux.acoustic_profile import compact_for_volley, mix_contract, pacing_one_liner
from interview_mux.audio_timeline import append_with_crossfade
from interview_mux.operator_quality import preclean_acknowledged
from interview_mux.run_context import RunContext


def test_append_with_crossfade_increases_length(tmp_path):
    base = AudioSegment.silent(duration=1000)
    clip = AudioSegment.silent(duration=1000)
    merged = append_with_crossfade(base, clip, 100)
    assert len(merged) > len(base)
    assert len(merged) < len(base) + len(clip)


def test_mix_contract_defaults_when_profile_missing(tmp_path):
    ctx = RunContext("run_099", create=True)
    contract = mix_contract(ctx)
    assert contract["duck_under_speech_db"] == 18.0
    assert contract["underscore_policy"] == "normal"


def test_preclean_acknowledged_false_when_empty():
    assert preclean_acknowledged({}, "before_ingest") is False
    assert preclean_acknowledged({"audio_preclean": {"offered_at": []}}, "before_ingest") is False


def test_compact_for_volley_and_pacing_liner():
    profile = {
        "pacing": {"pace_class": "conversational", "global_wpm": 142, "pause_p50_ms": 680},
        "mix_contract": {"underscore_policy": "sparse", "duck_under_speech_db": 18},
        "placement_hints": {"stinger_density": "low"},
    }
    compact = compact_for_volley(profile)
    assert compact["pace_class"] == "conversational"
    assert compact["mix_contract"]["underscore_policy"] == "sparse"
    assert "stinger_density" in compact["placement_hints"]
    assert "pace=conversational" in pacing_one_liner(profile)
