"""Deterministic narrative constraints must not name segments that no longer exist.

Found on a keyless traversal: chapter_close_hitch re-ran boundary_topic_resplit,
which honoured a seam locked on the first pass and merged seg_004 away. The
materialized cuts and mastering_plan.ordered_segment_ids still listed it, and
narrative_from_talking_points copied them verbatim, so the plan carried an
ordering constraint on a dead segment and the pre-flush barrier refused it:

    ordering_constraint segment seg_004 not in manifest

A real run reaches the same state whenever a second-pass resplit merges.
"""

from __future__ import annotations

from interview_mux.talking_points_authority import narrative_from_talking_points


def _inputs():
    tp = {"talking_points": [
        {"talking_point_id": "tp1", "title": "A", "importance": "core"},
        {"talking_point_id": "tp2", "title": "B", "importance": "core"},
    ]}
    mat = {"cuts": [
        {"segment_id": "seg_001", "talking_point_id": "tp1", "start_ms": 0},
        {"segment_id": "seg_003", "talking_point_id": "tp2", "start_ms": 40000},
        {"segment_id": "seg_004", "talking_point_id": "tp2", "start_ms": 80000},
    ]}
    plan = {"ordered_segment_ids": ["seg_001", "seg_002", "seg_003", "seg_004"]}
    return tp, mat, plan


def _pairs(plan):
    return [(c["before_segment_id"], c["after_segment_id"]) for c in plan["ordering_constraints"]]


def test_merged_away_segment_drops_out_of_constraints_and_chapters() -> None:
    tp, mat, plan = _inputs()
    out = narrative_from_talking_points(
        tp, mat, mastering_plan=plan, manifest_ids={"seg_001", "seg_002", "seg_003"}
    )
    referenced = {s for p in _pairs(out) for s in p}
    referenced |= {s for ch in out["chapters"] for s in ch["segment_ids"]}
    assert "seg_004" not in referenced, out
    # Relative order of the survivors is preserved, not re-derived.
    assert ("seg_002", "seg_003") in _pairs(out)


def test_no_manifest_means_no_filtering() -> None:
    """Callers without a manifest keep the old behaviour exactly."""
    tp, mat, plan = _inputs()
    out = narrative_from_talking_points(tp, mat, mastering_plan=plan)
    assert ("seg_003", "seg_004") in _pairs(out)
