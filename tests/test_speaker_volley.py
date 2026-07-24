"""Tests for speaker volley detection and integrity (podcast conversation units)."""

from __future__ import annotations

from interview_mux.speaker_volley import check_speaker_volley_integrity, detect_speaker_volleys
from interview_mux.speaker_volley_sfx import bind_cues_to_speaker_volleys
from interview_mux.tbiy_mix import annotate_cue_speaker_volley


def test_detect_qa_speaker_volley():
    segs = [
        {"segment_id": "a", "type": "question", "speaker_id": "host"},
        {"segment_id": "b", "type": "answer", "speaker_id": "guest"},
        {"segment_id": "c", "type": "answer", "speaker_id": "guest"},
        {"segment_id": "d", "type": "question", "speaker_id": "host"},
        {"segment_id": "e", "type": "answer", "speaker_id": "guest"},
    ]
    volleys = detect_speaker_volleys(segs)
    assert volleys
    assert volleys[0]["kind"] == "qa"
    assert "a" in volleys[0]["segment_ids"]
    assert "b" in volleys[0]["segment_ids"]


def test_speaker_volley_integrity_split():
    volleys = [
        {
            "speaker_volley_id": "sv_a_b",
            "segment_ids": ["a", "b"],
            "kind": "qa",
            "locked": True,
        }
    ]
    ok, flags = check_speaker_volley_integrity(["a", "x", "b"], volleys)
    assert not ok
    assert any("split" in f for f in flags)


def test_speaker_volley_integrity_ok():
    volleys = [
        {
            "speaker_volley_id": "sv_a_b",
            "segment_ids": ["a", "b"],
            "kind": "qa",
            "locked": True,
        }
    ]
    ok, flags = check_speaker_volley_integrity(["a", "b", "c"], volleys)
    assert ok
    assert flags == []


def test_bind_cues_to_speaker_volleys():
    volleys = [{"speaker_volley_id": "sv1", "segment_ids": ["a", "b"], "locked": True}]
    cues = [{"role": "ambient_bed", "music_transition": "under_speech"}]
    out = bind_cues_to_speaker_volleys(cues, volleys)
    assert out[0].get("speaker_volley_id") == "sv1"


def test_annotate_cue_speaker_volley():
    c = annotate_cue_speaker_volley({"level_db": -24}, "sv1", hinge=True)
    assert c["speaker_volley_id"] == "sv1"
    assert c["speaker_volley_hinge"] is True
