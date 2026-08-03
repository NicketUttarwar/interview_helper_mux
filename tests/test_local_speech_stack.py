"""Transcript normalization + local speech selection."""

from __future__ import annotations

from interview_mux.local_model_selection import build_speech_selection, speech_tier_for_ram
from interview_mux.transcript_normalize import normalize_legacy_word_transcript, normalize_local_stt


def test_normalize_local_stt_assigns_default_speaker():
    raw = {"text": "hello world", "words": [{"text": "hello", "start_ms": 0, "end_ms": 100}]}
    full, speakers = normalize_local_stt(raw)
    assert full["words"][0]["speaker_id"] == "spk_0"
    assert speakers["speakers"][0]["id"] == "spk_0"


def test_normalize_legacy_word_transcript_words():
    raw = {
        "results": {
            "transcripts": [{"transcript": "hi"}],
            "items": [
                {
                    "type": "pronunciation",
                    "start_time": "0.0",
                    "end_time": "0.5",
                    "speaker_label": "spk_0",
                    "alternatives": [{"content": "hi", "confidence": "0.99"}],
                }
            ],
            "speaker_labels": {"segments": []},
        }
    }
    full, speakers = normalize_legacy_word_transcript(raw)
    assert full["words"][0]["text"] == "hi"
    assert speakers["speakers"][0]["id"] == "spk_0"


def test_speech_tier_for_ram():
    tier = speech_tier_for_ram(8.0)
    assert "whisper" in tier.stt_model_id.lower() or "Whisper" in tier.stt_model_id
    payload = build_speech_selection(source="test")
    assert payload["stt_model_id"]
    assert payload["s2s_model_id"]
