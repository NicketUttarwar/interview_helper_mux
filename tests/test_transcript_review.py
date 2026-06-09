from interview_mux.run_context import RunContext
from interview_mux.stages.transcript_review import (
    _apply_correction_to_range,
    _build_chunks,
    _replace_words_in_range,
    _text_for_word_range,
    apply_corrections,
    get_transcript_state,
    patch_transcript_words,
)


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


def test_get_transcript_state(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    ctx.path("transcript").mkdir(parents=True)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "Hello world",
            "words": [
                {"text": "Hello", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_0", "confidence": 0.99},
                {"text": "world", "start_ms": 450, "end_ms": 900, "speaker_id": "spk_0", "confidence": 0.95},
            ],
        },
    )
    state = get_transcript_state(ctx)
    assert state["ready"] is True
    assert len(state["words"]) == 2
    assert state["duration_ms"] == 900


def test_patch_transcript_words(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    ctx.path("transcript").mkdir(parents=True)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "Hello world",
            "words": [
                {"text": "Hello", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_0"},
                {"text": "world", "start_ms": 450, "end_ms": 900, "speaker_id": "spk_0"},
            ],
        },
    )
    result = patch_transcript_words(ctx, [{"index": 1, "text": "earth"}])
    assert result["updated_count"] == 1
    assert result["text"] == "Hello earth"
    full = ctx.read_json("transcript/full.json")
    assert full["words"][1]["text"] == "earth"
    assert full["words"][1]["corrected"] is True


def test_patch_transcript_words_syncs_review_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    ctx.path("transcript").mkdir(parents=True)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "Hello teh world",
            "words": [
                {"text": "Hello", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_0"},
                {"text": "teh", "start_ms": 450, "end_ms": 700, "speaker_id": "spk_0"},
                {"text": "world", "start_ms": 750, "end_ms": 1100, "speaker_id": "spk_0"},
            ],
        },
    )
    ctx.write_json(
        "transcript/review_queue.json",
        {
            "version": 1,
            "low_confidence_threshold": 0.85,
            "chunk_count": 1,
                "chunks": [
                    {
                        "chunk_id": "tr_0001",
                        "rank": 1,
                        "start_ms": 0,
                        "end_ms": 1100,
                        "speaker_id": "spk_0",
                        "text": "Hello teh world",
                        "confidence": 0.7,
                        "reviewed": False,
                    }
                ],
        },
    )
    ctx.write_json("transcript/corrections.json", {"corrections": {}})

    result = patch_transcript_words(ctx, [{"index": 1, "text": "the"}])
    assert result["synced_chunk_ids"] == ["tr_0001"]

    queue = ctx.read_json("transcript/review_queue.json")
    assert queue["chunks"][0]["corrected_text"] == "Hello the world"
    corrections = ctx.read_json("transcript/corrections.json")["corrections"]["tr_0001"]
    assert corrections["text"] == "Hello the world"
    assert corrections["reviewed"] is False


def test_apply_correction_preserves_dock_word_edits():
    words = [
        {"text": "Hello", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_0", "corrected": True},
        {"text": "the", "start_ms": 450, "end_ms": 700, "speaker_id": "spk_0", "corrected": True},
        {"text": "world", "start_ms": 750, "end_ms": 1100, "speaker_id": "spk_0", "corrected": True},
    ]
    out = _apply_correction_to_range(words, 0, 1100, "Hello teh world", "spk_0")
    assert len(out) == 3
    assert [w["text"] for w in out] == ["Hello", "the", "world"]


def test_apply_correction_word_aligned():
    words = [
        {"text": "Hello", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_0"},
        {"text": "teh", "start_ms": 450, "end_ms": 700, "speaker_id": "spk_0"},
        {"text": "world", "start_ms": 750, "end_ms": 1100, "speaker_id": "spk_0"},
    ]
    out = _apply_correction_to_range(words, 0, 1100, "Hello the world", "spk_0")
    assert len(out) == 3
    assert [w["text"] for w in out] == ["Hello", "the", "world"]
    assert all(w.get("corrected") for w in out)


def test_apply_corrections_skips_already_synced_dock_edits(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    ctx.path("transcript").mkdir(parents=True)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "Hello the world",
            "words": [
                {"text": "Hello", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_0", "corrected": True},
                {"text": "the", "start_ms": 450, "end_ms": 700, "speaker_id": "spk_0", "corrected": True},
                {"text": "world", "start_ms": 750, "end_ms": 1100, "speaker_id": "spk_0", "corrected": True},
            ],
        },
    )
    ctx.write_json(
        "transcript/review_queue.json",
        {
            "version": 1,
            "chunk_count": 1,
                "chunks": [
                    {
                        "chunk_id": "tr_0001",
                        "rank": 1,
                        "start_ms": 0,
                        "end_ms": 1100,
                        "speaker_id": "spk_0",
                        "text": "Hello teh world",
                        "corrected_text": "Hello the world",
                        "confidence": 0.7,
                        "reviewed": True,
                    }
                ],
        },
    )
    ctx.write_json(
        "transcript/corrections.json",
        {"corrections": {"tr_0001": {"text": "Hello the world", "reviewed": True}}},
    )

    apply_corrections(ctx)
    full = ctx.read_json("transcript/full.json")
    assert len(full["words"]) == 3
    assert [w["text"] for w in full["words"]] == ["Hello", "the", "world"]


def test_text_for_word_range():
    words = [
        {"text": "a", "start_ms": 0, "end_ms": 100},
        {"text": "b", "start_ms": 200, "end_ms": 300},
    ]
    assert _text_for_word_range(words, 0, 150) == "a"
    assert _text_for_word_range(words, 0, 350) == "a b"
