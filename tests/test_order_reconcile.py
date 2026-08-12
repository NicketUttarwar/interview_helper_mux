"""Selection vs narrative order reconcile."""

from __future__ import annotations

from pathlib import Path

from interview_mux.order_reconcile import (
    material_order_conflicts,
    reconcile_selection_and_narrative,
    rewrite_constraints_to_selection,
)
from run_fixtures import isolated_run_ctx


def test_rewrite_flips_contradictory_constraint() -> None:
    plan = {
        "ordering_constraints": [
            {
                "before_segment_id": "seg_020",
                "after_segment_id": "seg_018",
                "reason": "payoff after setup",
            }
        ]
    }
    ordered = ["seg_018", "seg_019", "seg_020"]
    assert material_order_conflicts(ordered, plan)
    out, notes = rewrite_constraints_to_selection(plan, ordered)
    assert notes
    assert not material_order_conflicts(ordered, out)
    row = out["ordering_constraints"][0]
    assert row["before_segment_id"] == "seg_018"
    assert row["after_segment_id"] == "seg_020"


def test_reconcile_selection_and_narrative_deterministic(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_order")
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_018", "seg_019", "seg_020"]},
        skip_handoff=True,
    )
    ctx.write_json(
        "master/narrative_plan.json",
        {
            "arc_summary": "setup then payoff",
            "chapters": [
                {
                    "chapter_id": "ch_01",
                    "title": "A",
                    "segment_ids": ["seg_018", "seg_019", "seg_020"],
                    "suggested_open_segment_id": "seg_018",
                }
            ],
            "ordering_constraints": [
                {
                    "before_segment_id": "seg_020",
                    "after_segment_id": "seg_018",
                    "reason": "bad",
                }
            ],
        },
        skip_handoff=True,
    )
    report = reconcile_selection_and_narrative(ctx, allow_llm=False, label="test")
    assert report["conflicts_before"]
    assert report["ok"] is True
    assert report["conflicts_after"] == []
    plan = ctx.read_json("master/narrative_plan.json")
    assert not material_order_conflicts(
        ["seg_018", "seg_019", "seg_020"],
        plan if isinstance(plan, dict) else {},
    )
