from interview_mux.operator_snapshots import (
    MANIFEST_REL,
    persist_operator_transcript,
)
from interview_mux.run_context import RunContext
from interview_mux.stages.transcript_review import patch_transcript_words

def test_persist_operator_transcript_writes_independent_files(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    ctx.path("transcript").mkdir(parents=True, exist_ok=True)
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

    persist_operator_transcript(ctx, source="test")

    assert ctx.artifact_exists("operator/transcript_corrected.json")
    assert ctx.artifact_exists("operator/transcript_corrected.txt")
    assert ctx.artifact_exists(MANIFEST_REL)
    corrected = ctx.read_json("operator/transcript_corrected.json")
    assert corrected["text"] == "Hello world"
    assert corrected["run_id"] == ctx.run_id
    assert corrected["source"] == "test"
    assert ctx.path("operator/transcript_corrected.txt").read_text(encoding="utf-8") == "Hello world"

def test_patch_transcript_words_updates_operator_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    ctx.path("transcript").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "Hello world",
            "words": [
                {"text": "Hello", "start_ms": 0, "end_ms": 400},
                {"text": "world", "start_ms": 450, "end_ms": 900},
            ],
        },
    )

    patch_transcript_words(ctx, [{"index": 1, "text": "earth"}])

    full = ctx.read_json("transcript/full.json")
    assert full["text"] == "Hello earth"
