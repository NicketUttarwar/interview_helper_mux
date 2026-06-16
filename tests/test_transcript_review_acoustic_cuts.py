from __future__ import annotations

from interview_mux.stages import transcript_review


def test_refine_chunk_edges_snaps_and_sets_clip_padding():
    words = [
        {"text": "one", "start_ms": 100, "end_ms": 300},
        {"text": "two", "start_ms": 320, "end_ms": 500},
        {"text": "three", "start_ms": 520, "end_ms": 700},
    ]
    chunk = {"start_ms": 150, "end_ms": 650}
    transcript_review._refine_chunk_edges(chunk, words, None)  # type: ignore[arg-type]
    assert chunk["start_ms"] <= 150
    assert chunk["end_ms"] >= 500
    assert "clip_start_ms" in chunk
    assert "clip_end_ms" in chunk
    assert chunk["clip_end_ms"] >= chunk["end_ms"]
