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


def test_evaluate_boundary_quality_flags_sparse_ideal_cut_bind():
    from interview_mux.stages.segmentation import evaluate_boundary_quality

    # 56-minute interview with only 4 keep windows → metric_coarse
    doc = {
        "boundaries": [
            {"segment_id": "seg_001", "start_ms": 0, "end_ms": 60_000},
            {"segment_id": "seg_002", "start_ms": 600_000, "end_ms": 720_000},
            {"segment_id": "seg_003", "start_ms": 1_200_000, "end_ms": 1_320_000},
            {"segment_id": "seg_004", "start_ms": 3_000_000, "end_ms": 3_120_000},
        ]
    }
    report = evaluate_boundary_quality(doc, duration_ms=3_350_000)
    assert report["reject"] is True
    assert report["metric_coarse"] is True
    assert report["segment_count"] == 4


def test_evaluate_boundary_quality_accepts_dense_timeline():
    from interview_mux.stages.segmentation import evaluate_boundary_quality

    boundaries = []
    t = 0
    for i in range(80):
        boundaries.append(
            {
                "segment_id": f"seg_{i+1:03d}",
                "start_ms": t,
                "end_ms": t + 40_000,
            }
        )
        t += 40_000
    report = evaluate_boundary_quality({"boundaries": boundaries}, duration_ms=t)
    assert report["reject"] is False
    assert report["segment_count"] == 80


def test_evaluate_boundary_quality_accepts_fine_map_with_minor_coverage_hole():
    """Turn-mapped fine segments must not fail at ~84% coverage (silence gaps)."""
    from interview_mux.stages.segmentation import evaluate_boundary_quality

    duration_ms = 3_347_860
    boundaries = []
    t = 0
    # ~84.5% coverage with hundreds of short segments (baba-like turn map).
    while t < int(duration_ms * 0.845):
        end = min(t + 8_500, int(duration_ms * 0.845))
        if end <= t:
            break
        boundaries.append(
            {
                "segment_id": f"seg_{len(boundaries)+1:03d}",
                "start_ms": t,
                "end_ms": end,
            }
        )
        t = end
    report = evaluate_boundary_quality(
        {"boundaries": boundaries}, duration_ms=duration_ms
    )
    assert report["coverage_ratio"] < 0.85
    assert report["coverage_ratio"] >= 0.70
    assert report["reject"] is False
    assert report["segment_count"] >= 100

def test_resolve_ideal_cuts_air_order_appends_missing():
    seed = {"ordered_segment_ids": ["seg_001", "seg_003"]}
    bind = resolve_ideal_cuts_air_order(
        seed=seed,
        selection_ordered=["seg_001", "seg_002", "seg_003"],
    )
    assert bind["order_authority"] == "ideal_cuts"
    assert bind["ordered_segment_ids"] == ["seg_001", "seg_003", "seg_002"]
