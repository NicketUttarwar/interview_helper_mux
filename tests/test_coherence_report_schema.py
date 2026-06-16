from __future__ import annotations

from interview_mux.coherence.analyze import build_coherence_report
from interview_mux.prompt_validation import validate_coherence_report
from interview_mux.run_context import RunContext
from run_fixtures import minimal_manifest, minimal_manifest_segment


def _minimal_spine(duration_ms: int) -> dict:
    return {
        "schema_version": 1,
        "derived_from": {
            "normalized_wav": "ingest/normalized.wav",
            "transcript": "transcript/full.json",
            "computed_at": "2026-01-01T00:00:00Z",
            "stage": "interview_spine_build",
        },
        "encoders": {"dsp": "numpy_rms_v1", "clap": None, "ssl": None},
        "window_policy": {"window_sec": 10, "hop_sec": 5, "align_to": "words"},
        "speaker_stats": [],
        "windows": [
            {
                "window_id": "win_0001",
                "start_ms": 0,
                "end_ms": 5000,
                "text_span": "intro platform strategy",
                "features": {"rms_p50": 0.2, "pause_before_ms": 0},
            },
            {
                "window_id": "win_0002",
                "start_ms": duration_ms - 5000,
                "end_ms": duration_ms,
                "text_span": "we never ship on schedule actually",
                "features": {"rms_p50": 0.5, "pause_before_ms": 800},
            },
        ],
        "boundary_events": [],
        "retrieval": {"enabled": False, "model_id": None, "sidecar_path": None, "vector_dim": None, "window_count": 2},
    }


def test_coherence_report_schema_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("schema", create=True)
    duration = 31 * 60 * 1000
    ctx.write_json(
        "transcript/full.json",
        {"text": "x", "words": [{"text": "x", "start_ms": 0, "end_ms": duration, "speaker_id": "spk_0"}]},
    )
    ctx.write_json("understanding/interview_spine.json", _minimal_spine(duration))
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "t",
            "topics": [{"name": "Platform", "summary": "Product"}],
            "key_claims": [{"id": "c1", "claim": "We always ship on schedule"}],
            "topic_relationships": [],
        },
    )
    ctx.write_json("segments/manifest.json", minimal_manifest(minimal_manifest_segment("seg_001")))
    report = build_coherence_report(ctx, phase="post_reanchor")
    assert validate_coherence_report(report) == []
    assert report["gate"]["activated"] is True
