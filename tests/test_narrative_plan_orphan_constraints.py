"""Ordering constraints citing fused-away segments are remapped or dropped (ISSUES 81)."""

from __future__ import annotations

import json

from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment

from interview_mux.artifact_repairs import repair_narrative_plan


def _ctx(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_orphan_constraints")
    man = minimal_manifest(
        minimal_manifest_segment("seg_030", start_ms=0, end_ms=5000, text="a"),
        minimal_manifest_segment("seg_046", start_ms=5000, end_ms=12000, text="b"),
    )
    # seg_046 is the connector-fuse survivor that absorbed seg_052.
    man["segments"][1]["fused_from"] = ["seg_046", "seg_052"]
    path = ctx.final_path("segments", "manifest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(man), encoding="utf-8")
    return ctx


def test_fused_ref_is_remapped_orphan_ref_is_dropped_live_ref_is_kept(tmp_path) -> None:
    ctx = _ctx(tmp_path)
    plan = {
        "chapters": [{"chapter_id": "ch_01", "title": "t", "segment_ids": ["seg_030", "seg_046"]}],
        "ordering_constraints": [
            {"before_segment_id": "seg_052", "after_segment_id": "seg_030", "why": "fused"},
            {"before_segment_id": "seg_057", "after_segment_id": "seg_030", "why": "gone"},
            {"before_segment_id": "seg_030", "after_segment_id": "seg_046", "why": "live"},
        ],
    }
    out, applied = repair_narrative_plan(ctx, plan)
    pairs = [(c["before_segment_id"], c["after_segment_id"]) for c in out["ordering_constraints"]]
    assert pairs == [("seg_046", "seg_030"), ("seg_030", "seg_046")]
    row = next(a for a in applied if a["action"] == "resolve_constraint_refs_to_manifest")
    assert row == {"action": "resolve_constraint_refs_to_manifest", "remapped": 1, "dropped": 1}


def test_constraint_collapsing_onto_one_survivor_is_dropped(tmp_path) -> None:
    ctx = _ctx(tmp_path)
    plan = {
        "chapters": [{"chapter_id": "ch_01", "title": "t", "segment_ids": ["seg_030", "seg_046"]}],
        "ordering_constraints": [
            {"before_segment_id": "seg_052", "after_segment_id": "seg_046"},
        ],
    }
    out, _ = repair_narrative_plan(ctx, plan)
    assert out["ordering_constraints"] == []


def test_the_lint_accepts_the_repaired_plan(tmp_path) -> None:
    from interview_mux.deterministic_lint import _lint_narrative_arc_plan

    ctx = _ctx(tmp_path)
    plan = {
        "chapters": [{"chapter_id": "ch_01", "title": "t", "segment_ids": ["seg_030", "seg_046"]}],
        "ordering_constraints": [
            {"before_segment_id": "seg_052", "after_segment_id": "seg_030"},
        ],
    }
    assert any("not in manifest" in e for e in _lint_narrative_arc_plan(plan, ctx))
    out, _ = repair_narrative_plan(ctx, plan)
    assert not [e for e in _lint_narrative_arc_plan(out, ctx) if "not in manifest" in e]
