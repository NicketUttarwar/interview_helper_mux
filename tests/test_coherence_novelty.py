from __future__ import annotations

import numpy as np

from interview_mux.coherence.novelty import compute_novelty_scores
from interview_mux.run_context import RunContext


def test_novelty_prosody_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("novelty_fb", create=True)
    windows = [
        {
            "window_id": "win_0001",
            "start_ms": 0,
            "end_ms": 5000,
            "features": {"rms_p50": 0.1, "pause_before_ms": 0, "f0_median_hz": 120},
        },
        {
            "window_id": "win_0002",
            "start_ms": 5000,
            "end_ms": 10000,
            "features": {"rms_p50": 0.8, "pause_before_ms": 900, "f0_median_hz": 220},
        },
    ]
    scores = compute_novelty_scores(windows, ctx)
    assert scores["win_0002"] > 0.15


def test_novelty_clap_delta(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("novelty_clap", create=True)
    sidecar = ctx.path("understanding", "interview_spine", "embeddings.npz")
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    emb = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    np.savez(sidecar, embeddings=emb, window_ids=np.array(["win_0001", "win_0002"]))
    windows = [
        {"window_id": "win_0001", "start_ms": 0, "end_ms": 5000, "features": {}},
        {"window_id": "win_0002", "start_ms": 5000, "end_ms": 10000, "features": {}},
    ]
    scores = compute_novelty_scores(windows, ctx)
    assert scores["win_0002"] == 1.0
