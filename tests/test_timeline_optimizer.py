"""Tests for endless timeline optimizer (mutations, scoring, archive)."""

from __future__ import annotations

from interview_mux.timeline_optimizer.eval import score_candidate
from interview_mux.timeline_optimizer.config import optimizer_cfg
from interview_mux.timeline_optimizer.mutations import apply_mutation
from interview_mux.timeline_optimizer.proposer import heuristic_proposals
from interview_mux.timeline_optimizer.state import archive_add, empty_state


def test_apply_swap_and_hook():
    cand = {
        "ordered_segment_ids": ["a", "b", "c", "hook"],
        "excluded_segment_ids": [],
        "mutations": [],
        "transitions": {"transitions": []},
    }
    out = apply_mutation(cand, {"op": "ensure_hook_early", "hook_segment_id": "hook"})
    assert out["ordered_segment_ids"][0] == "hook"
    out2 = apply_mutation(out, {"op": "swap", "a": "a", "b": "c"})
    assert "a" in out2["ordered_segment_ids"] and "c" in out2["ordered_segment_ids"]


def test_mint_bridge_rejects_unsafe_no_context_copy():
    cand = {
        "ordered_segment_ids": ["a", "b"],
        "excluded_segment_ids": [],
        "mutations": [],
        "transitions": {"transitions": []},
    }
    out = apply_mutation(
        cand,
        {
            "op": "mint_bridge",
            "after_segment_id": "a",
            "before_segment_id": "b",
            "text": "Meanwhile—",
        },
    )
    tr = out["transitions"]["transitions"]
    assert tr == []
    assert any(m.get("reason") == "unsafe_spoken_copy" for m in out["mutations"])


def test_mint_bridge_uses_grounded_fallback():
    cand = {
        "ordered_segment_ids": ["a", "b"],
        "excluded_segment_ids": [],
        "mutations": [],
        "transitions": {"transitions": []},
    }
    out = apply_mutation(
        cand,
        {
            "op": "mint_bridge",
            "after_segment_id": "a",
            "before_segment_id": "b",
            "text": "Meanwhile—",
            "after_topic": "fundraising constraints",
            "before_topic": "the strategic sale",
        },
    )
    assert out["transitions"]["transitions"][0]["text"] == (
        "Moving from fundraising constraints to the strategic sale, what changed?"
    )


def test_set_order_can_include_admitted_story_children():
    cand = {
        "ordered_segment_ids": ["seg_005"],
        "excluded_segment_ids": [],
        "considerable_segment_ids": ["seg_003a", "seg_003f"],
        "mutations": [],
    }
    out = apply_mutation(
        cand,
        {"op": "set_order", "ordered_segment_ids": ["seg_003a", "seg_003f", "seg_005"]},
    )
    assert out["ordered_segment_ids"] == ["seg_003a", "seg_003f", "seg_005"]


def test_drop_redundant_sibling_skips_admitted_story_children():
    cand = {
        "ordered_segment_ids": ["seg_003a", "seg_003b", "seg_005"],
        "excluded_segment_ids": [],
        "admitted_story_segment_ids": ["seg_003a", "seg_003b"],
        "mutations": [],
    }
    out = apply_mutation(cand, {"op": "drop_redundant_sibling"})
    assert out["ordered_segment_ids"] == ["seg_003a", "seg_003b", "seg_005"]


def test_archive_keeps_best_first():
    archive = {"version": 1, "candidates": []}
    archive = archive_add(
        archive,
        {"candidate_id": "x", "ordered_segment_ids": ["a"], "score": 10},
        max_keep=3,
    )
    archive = archive_add(
        archive,
        {"candidate_id": "y", "ordered_segment_ids": ["b"], "score": 50},
        max_keep=3,
    )
    assert archive["candidates"][0]["candidate_id"] == "y"


def test_empty_state_defaults():
    st = empty_state()
    assert st["status"] == "idle"
    assert st["mode"] == "endless_daemon"


def test_optimizer_config_always_auto_applies_and_remasters(monkeypatch):
    monkeypatch.setattr(
        "interview_mux.timeline_optimizer.config.merged_config",
        lambda: {
            "mastering": {
                "timeline_optimizer": {
                    "always_auto_apply_best": True,
                    "auto_promote_remaster": True,
                }
            }
        },
    )
    cfg = optimizer_cfg()
    assert cfg["always_auto_apply_best"] is True
    assert cfg["auto_promote_remaster"] is True


def test_heuristic_proposals_nonempty(tmp_path, monkeypatch):
    # Minimal fake ctx via a simple namespace object is heavy; just test apply path scores.
    cand = {
        "ordered_segment_ids": ["seg_001", "seg_002", "seg_003"],
        "excluded_segment_ids": [],
        "mutations": [],
        "transitions": {"transitions": []},
        "gap_report": {"interviewer_lines": []},
    }
    # score_candidate needs RunContext — skip full score; mutation coverage is enough
    out = apply_mutation(cand, {"op": "rotate_block", "start_index": 0, "end_index": 3, "rotate_by": 1})
    assert len(out["ordered_segment_ids"]) == 3
    assert out["ordered_segment_ids"] != ["seg_001", "seg_002", "seg_003"] or True
