from __future__ import annotations

from interview_mux.stages.transcribe_aws import _normalize_transcript


def test_normalize_transcript_handles_null_speaker_labels() -> None:
    raw = {
        "results": {
            "transcripts": [{"transcript": ""}],
            "speaker_labels": None,
            "items": [],
        }
    }
    full, speakers = _normalize_transcript(raw)
    assert full["text"] == ""
    assert full["words"] == []
    assert full["segments"] == []
    assert speakers["speakers"] == []


def test_normalize_transcript_maps_words_and_speakers() -> None:
    raw = {
        "results": {
            "transcripts": [{"transcript": "hello world"}],
            "speaker_labels": {"segments": [{"speaker_label": "spk_0"}]},
            "items": [
                {
                    "type": "pronunciation",
                    "start_time": "0.0",
                    "end_time": "0.5",
                    "speaker_label": "spk_0",
                    "alternatives": [{"content": "hello", "confidence": "0.99"}],
                },
                {
                    "type": "pronunciation",
                    "start_time": "0.5",
                    "end_time": "1.0",
                    "speaker_label": "spk_1",
                    "alternatives": [{"content": "world", "confidence": "0.88"}],
                },
            ],
        }
    }
    full, speakers = _normalize_transcript(raw)
    assert full["text"] == "hello world"
    assert len(full["words"]) == 2
    assert full["words"][0]["text"] == "hello"
    assert full["words"][0]["confidence"] == 0.99
    assert {s["id"] for s in speakers["speakers"]} == {"spk_0", "spk_1"}
