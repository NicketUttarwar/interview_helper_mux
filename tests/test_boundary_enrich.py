"""Tests for deterministic boundary enrichment (fine-grained segmentation)."""

from __future__ import annotations

from interview_mux.boundary_collate import normalize_boundary_timeline
from interview_mux.boundary_enrich import (
    detect_overloaded_segment_ids,
    enforce_max_segment_duration,
    enrich_boundary_rows,
    split_backchannel_turns,
)


def _words(*pairs: tuple[str, str, int, int]) -> list[dict]:
    return [
        {"text": text, "speaker_id": spk, "start_ms": start, "end_ms": end}
        for text, spk, start, end in pairs
    ]


def test_split_backchannel_turns_isolates_host_affirmation():
    transcript = {
        "words": _words(
            ("So", "spk_1", 0, 200),
            ("we", "spk_1", 210, 400),
            ("built", "spk_1", 410, 700),
            ("yeah", "spk_0", 800, 950),
            ("the", "spk_1", 1000, 1200),
            ("product", "spk_1", 1210, 1500),
        )
        + [
            {"text": f"f{i}", "speaker_id": "spk_1", "start_ms": 1600 + i * 200, "end_ms": 1750 + i * 200}
            for i in range(40)
        ]
    }
    speakers = {
        "speakers": [
            {"speaker_id": "spk_0", "role": "interviewer"},
            {"speaker_id": "spk_1", "role": "interviewee"},
        ]
    }
    rows = [{"start_ms": 0, "end_ms": 9600, "speaker_id": "spk_1", "segment_id": "seg_001"}]
    cfg = {
        "split_backchannels": True,
        "backchannel_max_words": 8,
        "min_segment_duration_ms": 400,
        "default_granularity": "fine",
    }
    out, actions = split_backchannel_turns(rows, transcript, speakers, cfg=cfg)
    assert len(out) >= 3
    assert any(a.get("action") == "split_backchannel" for a in actions)


def test_enforce_max_segment_duration_splits_long_span():
    transcript = {
        "words": [
            {"text": f"w{i}", "speaker_id": "spk_1", "start_ms": i * 1000, "end_ms": i * 1000 + 900}
            for i in range(120)
        ]
    }
    rows = [{"start_ms": 0, "end_ms": 120_000, "speaker_id": "spk_1"}]
    cfg = {"max_segment_duration_ms": 30_000, "min_segment_duration_ms": 4000}
    out, actions = enforce_max_segment_duration(rows, transcript, cfg=cfg)
    assert len(out) >= 3
    assert all(int(r["end_ms"]) - int(r["start_ms"]) <= 30_000 for r in out)
    assert any(a.get("action") == "enforce_max_duration" for a in actions)


def test_detect_overloaded_segment_ids_by_duration_and_topics():
    boundaries = {
        "boundaries": [
            {"segment_id": "seg_001", "start_ms": 0, "end_ms": 100_000},
            {"segment_id": "seg_002", "start_ms": 100_000, "end_ms": 110_000},
        ]
    }
    brief = {
        "topics": [
            {"name": "a", "segment_ids": ["seg_001"]},
            {"name": "b", "segment_ids": ["seg_001"]},
        ]
    }
    manifest = {
        "segments": [
            {"segment_id": "seg_001", "topic_tags": ["alpha", "beta"]},
        ]
    }
    overloaded = detect_overloaded_segment_ids(
        boundaries,
        content_brief=brief,
        manifest=manifest,
        cfg={"max_segment_duration_ms": 60_000},
    )
    assert "seg_001" in overloaded


def test_fine_granularity_skips_micro_merge_for_valid_segments():
    rows = [
        {"start_ms": 0, "end_ms": 5000, "speaker_id": "spk_0"},
        {"start_ms": 5000, "end_ms": 5200, "speaker_id": "spk_0"},
        {"start_ms": 5200, "end_ms": 12_000, "speaker_id": "spk_0"},
    ]
    cfg = {
        "analysis": {
            "artifact_issue_triage": {"boundary_merge_threshold_ms": 500},
            "segmentation": {
                "default_granularity": "fine",
                "min_segment_duration_ms": 4000,
                "boundary_merge_threshold_ms": 200,
            },
        }
    }
    normalized, _ = normalize_boundary_timeline(rows, cfg=cfg)
    assert len(normalized) >= 2


def test_enrich_boundary_rows_respects_min_duration_floor():
    transcript = {
        "words": _words(
            ("hi", "spk_0", 0, 100),
            ("there", "spk_0", 110, 200),
        )
    }
    rows = [{"start_ms": 0, "end_ms": 200, "speaker_id": "spk_0"}]
    out, _ = enrich_boundary_rows(rows, transcript=transcript, cfg={"min_segment_duration_ms": 3000})
    assert len(out) == 1
