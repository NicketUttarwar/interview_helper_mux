from interview_mux.run_context import RunContext
from interview_mux.stages.transcript_review import (
    _build_chunks,
    _replace_words_in_range,
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
