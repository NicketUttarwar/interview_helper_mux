from __future__ import annotations

import json

import numpy as np

from interview_mux.interview_spine.retrieval import query_spine


def _write_spine(ctx, *, windows: list[dict], retrieval_enabled: bool = True) -> None:
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
        "windows": windows,
        "boundary_events": [],
        "retrieval": {
            "enabled": retrieval_enabled,
            "model_id": "laion/clap-htsat-fused" if retrieval_enabled else None,
            "sidecar_path": None,
            "vector_dim": None,
            "window_count": len(windows),
        },
        "speaker_stats": [],
    }
    path = ctx.path("understanding", "interview_spine.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_query_spine_text_fallback_without_embeddings(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    from interview_mux.run_context import RunContext

    ctx = RunContext("retrieval_fb", create=True)
    _write_spine(
        ctx,
        windows=[
            {
                "window_id": "win_0001",
                "start_ms": 0,
                "end_ms": 1000,
                "text_span": "pricing objection from customer",
                "features": {},
            },
            {
                "window_id": "win_0002",
                "start_ms": 1000,
                "end_ms": 2000,
                "text_span": "weather small talk",
                "features": {},
            },
        ],
    )
    monkeypatch.setattr(
        "interview_mux.interview_spine.retrieval._embed_query_text",
        lambda *a, **k: None,
    )
    hits = query_spine(ctx, "pricing objection", top_k=2)
    assert hits
    assert hits[0]["window_id"] == "win_0001"


def test_query_spine_cosine_ranking(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    from interview_mux.run_context import RunContext

    ctx = RunContext("retrieval_cos", create=True)
    sidecar_dir = ctx.path("understanding", "interview_spine")
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    np.savez(
        sidecar_dir / "embeddings.npz",
        embeddings=np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        window_ids=np.array(["win_a", "win_b"]),
    )
    _write_spine(
        ctx,
        windows=[
            {"window_id": "win_a", "start_ms": 0, "end_ms": 500, "text_span": "alpha", "features": {}},
            {"window_id": "win_b", "start_ms": 500, "end_ms": 1000, "text_span": "beta", "features": {}},
        ],
    )
    monkeypatch.setattr(
        "interview_mux.interview_spine.retrieval._embed_query_text",
        lambda *a, **k: np.array([1.0, 0.0], dtype=np.float32),
    )
    hits = query_spine(ctx, "alpha topic", top_k=1)
    assert hits[0]["window_id"] == "win_a"
