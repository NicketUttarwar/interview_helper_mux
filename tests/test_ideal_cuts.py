"""Tests for talking-points-first ideal cuts snap + bind helpers."""

from __future__ import annotations

from interview_mux.ideal_cuts import (
    boundaries_from_snapped_cuts,
    resolve_ideal_cuts_air_order,
    selection_seed_from_snapped,
    snap_ideal_cuts,
)


def _words() -> list[dict]:
    # 0–10s of words at 500ms each
    out = []
    for i in range(20):
        out.append(
            {
                "word": f"w{i}",
                "start_ms": i * 500,
                "end_ms": i * 500 + 480,
                "speaker_id": "spk_0" if i < 10 else "spk_1",
            }
        )
    return out


def test_snap_ideal_cuts_and_seed_order():
    cuts = {
        "cuts": [
            {
                "cut_id": "c1",
                "talking_point_id": "tp_1",
                "start_ms": 510,
                "end_ms": 2490,
                "priority": "must_keep",
                "rationale": "proof",
            },
            {
                "cut_id": "c2",
                "talking_point_id": "tp_2",
                "start_ms": 3000,
                "end_ms": 8000,
                "priority": "should_keep",
                "rationale": "color",
            },
        ]
    }
    snapped = snap_ideal_cuts(cuts, {"words": _words()})
    assert snapped["cut_count"] == 2
    assert all(c.get("snapped") for c in snapped["cuts"])
    bounds = boundaries_from_snapped_cuts(snapped)
    assert bounds["_meta"]["segment_contract"]["publisher_stage"] == "ideal_cuts_materialize"
    assert bounds["_meta"]["segment_contract"]["timeline_valid"] is True
    assert len(bounds["boundaries"]) == 2
    seed = selection_seed_from_snapped(snapped)
    assert seed["ordered_segment_ids"] == ["seg_001", "seg_002"]
    assert seed["must_keep_segment_ids"] == ["seg_001"]


def test_resolve_ideal_cuts_air_order_appends_missing():
    seed = {"ordered_segment_ids": ["seg_001", "seg_003"]}
    bind = resolve_ideal_cuts_air_order(
        seed=seed,
        selection_ordered=["seg_001", "seg_002", "seg_003"],
    )
    assert bind["order_authority"] == "ideal_cuts"
    assert bind["ordered_segment_ids"] == ["seg_001", "seg_003", "seg_002"]
