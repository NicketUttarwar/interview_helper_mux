"""Tests for deterministic boundary enrichment (fine-grained segmentation)."""

from __future__ import annotations

import pytest

from interview_mux.boundary_collate import normalize_boundary_timeline
from interview_mux.boundary_enrich import (
    detect_overloaded_segment_ids,
    enforce_max_segment_duration,
    enrich_boundary_rows,
    split_backchannel_turns,
    split_complete_thought_hinges,
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


def test_split_backchannel_turns_skips_nested_um():
    transcript = {
        "words": _words(
            ("So", "spk_1", 0, 200),
            ("we", "spk_1", 210, 400),
            ("built", "spk_1", 410, 700),
        )
        + [{"text": "um", "speaker_id": "spk_0", "start_ms": 800, "end_ms": 950}]
        + [
            {"text": f"f{i}", "speaker_id": "spk_1", "start_ms": 1600 + i * 200, "end_ms": 1750 + i * 200}
            for i in range(80)
        ]
    }
    speakers = {
        "speakers": [
            {"speaker_id": "spk_0", "role": "interviewer"},
            {"speaker_id": "spk_1", "role": "interviewee"},
        ]
    }
    rows = [{"start_ms": 0, "end_ms": 18_000, "speaker_id": "spk_1", "segment_id": "seg_001"}]
    cfg = {
        "split_backchannels": True,
        "backchannel_max_words": 8,
        "min_segment_duration_ms": 400,
        "default_granularity": "fine",
    }
    out, actions = split_backchannel_turns(rows, transcript, speakers, cfg=cfg)
    assert not any(a.get("action") == "split_backchannel" for a in actions)
    assert len(out) == 1


def test_enforce_max_segment_duration_splits_long_span():
    # Long pauses after complete sentences so splits stay sentence-safe.
    words = []
    t = 0
    i = 0
    while t < 120_000:
        words.append(
            {
                "text": f"word{i}.",
                "speaker_id": "spk_1",
                "start_ms": t,
                "end_ms": t + 400,
            }
        )
        t += 400
        # ≥1s pause between sentences → complete-thought hinge
        t += 1200
        i += 1
    transcript = {"words": words}
    rows = [{"start_ms": 0, "end_ms": 120_000, "speaker_id": "spk_1"}]
    cfg = {"max_segment_duration_ms": 30_000, "min_segment_duration_ms": 4000}
    out, actions = enforce_max_segment_duration(rows, transcript, cfg=cfg)
    assert len(out) >= 3
    assert all(int(r["end_ms"]) - int(r["start_ms"]) <= 30_000 for r in out)
    assert any(a.get("action") == "enforce_max_duration" for a in actions)
    assert not any(a.get("action") == "force_split_midpoint" for a in actions)


def test_enforce_max_skips_midpoint_when_no_complete_hinge():
    # Continuous speech with sub-pause gaps — must not invent a midpoint cut.
    transcript = {
        "words": [
            {
                "text": f"w{i}",
                "speaker_id": "spk_1",
                "start_ms": i * 200,
                "end_ms": i * 200 + 180,
            }
            for i in range(400)
        ]
    }
    rows = [{"start_ms": 0, "end_ms": 80_000, "speaker_id": "spk_1"}]
    cfg = {"max_segment_duration_ms": 20_000, "min_segment_duration_ms": 4000}
    out, actions = enforce_max_segment_duration(rows, transcript, cfg=cfg)
    assert len(out) == 1
    assert out[0].get("airable") is False
    assert out[0].get("overlong_unsplit") is True
    assert any(a.get("action") == "skip_midpoint_split" for a in actions)


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
        {"start_ms": 5000, "end_ms": 5200, "speaker_id": "spk_1"},
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
    normalized, applied = normalize_boundary_timeline(rows, cfg=cfg)
    # Speaker changes keep the two substantive beds; micro may stay or merge.
    assert len(normalized) >= 2
    assert {str(r.get("speaker_id")) for r in normalized} >= {"spk_0"}


def test_same_speaker_small_pause_merges_in_fine_mode():
    rows = [
        {"start_ms": 0, "end_ms": 5000, "speaker_id": "spk_0"},
        {"start_ms": 5200, "end_ms": 12_000, "speaker_id": "spk_0"},
    ]
    cfg = {
        "analysis": {
            "segmentation": {
                "default_granularity": "fine",
                "min_segment_duration_ms": 4000,
                "boundary_merge_threshold_ms": 200,
            },
        }
    }
    normalized, applied = normalize_boundary_timeline(rows, cfg=cfg)
    assert len(normalized) == 1
    assert any(a.get("action") == "merge_same_speaker_boundary" for a in applied)


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


def test_split_complete_thought_hinges_every_legal_pause():
    words = []
    t = 0
    sentences = [
        "We shipped the product in June.",
        "Then the buyers came back every week.",
        "That changed how we staffed the team.",
    ]
    for sent in sentences:
        for tok in sent.split():
            words.append(
                {"text": tok, "speaker_id": "spk_1", "start_ms": t, "end_ms": t + 200}
            )
            t += 220
        t += 1200
    rows = [{"start_ms": 0, "end_ms": t, "speaker_id": "spk_1"}]
    cfg = {"min_segment_duration_ms": 400, "max_segment_duration_ms": 180_000}
    out, actions = split_complete_thought_hinges(rows, {"words": words}, cfg=cfg)
    assert len(out) >= 3
    assert any(a.get("action") == "split_complete_thought" for a in actions)
    assert not any(a.get("action") == "force_split_midpoint" for a in actions)


def test_split_complete_thought_hinges_snaps_topic_shift():
    words = []
    t = 0
    first = "We shipped the product in June and the buyers loved it."
    second = "Hiring became the next constraint for the company."
    for tok in first.split():
        words.append({"text": tok, "speaker_id": "spk_1", "start_ms": t, "end_ms": t + 200})
        t += 220
    topic_at = t + 1300
    t = topic_at
    for tok in second.split():
        words.append({"text": tok, "speaker_id": "spk_1", "start_ms": t, "end_ms": t + 200})
        t += 220
    rows = [{"start_ms": 0, "end_ms": t, "speaker_id": "spk_1"}]
    cfg = {"min_segment_duration_ms": 400, "max_segment_duration_ms": 180_000}
    out, actions = split_complete_thought_hinges(
        rows, {"words": words}, cfg=cfg, topic_split_times=[topic_at]
    )
    assert len(out) >= 2
    assert any(a.get("action") == "split_complete_thought" for a in actions)


def test_stamp_span_speakers_uses_majority_talk_time_not_first_word():
    from interview_mux.boundary_enrich import majority_speaker_for_span, stamp_span_speakers

    words = _words(
        ("Hi", "spk_0", 0, 400),
        ("thanks", "spk_0", 410, 800),
        ("The", "spk_1", 1000, 20000),
        ("science", "spk_1", 20100, 40000),
        ("evolved", "spk_1", 40100, 78000),
    )
    assert majority_speaker_for_span(words, 0, 78000) == "spk_1"
    rows = stamp_span_speakers(
        [{"segment_id": "seg_003", "start_ms": 0, "end_ms": 78000, "speaker_id": "spk_0"}],
        {"words": words},
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer"},
                {"speaker_id": "spk_1", "role": "interviewee"},
            ]
        },
    )
    assert rows[0]["speaker_id"] == "spk_1"
    assert rows[0]["speaker_role"] == "interviewee"


