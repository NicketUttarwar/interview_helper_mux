from __future__ import annotations

import json

from interview_mux.interview_spine.boundaries import build_boundary_events
from interview_mux.interview_spine.lineage import build_derived_from, derived_from_matches
from interview_mux.interview_spine.windows import build_windows
from interview_mux.prompt_validation import validate_interview_spine
from interview_mux.run_context import RunContext
from interview_mux.stages.interview_spine_stage import run_interview_spine_build


def _sample_words() -> list[dict]:
    return [
        {"text": "hello", "start_ms": 0, "end_ms": 200, "speaker_id": "spk_0"},
        {"text": "world", "start_ms": 250, "end_ms": 500, "speaker_id": "spk_0"},
        {"text": "pause", "start_ms": 1500, "end_ms": 1700, "speaker_id": "spk_1"},
        {"text": "here", "start_ms": 1750, "end_ms": 1950, "speaker_id": "spk_1"},
    ]


def test_build_windows_splits_on_long_pause():
    windows = build_windows(_sample_words(), pace_class="dense", cfg={"window_sec_dense": 6, "hop_sec": 5})
    assert len(windows) >= 2
    assert windows[0]["window_id"] == "win_0001"
    assert windows[0]["text_span"]


def test_build_boundary_events_includes_topic_shift_on_speaker_pause():
    from interview_mux.interview_spine.boundaries import _topic_shift_hint_events

    words = _sample_words()
    events = _topic_shift_hint_events(words)
    assert any(e["type"] == "topic_shift_hint" for e in events)


def test_validate_minimal_spine_schema():
    doc = {
        "schema_version": 1,
        "derived_from": {
            "normalized_wav": "ingest/normalized.wav",
            "transcript": "transcript/full.json",
            "computed_at": "2026-01-01T00:00:00Z",
            "stage": "interview_spine_build",
        },
        "encoders": {"dsp": "numpy_rms_v1", "clap": None, "ssl": None},
        "window_policy": {"window_sec": 10, "hop_sec": 5, "align_to": "words"},
        "windows": [
            {
                "window_id": "win_0001",
                "start_ms": 0,
                "end_ms": 500,
                "text_span": "hello world",
                "features": {"rms_p50": 0.1, "pause_before_ms": 0, "speaking_rate_wpm": 120},
            }
        ],
        "boundary_events": [
            {"time_ms": 500, "type": "pause_ladder", "confidence": 0.5, "sources": ["pause_ladder_400ms"]}
        ],
        "retrieval": {
            "enabled": False,
            "model_id": None,
            "sidecar_path": None,
            "vector_dim": None,
            "window_count": 1,
        },
        "speaker_stats": [],
    }
    assert validate_interview_spine(doc) == []


def test_can_skip_rebuild_when_derived_from_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("spine_skip", create=True)
    ctx.write_json("transcript/full.json", {"text": "hi", "words": _sample_words()})
    sap_path = ctx.path("understanding", "source_acoustic_profile.json")
    sap_path.parent.mkdir(parents=True, exist_ok=True)
    sap_path.write_text(
        json.dumps({"schema_version": 1, "pacing": {"pace_class": "conversational"}}),
        encoding="utf-8",
    )
    wav = ctx.path("ingest", "normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\0" * 40)

    derived = build_derived_from(ctx)
    ctx.write_json(
        "understanding/interview_spine.json",
        {
            "schema_version": 1,
            "derived_from": derived,
            "encoders": {"dsp": "numpy_rms_v1", "clap": None, "ssl": None},
            "window_policy": {"window_sec": 10, "hop_sec": 5, "align_to": "words"},
            "windows": [],
            "boundary_events": [],
            "retrieval": {
                "enabled": False,
                "model_id": None,
                "sidecar_path": None,
                "vector_dim": None,
                "window_count": 0,
            },
            "speaker_stats": [],
        },
    )
    assert derived_from_matches(ctx, derived)

    monkeypatch.setattr(
        "interview_mux.interview_spine.config.spine_cfg",
        lambda cfg=None: {
            "enabled": True,
            "clap_enabled": False,
            "prosody_enabled": False,
            "window_sec_default": 10,
            "hop_sec": 5,
        },
    )
    run_interview_spine_build(ctx)
    assert ctx.is_done("interview_spine_build")
