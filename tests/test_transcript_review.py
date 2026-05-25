from interview_mux.stages.transcript_review import _build_chunks, _replace_words_in_range


def test_build_chunks_from_words_with_pause_split():
    words = [
        {"text": "Hello", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_0", "confidence": 0.99},
        {"text": "world", "start_ms": 1200, "end_ms": 1600, "speaker_id": "spk_0", "confidence": 0.4},
    ]
    full = {"words": words, "segments": []}
    chunks = _build_chunks(full)
    assert len(chunks) == 2
    assert chunks[0]["text"] == "Hello"
    assert chunks[1]["confidence"] == 0.4


def test_replace_words_in_range():
    words = [
        {"text": "foo", "start_ms": 0, "end_ms": 500, "speaker_id": "spk_0"},
        {"text": "bar", "start_ms": 600, "end_ms": 1000, "speaker_id": "spk_0"},
    ]
    out = _replace_words_in_range(words, 0, 500, "food", "spk_0")
    assert len(out) == 2
    assert out[0]["text"] == "food"
    assert out[0].get("corrected")
    assert out[1]["text"] == "bar"
