from __future__ import annotations

from interview_mux.transcript_sampling import (
    stratified_transcript_samples,
    stratified_transcript_samples_from_words,
)


def test_stratified_samples_short_text_single_window():
    text = "hello world"
    out = stratified_transcript_samples(text, total_chars=1000)
    assert out == {"opening": "hello world"}


def test_stratified_samples_long_text_three_windows():
    text = "a" * 90000
    out = stratified_transcript_samples(text, total_chars=24000, windows=3)
    assert set(out.keys()) == {"opening", "middle", "closing"}
    assert sum(len(v) for v in out.values()) <= 24000 + 10


def test_stratified_samples_from_words_returns_three_windows():
    words = [{"text": f"word{i}", "start_ms": i * 10, "end_ms": i * 10 + 5} for i in range(200)]
    text = " ".join(w["text"] for w in words)
    out = stratified_transcript_samples_from_words(words, total_chars=500)
    assert set(out.keys()) == {"opening", "middle", "closing"}
    assert sum(len(v) for v in out.values()) <= 500 + 10
    assert len(text) > 500


def test_stratified_samples_from_words_prefix_speaker_turns():
    words = []
    for i in range(40):
        words.append(
            {
                "text": "hello" if i < 20 else "thanks",
                "speaker_id": "spk_0" if i < 20 else "spk_1",
                "start_ms": i * 10,
                "end_ms": i * 10 + 5,
            }
        )
    out = stratified_transcript_samples_from_words(words, total_chars=4000)
    blob = " ".join(out.values())
    assert "[spk_0]" in blob
    assert "[spk_1]" in blob