def test_restamp_run_span_speakers_rewrites_manifest_from_words(tmp_path):
    from interview_mux.boundary_enrich import restamp_run_span_speakers
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "restamp_majority")
    words = _words(
        ("Hi", "spk_0", 0, 400),
        ("The", "spk_1", 1000, 40000),
        ("science", "spk_1", 40100, 78000),
    )
    ctx.write_json("transcript/full.json", {"words": words, "text": "Hi The science"}, skip_handoff=True)
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9},
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_003",
                    "start_ms": 0,
                    "end_ms": 78000,
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewer",
                    "type": "interviewer_question",
                    "topic_tags": ["guest"],
                }
            ]
        },
        skip_handoff=True,
    )
    changed = restamp_run_span_speakers(ctx)
    assert changed["manifest"] >= 1
    row = ctx.read_json("segments/manifest.json")["segments"][0]
    assert row["speaker_id"] == "spk_1"
    assert row["speaker_role"] == "interviewee"
    assert row["type"] == "interviewee_answer"


def test_restamp_under_missing_framing_uses_allow_stage_key(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade (MUX_FORENSICS=0): restamp must not inherit missing_framing owner.

    exec_13159: AuthorityDenied persist segments/boundaries.json under
    missing_framing (owner=edl_overlap_repair) — blocked analysis completion.
    """
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.boundary_enrich import restamp_run_span_speakers
    from interview_mux.write_staging import (
        active_stage_id,
        enter_stage_staging,
        exit_stage_staging,
    )
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "restamp_msa_owner")
    words = _words(
        ("The", "spk_1", 0, 2000),
        ("science", "spk_1", 2100, 4000),
    )
    ctx.write_json("transcript/full.json", {"words": words, "text": "The science"}, skip_handoff=True)
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9},
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/boundaries.json",
        {
            "_meta": {"segment_contract": {"publisher_stage": "chapter_close_hitch"}},
            "boundaries": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 4000,
                    "speaker_id": "spk_0",
                    "proposed_split_reason": "test",
                }
            ],
        },
        skip_handoff=True,
        stage_key="boundary_detection",
    )
    enter_stage_staging("missing_framing")
    try:
        assert active_stage_id() == "missing_framing"
        changed = restamp_run_span_speakers(ctx)
    finally:
        exit_stage_staging()
    assert changed["boundaries"] >= 1
    row = ctx.read_json("segments/boundaries.json")["boundaries"][0]
    assert row["speaker_id"] == "spk_1"
