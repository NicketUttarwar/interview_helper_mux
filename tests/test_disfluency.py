from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.disfluency.classify import classify_transcript_words, is_filler_text
from interview_mux.disfluency.config import DEFAULT_FILLER_LEXICON, disfluency_enabled, disfluency_restore_enabled
from interview_mux.disfluency.extract import confirmed_events, recompute_stats, write_skipped_artifact
from interview_mux.disfluency.gaps import build_gap_candidates
from interview_mux.disfluency.restore import build_restore_plan, split_speech_with_disfluencies
from interview_mux.gates import check_disfluency_review_pending, require_disfluency_review_clear
from interview_mux.run_context import RunContext
from interview_mux.stages.assembly_flow1 import build_flow1_edl
from interview_mux.stages.disfluency import (
    mark_disfluency_review_complete,
    run_disfluency_extract,
    update_event_review,
)
from run_fixtures import isolated_run_ctx, patch_merged_config


def test_is_filler_text_lexicon() -> None:
    assert is_filler_text("um", DEFAULT_FILLER_LEXICON)
    assert not is_filler_text("hello", DEFAULT_FILLER_LEXICON)


def test_build_gap_candidates_filters_duration() -> None:
    words = [
        {"start_ms": 0, "end_ms": 1000, "text": "hello"},
        {"start_ms": 1200, "end_ms": 2000, "text": "world"},
    ]
    gaps = build_gap_candidates(words, gap_min_ms=80, gap_max_ms=2500, pad_ms=10)
    assert len(gaps) == 1
    assert gaps[0]["gap_ms"] == 200


def test_classify_transcript_words_finds_um() -> None:
    words = [{"start_ms": 100, "end_ms": 400, "text": "um", "speaker_id": "spk_0"}]
    events = classify_transcript_words(words, DEFAULT_FILLER_LEXICON)
    assert len(events) == 1
    assert events[0]["source"] == "transcript_lexicon"


def test_split_speech_with_disfluencies_inserts_clip() -> None:
    events = [
        {
            "event_id": "fill_0001",
            "start_ms": 5000,
            "end_ms": 5300,
            "clip_path": "transcript/disfluency_clips/fill_0001.wav",
            "text": "um",
        }
    ]
    clips, end = split_speech_with_disfluencies(
        segment_id="seg_a",
        seg_start_ms=0,
        seg_end_ms=10_000,
        events=events,
        timeline_ms=0,
        settings={"min_speech_slice_ms": 200},
    )
    types = [c["type"] for c in clips]
    assert "speech" in types
    assert "disfluency" in types
    assert end == 10_000


def test_build_flow1_edl_with_disfluency_restore() -> None:
    segments = {"seg_a": {"segment_id": "seg_a", "start_ms": 0, "end_ms": 10_000}}
    events = [
        {
            "event_id": "fill_0001",
            "start_ms": 4000,
            "end_ms": 4300,
            "clip_path": "transcript/disfluency_clips/fill_0001.wav",
            "text": "um",
        }
    ]
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a"]},
        segments_by_id=segments,
        disfluency_events=events,
        restore_enabled=True,
    )
    assert edl["disfluency_restore_enabled"] is True
    assert edl["disfluency_clip_count"] >= 1


def test_disfluency_extract_disabled_auto_completes(tmp_path: Path, monkeypatch) -> None:
    cfg = {"disfluency_extract": {"enabled": False}, "disfluency_restore": {"enabled": True}}
    patch_merged_config(monkeypatch, cfg)
    ctx = isolated_run_ctx(tmp_path, "run_df_off")
    ctx.write_json("transcript/full.json", {"words": []})
    run_disfluency_extract(ctx)
    doc = ctx.read_json("transcript/disfluencies.json")
    assert doc["status"] == "skipped"
    assert ctx.is_done("disfluency_extract")
    assert ctx.is_done("disfluency_review")


def test_disfluency_review_gate_pending(tmp_path: Path, monkeypatch) -> None:
    cfg = {"disfluency_extract": {"enabled": True}, "disfluency_restore": {"enabled": True}}
    patch_merged_config(monkeypatch, cfg)
    ctx = isolated_run_ctx(tmp_path, "run_df_gate")
    ctx.write_json(
        "transcript/disfluencies.json",
        {
            "schema_version": 1,
            "status": "ready",
            "events": [
                {
                    "event_id": "fill_0001",
                    "start_ms": 1,
                    "end_ms": 2,
                    "review_status": "pending",
                }
            ],
            "stats": {"total": 1, "pending": 1, "confirmed": 0, "rejected": 0},
        },
    )
    ctx.mark_done("disfluency_extract")
    assert check_disfluency_review_pending(ctx) is True
    update_event_review(ctx, "fill_0001", review_status="confirmed")
    assert check_disfluency_review_pending(ctx) is True
    mark_disfluency_review_complete(ctx)
    assert check_disfluency_review_pending(ctx) is False


def test_require_disfluency_review_clear_raises(tmp_path: Path, monkeypatch) -> None:
    cfg = {"disfluency_extract": {"enabled": True}}
    patch_merged_config(monkeypatch, cfg)
    ctx = isolated_run_ctx(tmp_path, "run_df_req")
    ctx.write_json(
        "transcript/disfluencies.json",
        {
            "schema_version": 1,
            "status": "ready",
            "events": [{"event_id": "x", "start_ms": 0, "end_ms": 1, "review_status": "pending"}],
            "stats": {},
        },
    )
    ctx.mark_done("disfluency_extract")
    with pytest.raises(SystemExit, match="Disfluency review"):
        require_disfluency_review_clear(ctx)


def test_confirmed_events_respects_include_flag() -> None:
    doc = {
        "events": [
            {"event_id": "a", "review_status": "confirmed", "include_in_restore": True},
            {"event_id": "b", "review_status": "confirmed", "include_in_restore": False},
            {"event_id": "c", "review_status": "rejected"},
        ]
    }
    ids = {e["event_id"] for e in confirmed_events(doc)}
    assert ids == {"a"}


def test_disfluency_restore_run_meta_override(tmp_path: Path, monkeypatch) -> None:
    cfg = {"disfluency_restore": {"enabled": True}}
    patch_merged_config(monkeypatch, cfg)
    ctx = isolated_run_ctx(tmp_path, "run_restore")
    ctx.write_json("run_meta.json", {"disfluency_restore": {"enabled": False}})
    meta = ctx.read_json("run_meta.json")
    assert disfluency_restore_enabled(run_meta=meta) is False
    assert disfluency_enabled(cfg) is True
