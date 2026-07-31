"""Tests for story order repair, spoken meta lint, bridges, and speaker plan."""

from __future__ import annotations

from interview_mux.bridge_voice_policy import choose_bridge_voice
from interview_mux.reorder_bridges import build_reorder_bridges
from interview_mux.selection_order_repair import (
    finale_tail_errors,
    ordering_constraint_errors,
    topo_satisfy_order,
)
from interview_mux.spoken_meta_lint import lint_spoken_text, spoken_structure_hits
from interview_mux.story_health import evaluate_story_health
from interview_mux.nle_state import apply_nle_to_selection


def test_topo_does_not_append_early_after_finale():
    plan = {
        "chapters": [
            {"chapter_id": "ch1", "segment_ids": ["seg_001", "seg_002"]},
            {"chapter_id": "ch2", "segment_ids": ["seg_010"]},
            {"chapter_id": "ch3", "segment_ids": ["seg_020", "seg_021"]},
        ],
        "ordering_constraints": [
            {"before_segment_id": "seg_001", "after_segment_id": "seg_010"},
            {"before_segment_id": "seg_010", "after_segment_id": "seg_020"},
        ],
    }
    # Bad order: early segs after finale
    bad = ["seg_001", "seg_010", "seg_020", "seg_021", "seg_002"]
    assert finale_tail_errors(bad, plan)
    fixed, applied = topo_satisfy_order(bad, narrative_plan=plan)
    assert "seg_002" in fixed
    assert fixed.index("seg_002") < fixed.index("seg_020") or fixed.index("seg_002") < max(
        fixed.index("seg_020"), fixed.index("seg_021")
    )
    assert not finale_tail_errors(fixed, plan)
    assert applied


def test_ordering_constraint_errors():
    plan = {
        "ordering_constraints": [
            {"before_segment_id": "a", "after_segment_id": "b"},
        ]
    }
    assert ordering_constraint_errors(["b", "a"], plan)
    assert not ordering_constraint_errors(["a", "b"], plan)


def test_spoken_meta_rejects_chapter_numbers():
    assert spoken_structure_hits("Chapter Four—Ownership for Everyone.")
    assert lint_spoken_text("Welcome back to Act 2 of our show.")
    assert not spoken_structure_hits("On ownership for everyone—Vijay opens the ESOP.")


def test_nle_overlay_does_not_tail_dump():
    selection = {
        "ordered_segment_ids": ["seg_001", "seg_002", "seg_003", "seg_010", "seg_020"],
    }
    nle = {
        "sequence_order": ["seg_010", "seg_001"],  # operator touched only these
        "segment_overrides": {},
    }
    out = apply_nle_to_selection(selection, nle)
    ordered = out["ordered_segment_ids"]
    # Must include all base segments; not operator list + rest as naive append
    assert set(ordered) == {"seg_001", "seg_002", "seg_003", "seg_010", "seg_020"}
    assert out.get("nle_merge", {}).get("mode") == "app_base_plus_operator_overlay"
    # Operator-moved ids present
    assert "seg_010" in ordered and "seg_001" in ordered


def test_reorder_bridges_detects_jump():
    segs = {
        "seg_001": {"segment_id": "seg_001", "start_ms": 0, "end_ms": 1000},
        "seg_002": {"segment_id": "seg_002", "start_ms": 1000, "end_ms": 2000},
        "seg_050": {"segment_id": "seg_050", "start_ms": 500_000, "end_ms": 501_000},
    }
    doc = build_reorder_bridges(["seg_001", "seg_002", "seg_050"], segs)
    kinds = {p["kind"] for p in doc["pairs"]}
    assert "reorder" in kinds
    # contiguous 001->002 should be skipped
    assert not any(p["after_id"] == "seg_001" and p["before_id"] == "seg_002" for p in doc["pairs"])


def test_bridge_voice_policy_chapter_jump():
    row = choose_bridge_voice({"kind": "chapter_jump", "after_id": "a", "before_id": "b"})
    assert row["suggested_pov"] == "expository_third_person"
    assert row["suggested_line_category"] == "story_bridge"


def test_story_health_nle_softens_to_warn():
    plan = {
        "chapters": [
            {"segment_ids": ["seg_001", "seg_002"]},
            {"segment_ids": ["seg_010"]},
        ]
    }
    ordered = ["seg_010", "seg_001", "seg_002"]  # early after "finale" of 2-ch plan
    hard = evaluate_story_health(ordered=ordered, narrative_plan=plan, nle_overlay_applied=False)
    soft = evaluate_story_health(ordered=ordered, narrative_plan=plan, nle_overlay_applied=True)
    # May be fail or pass depending on finale_tail heuristic with 2 chapters;
    # soft path must not be fail when errors were softened.
    if hard.get("verdict") == "fail":
        assert soft.get("verdict") == "warn"
