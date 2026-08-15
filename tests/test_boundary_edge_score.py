"""Tests for per-edge boundary confidence scoring and repair."""

from __future__ import annotations

from interview_mux.boundary_edge_score import (
    build_boundary_review_queue,
    continuation_pair_penalty,
    linguistic_end_penalty,
    repair_low_confidence_edges,
    score_and_repair_boundaries,
    score_boundary_rows,
)
from interview_mux.gap_vo_prior_context import ends_hanging_setup, is_legal_conceptual_hinge
from interview_mux.prompt_validation import validate_boundaries, validate_boundary_review_queue


def _words_pause_ok() -> list[dict]:
    # Two complete sentences with a 1.2s pause between them.
    out = []
    for i, tok in enumerate(["We", "shipped", "the", "product."]):
        out.append(
            {
                "text": tok,
                "start_ms": i * 400,
                "end_ms": i * 400 + 350,
                "speaker_id": "spk_1",
                "confidence": 0.95,
            }
        )
    base = 2800
    for i, tok in enumerate(["Then", "we", "scaled", "up."]):
        out.append(
            {
                "text": tok,
                "start_ms": base + i * 400,
                "end_ms": base + i * 400 + 350,
                "speaker_id": "spk_1",
                "confidence": 0.94,
            }
        )
    return out


def test_ellipsis_and_dangling_interrogative_are_hanging():
    assert ends_hanging_setup("when you're doing the liquid biopsy, like, do...")
    assert ends_hanging_setup("like, do")
    assert ends_hanging_setup("making it actionable,")
    assert not ends_hanging_setup("which refers to personalization.")
    pen, reasons = linguistic_end_penalty("like, do...")
    assert pen >= 0.5
    assert "ellipsis_hang" in reasons or "dangling_interrogative" in reasons


def test_parallel_making_split_penalty():
    pen, reasons = continuation_pair_penalty(
        "our mission is democratize precision oncology, making it actionable,",
        "making it accessible across the country",
    )
    assert pen >= 0.4
    assert "parallel_making_split" in reasons


def test_clean_pause_scores_high():
    rows = [
        {
            "segment_id": "seg_001",
            "start_ms": 0,
            "end_ms": 1550,
            "speaker_id": "spk_1",
            "proposed_split_reason": "topic_shift",
        },
        {
            "segment_id": "seg_002",
            "start_ms": 2800,
            "end_ms": 4200,
            "speaker_id": "spk_1",
            "proposed_split_reason": "topic_shift",
        },
    ]
    spine = [
        {
            "time_ms": 1550,
            "type": "pause_ladder",
            "confidence": 1.0,
            "sources": ["pause_ladder_1200ms", "speaker_turn_pause"],
        },
        {
            "time_ms": 2800,
            "type": "pause_ladder",
            "confidence": 1.0,
            "sources": ["pause_ladder_1200ms"],
        },
    ]
    scored = score_boundary_rows(
        rows,
        transcript={"words": _words_pause_ok()},
        spine_events=spine,
    )
    assert scored[0]["end_edge"]["overall"] >= 0.65
    assert scored[0]["confidence"] >= 0.55
    assert validate_boundaries({"boundaries": scored}) == []


def test_hanging_ellipsis_edge_is_low_or_reject():
    words = [
        {"text": "Okay.", "start_ms": 0, "end_ms": 200, "speaker_id": "spk_0", "confidence": 0.9},
        {"text": "Now,", "start_ms": 300, "end_ms": 450, "speaker_id": "spk_0", "confidence": 0.9},
        {
            "text": "when",
            "start_ms": 500,
            "end_ms": 650,
            "speaker_id": "spk_0",
            "confidence": 0.9,
        },
        {
            "text": "you're",
            "start_ms": 700,
            "end_ms": 850,
            "speaker_id": "spk_0",
            "confidence": 0.9,
        },
        {
            "text": "doing",
            "start_ms": 900,
            "end_ms": 1050,
            "speaker_id": "spk_0",
            "confidence": 0.9,
        },
        {
            "text": "the",
            "start_ms": 1100,
            "end_ms": 1200,
            "speaker_id": "spk_0",
            "confidence": 0.9,
        },
        {
            "text": "liquid",
            "start_ms": 1250,
            "end_ms": 1450,
            "speaker_id": "spk_0",
            "confidence": 0.9,
        },
        {
            "text": "biopsy,",
            "start_ms": 1500,
            "end_ms": 1750,
            "speaker_id": "spk_0",
            "confidence": 0.9,
        },
        {
            "text": "like,",
            "start_ms": 1800,
            "end_ms": 1950,
            "speaker_id": "spk_0",
            "confidence": 0.9,
        },
        {
            "text": "do...",
            "start_ms": 2000,
            "end_ms": 2200,
            "speaker_id": "spk_0",
            "confidence": 0.9,
        },
        {
            "text": "Is",
            "start_ms": 2940,
            "end_ms": 3100,
            "speaker_id": "spk_1",
            "confidence": 0.9,
        },
        {
            "text": "this",
            "start_ms": 3150,
            "end_ms": 3300,
            "speaker_id": "spk_1",
            "confidence": 0.9,
        },
        {
            "text": "circulating?",
            "start_ms": 3350,
            "end_ms": 3700,
            "speaker_id": "spk_1",
            "confidence": 0.9,
        },
    ]
    rows = [
        {
            "segment_id": "seg_004",
            "start_ms": 0,
            "end_ms": 2200,
            "speaker_id": "spk_0",
            "proposed_split_reason": "topic_shift",
        },
        {
            "segment_id": "seg_005",
            "start_ms": 2940,
            "end_ms": 3700,
            "speaker_id": "spk_1",
            "proposed_split_reason": "question_answer_pair",
        },
    ]
    scored = score_boundary_rows(rows, transcript={"words": words}, spine_events=[])
    end = scored[0]["end_edge"]
    assert end["overall"] < 0.65
    assert end["grade"] in {"low", "reject"}
    assert any(
        r in (end.get("reasons") or [])
        for r in ("ellipsis_hang", "dangling_interrogative", "clause_continues_after")
    )
    # Shared hinge predicate also rejects.
    text = "Okay. Now, when you're doing the liquid biopsy, like, do..."
    assert not is_legal_conceptual_hinge(text, words=words, end_ms=2200, next_pause_ms=740)


