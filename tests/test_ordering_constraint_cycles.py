"""Narrative ordering constraints are made satisfiable before anything consumes them (ISSUES 173).

exec_022: narrative_arc_plan returned seg_017 -> seg_024 -> seg_015 -> seg_016 -> seg_017;
full_master_ranking answered partial ("ordering constraints create a cycle"),
its commit was refused twice and the stage failed.
"""

from __future__ import annotations

from interview_mux.artifact_repairs import break_ordering_constraint_cycles


def _c(a: str, b: str) -> dict:
    return {"before_segment_id": a, "after_segment_id": b}


STARTS = {"seg_013": 1, "seg_015": 1_492_220, "seg_016": 1_615_640, "seg_017": 1_668_190, "seg_020": 2, "seg_024": 2_122_380}


def test_exec_022_cycle_drops_the_backward_tape_edge() -> None:
    rows = [_c("seg_017", "seg_024"), _c("seg_024", "seg_015"), _c("seg_015", "seg_016"), _c("seg_016", "seg_017"), _c("seg_013", "seg_020")]
    kept, dropped = break_ordering_constraint_cycles(rows, STARTS)
    assert dropped == [{"before": "seg_024", "after": "seg_015"}]
    assert len(kept) == 4


def test_acyclic_constraints_are_untouched() -> None:
    rows = [_c("seg_015", "seg_016"), _c("seg_016", "seg_017")]
    kept, dropped = break_ordering_constraint_cycles(rows, STARTS)
    assert kept == rows and dropped == []


def test_two_node_cycle_without_starts_still_breaks() -> None:
    rows = [_c("a", "b"), _c("b", "a")]
    kept, dropped = break_ordering_constraint_cycles(rows, {})
    assert len(kept) == 1 and len(dropped) == 1


def test_two_independent_cycles_both_break() -> None:
    rows = [_c("a", "b"), _c("b", "a"), _c("c", "d"), _c("d", "e"), _c("e", "c")]
    kept, dropped = break_ordering_constraint_cycles(rows, {})
    assert len(dropped) == 2
    _, again = break_ordering_constraint_cycles(kept, {})
    assert again == []
