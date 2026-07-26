from __future__ import annotations

from interview_mux.artifact_completeness import hydrate_manifest_from_boundaries
from interview_mux.run_context import RunContext


def test_hydrate_manifest_from_boundaries_fills_timeline_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    ctx.write_json(
        "segments/boundaries.json",
        {
            "boundaries": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 1500,
                    "speaker_id": "spk_1",
                    "proposed_split_reason": "topic_shift",
                }
            ]
        },
    )
    ctx.write_json(
        "understanding/speakers.json",
        {"speakers": [{"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9}]},
    )
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                {"text": "hello", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_1"},
                {"text": "world", "start_ms": 500, "end_ms": 1200, "speaker_id": "spk_1"},
            ]
        },
    )
    manifest = {
        "segments": [
            {
                "segment_id": "seg_001",
                "type": "interviewee_answer",
                "speaker_id": "spk_1",
                "speaker_role": "interviewee",
                "topic_tags": ["intro"],
            }
        ]
    }
    hydrated = hydrate_manifest_from_boundaries(ctx, manifest)
    seg = hydrated["segments"][0]
    assert seg["start_ms"] == 0
    assert seg["end_ms"] == 1500
    assert seg["text"] == "hello world"
