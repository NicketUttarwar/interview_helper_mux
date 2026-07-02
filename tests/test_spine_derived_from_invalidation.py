from __future__ import annotations

import json

from interview_mux.interview_spine.lineage import (
    build_derived_from,
    can_skip_rebuild,
    derived_from_matches,
)
from interview_mux.run_context import RunContext


def _seed_spine_inputs(ctx: RunContext, *, words: list[dict] | None = None) -> dict:
    words = words or [
        {"text": "hello", "start_ms": 0, "end_ms": 200, "speaker_id": "spk_0"},
        {"text": "world", "start_ms": 250, "end_ms": 500, "speaker_id": "spk_0"},
    ]
    ctx.write_json("transcript/full.json", {"text": "hello world", "words": words})
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
    return derived


def test_transcript_change_invalidates_derived_from(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("spine_inv", create=True)
    prior = _seed_spine_inputs(ctx)
    assert derived_from_matches(ctx, prior)
    assert can_skip_rebuild(ctx)

    ctx.write_json(
        "transcript/full.json",
        {
            "text": "changed transcript",
            "words": [
                {"text": "changed", "start_ms": 0, "end_ms": 300, "speaker_id": "spk_0"},
            ],
        },
    )
    assert not derived_from_matches(ctx, prior)
    assert not can_skip_rebuild(ctx)


def test_preclean_wav_change_invalidates_derived_from(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("spine_preclean", create=True)
    preclean = ctx.path("preclean", "isolated.wav")
    preclean.parent.mkdir(parents=True, exist_ok=True)
    preclean.write_bytes(b"RIFF" + b"\x00" * 40)
    prior = _seed_spine_inputs(ctx)
    assert derived_from_matches(ctx, prior)
    assert can_skip_rebuild(ctx)

    preclean.write_bytes(b"RIFF" + b"\x01" * 40)
    assert not derived_from_matches(ctx, prior)
    assert not can_skip_rebuild(ctx)
