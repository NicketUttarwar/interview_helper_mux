from __future__ import annotations

from interview_mux.nle_state import (
    apply_nle_to_selection,
    apply_segments_with_nle,
    nle_has_operator_edits,
)


def _segments() -> list[dict]:
    return [
        {
            "segment_id": "seg_a",
            "start_ms": 0,
            "end_ms": 10_000,
            "speaker_id": "spk1",
            "type": "interviewee_answer",
        },
        {
            "segment_id": "seg_b",
            "start_ms": 10_000,
            "end_ms": 20_000,
            "speaker_id": "spk1",
            "type": "interviewee_answer",
        },
        {
            "segment_id": "seg_c",
            "start_ms": 20_000,
            "end_ms": 30_000,
            "speaker_id": "spk1",
            "type": "interviewee_answer",
        },
    ]


def test_nle_has_operator_edits_detects_order_and_exclude() -> None:
    assert not nle_has_operator_edits({"playhead_ms": 0})
    assert nle_has_operator_edits({"sequence_order": ["seg_a"]})
    assert nle_has_operator_edits(
        {"segment_overrides": {"seg_a": {"excluded": True}}}
    )


def test_apply_segments_excludes_and_reorders() -> None:
    nle = {
        "sequence_order": ["seg_c", "seg_a"],
        "segment_overrides": {"seg_b": {"excluded": True}},
    }
    out = apply_segments_with_nle(_segments(), nle)
    ids = [s["segment_id"] for s in out]
    assert ids == ["seg_c", "seg_a"]


def test_apply_segments_split_children() -> None:
    nle = {
        "sequence_order": ["seg_aa", "seg_ab", "seg_c"],
        "segment_overrides": {
            "seg_a": {"excluded": True, "split_into": ["seg_aa", "seg_ab"]},
            "seg_aa": {"start_ms": 0, "end_ms": 5000, "parent_id": "seg_a"},
            "seg_ab": {"start_ms": 5000, "end_ms": 10_000, "parent_id": "seg_a"},
        },
    }
    out = apply_segments_with_nle(_segments(), nle)
    by_id = {s["segment_id"]: s for s in out}
    assert "seg_a" not in by_id
    assert by_id["seg_aa"]["end_ms"] == 5000
    assert by_id["seg_ab"]["start_ms"] == 5000


def test_apply_nle_to_selection_merges_order_and_excludes() -> None:
    selection = {
        "ordered_segment_ids": ["seg_a", "seg_b", "seg_c"],
        "excluded_segment_ids": [],
    }
    nle = {
        "sequence_order": ["seg_c", "seg_a"],
        "segment_overrides": {"seg_b": {"excluded": True}},
    }
    by_id = {
        "seg_a": {"segment_id": "seg_a"},
        "seg_b": {"segment_id": "seg_b"},
        "seg_c": {"segment_id": "seg_c"},
    }
    merged = apply_nle_to_selection(selection, nle, segments_by_id=by_id)
    assert merged["ordered_segment_ids"] == ["seg_c", "seg_a"]
    assert any(
        e["segment_id"] == "seg_b" and e["reason"] == "nle_operator"
        for e in merged["excluded_segment_ids"]
    )
    assert merged.get("nle_applied") is True


def test_apply_segments_trim_override() -> None:
    nle = {"segment_overrides": {"seg_a": {"start_ms": 500, "end_ms": 8000}}}
    out = apply_segments_with_nle(_segments(), nle)
    by_id = {s["segment_id"]: s for s in out}
    assert by_id["seg_a"]["start_ms"] == 500
    assert by_id["seg_a"]["end_ms"] == 8000