def test_zero_gap_parallel_split_queued():
    words = []
    # "making it actionable," then immediately "making it accessible."
    toks = [
        ("I", 0, 100),
        ("have,", 120, 250),
        ("our", 300, 400),
        ("mission", 420, 600),
        ("is", 620, 700),
        ("to", 720, 800),
        ("democratize", 820, 1100),
        ("precision", 1120, 1400),
        ("oncology,", 1420, 1700),
        ("making", 1720, 1900),
        ("it", 1920, 2000),
        ("actionable,", 2020, 2300),
        ("making", 2300, 2450),
        ("it", 2470, 2550),
        ("accessible.", 2570, 2900),
    ]
    for t, s, e in toks:
        words.append(
            {
                "text": t,
                "start_ms": s,
                "end_ms": e,
                "speaker_id": "spk_1",
                "confidence": 0.95,
            }
        )
    rows = [
        {
            "segment_id": "seg_026",
            "start_ms": 0,
            "end_ms": 2300,
            "speaker_id": "spk_1",
            "proposed_split_reason": "complete_thought",
        },
        {
            "segment_id": "seg_027",
            "start_ms": 2300,
            "end_ms": 2900,
            "speaker_id": "spk_1",
            "proposed_split_reason": "complete_thought",
        },
    ]
    scored = score_boundary_rows(rows, transcript={"words": words})
    assert scored[0]["end_edge"]["overall"] < 0.65
    queue = build_boundary_review_queue(scored, transcript={"words": words})
    assert queue["item_count"] >= 1
    assert validate_boundary_review_queue(queue) == []


def test_repair_improves_or_queues_without_force_cut():
    # Incomplete end at 2000; legal hinge available at 1550 after "product."
    words = _words_pause_ok()
    # Corrupt first segment end into the middle of the pause poorly.
    rows = [
        {
            "segment_id": "seg_001",
            "start_ms": 0,
            "end_ms": 2000,  # mid-pause hang-ish
            "speaker_id": "spk_1",
            "proposed_split_reason": "pause",
        },
        {
            "segment_id": "seg_002",
            "start_ms": 2800,
            "end_ms": 4200,
            "speaker_id": "spk_1",
            "proposed_split_reason": "topic_shift",
        },
    ]
    repaired, actions = repair_low_confidence_edges(
        rows,
        transcript={"words": words},
        spine_events=[
            {
                "time_ms": 1550,
                "type": "pause_ladder",
                "confidence": 1.0,
                "sources": ["pause_ladder_1200ms", "local_diarization"],
            }
        ],
        cfg={
            "analysis": {
                "segmentation": {
                    "min_segment_duration_ms": 500,
                    "edge_confidence": {
                        "enabled": True,
                        "repair_enabled": True,
                        "repair_below": 0.9,
                        "min_improvement": 0.02,
                        "search_window_ms": 2000,
                    },
                }
            }
        },
    )
    # Either repaired toward the sentence end or left queued — never inverted.
    assert int(repaired[0]["end_ms"]) <= int(repaired[1]["start_ms"])
    assert int(repaired[0]["end_ms"]) > int(repaired[0]["start_ms"])
    doc, queue, _ = score_and_repair_boundaries(
        {"boundaries": rows},
        transcript={"words": words},
        repair=True,
    )
    assert "boundaries" in doc
    assert isinstance(queue.get("items"), list)


def test_old_boundaries_without_edge_fields_still_validate():
    doc = {
        "boundaries": [
            {
                "segment_id": "seg_001",
                "start_ms": 0,
                "end_ms": 1000,
                "proposed_split_reason": "pause",
            }
        ]
    }
    assert validate_boundaries(doc) == []
