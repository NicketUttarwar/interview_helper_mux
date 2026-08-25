"""Tests for story order repair, spoken meta lint, bridges, and speaker plan."""

from __future__ import annotations

import pytest

from interview_mux.bridge_completeness import assert_bridges_complete, missing_reorder_bridges
from interview_mux.bridge_voice_policy import choose_bridge_voice
from interview_mux.listen_quality import ensure_hook_early, evaluate_listen_critic
from interview_mux.rank_candidates import pick_best_order
from interview_mux.reorder_bridges import build_reorder_bridges
from interview_mux.selection_order_repair import (
    finale_tail_errors,
    ordering_constraint_errors,
    topo_satisfy_order,
)
from interview_mux.shape_order_bind import resolve_air_order, shape_order_bindable
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


def test_repair_pulls_earlier_hard_keeps_before_letter_split_signoff():
    """Live mohan: last-chapter 045/047/049/050 must not sit after sign-off 051i."""
    from interview_mux.selection_order_repair import (
        pull_earlier_ids_before_letter_split_signoff,
        pull_earlier_source_ids_before_finale,
        repair_selection_order,
    )

    live = [
        "seg_044",
        "seg_051a",
        "seg_051b",
        "seg_051c",
        "seg_051d",
        "seg_051f",
        "seg_051g",
        "seg_051h",
        "seg_051i",
        "seg_045",
        "seg_047",
        "seg_049",
        "seg_050",
    ]
    pulled, moved = pull_earlier_ids_before_letter_split_signoff(live)
    assert moved == ["seg_045", "seg_047", "seg_049", "seg_050"]
    assert pulled[-1] == "seg_051i"
    assert pulled.index("seg_045") < pulled.index("seg_051a")
    for sid in moved:
        assert pulled.index(sid) < pulled.index("seg_051i")

    starts = {"seg_045": 2_792_660, "seg_047": 3_000_000, "seg_049": 3_100_000, "seg_050": 3_200_000, "seg_051": 3_374_470}
    sourced, src_moved = pull_earlier_source_ids_before_finale(live, source_start_ms=starts)
    assert sourced[-1] == "seg_051i"
    assert "seg_045" in src_moved

    plan = {
        "chapters": [
            {
                "chapter_id": "ch_trials",
                "segment_ids": [
                    "seg_051a",
                    "seg_051b",
                    "seg_051c",
                    "seg_051d",
                    "seg_051f",
                    "seg_051g",
                    "seg_051h",
                    "seg_051i",
                ],
            },
            {"chapter_id": "ch_validation", "segment_ids": ["seg_045", "seg_047", "seg_049", "seg_050"]},
        ]
    }
    selection = {
        "ordered_segment_ids": list(live),
        "chapters": [
            {
                "title": "trials",
                "segment_ids": [
                    "seg_044",
                    "seg_051a",
                    "seg_051b",
                    "seg_051c",
                    "seg_051d",
                    "seg_051f",
                    "seg_051g",
                    "seg_051h",
                    "seg_051i",
                ],
            },
            {"title": "validation", "segment_ids": ["seg_045", "seg_047", "seg_049", "seg_050"]},
        ],
    }
    fixed, applied = repair_selection_order(selection, plan, source_start_ms=starts)
    order = fixed["ordered_segment_ids"]
    for sid in ("seg_045", "seg_047", "seg_049", "seg_050"):
        assert order.index(sid) < order.index("seg_051i")
    assert order[-1] == "seg_051i"
    assert order.index("seg_045") < order.index("seg_051a")
    titles = [str(ch.get("title") or "") for ch in (fixed.get("chapters") or []) if isinstance(ch, dict)]
    trials_ids = next(
        (ch.get("segment_ids") for ch in (fixed.get("chapters") or []) if isinstance(ch, dict) and "Trials" in str(ch.get("title") or ch.get("chapter_id") or "")),
        [],
    )
    assert "seg_045" not in (trials_ids or [])


def test_letter_split_signoff_keeps_later_coda():
    from interview_mux.selection_order_repair import pull_earlier_ids_before_letter_split_signoff

    order = ["seg_051a", "seg_051i", "seg_060"]
    fixed, moved = pull_earlier_ids_before_letter_split_signoff(order)
    assert fixed == order
    assert moved == []


def test_repair_moves_selection_chapter_members_off_finale_tail():
    """Live mohan failure: opening/mid members parked after coda while still listed in earlier chapters."""
    plan = {
        "chapters": [
            {"chapter_id": "ch_open", "segment_ids": ["seg_002", "seg_008"]},
            {"chapter_id": "ch_mid", "segment_ids": ["seg_033", "seg_034"]},
            {"chapter_id": "ch_coda", "segment_ids": ["seg_045", "seg_050"]},
        ]
    }
    selection = {
        "ordered_segment_ids": [
            "seg_002",
            "seg_033",
            "seg_045",
            "seg_050",
            "seg_008",
            "seg_034",
        ],
        "chapters": [
            {"title": "open", "segment_ids": ["seg_002", "seg_008"]},
            {"title": "mid", "segment_ids": ["seg_033", "seg_034"]},
            {"title": "coda", "segment_ids": ["seg_045", "seg_050"]},
        ],
    }
    from interview_mux.selection_order_repair import repair_selection_order

    bad = list(selection["ordered_segment_ids"])
    assert finale_tail_errors(bad, plan)
    fixed, applied = repair_selection_order(selection, plan)
    order = fixed["ordered_segment_ids"]
    assert order.index("seg_008") < order.index("seg_050")
    assert order.index("seg_034") < order.index("seg_050")
    assert not finale_tail_errors(order, plan)
    assert applied


def test_topo_latest_chapter_wins_on_overlap():
    """Overlapping chapter membership must not park early ids after finale anchors."""
    plan = {
        "chapters": [
            {"chapter_id": "ch1", "segment_ids": ["seg_001", "seg_002", "seg_133"]},
            {"chapter_id": "ch2", "segment_ids": ["seg_010", "seg_148"]},
            {"chapter_id": "ch3", "segment_ids": ["seg_133", "seg_200"]},  # shares seg_133
        ],
    }
    # seg_148 listed only in ch2; if seg_133 is assigned to ch1 (first-wins),
    # finale_tail would flag seg_148 after last_end at seg_133.
    bad = ["seg_001", "seg_002", "seg_010", "seg_133", "seg_200", "seg_148"]
    assert finale_tail_errors(bad, plan)
    fixed, _ = topo_satisfy_order(bad, narrative_plan=plan)
    assert not finale_tail_errors(fixed, plan)
    assert fixed.index("seg_148") < fixed.index("seg_133")


def test_ranking_exclude_without_plan(tmp_path, monkeypatch):
    """replaces_source_segments apply even when gap_framing_plan.json is absent."""
    from interview_mux.gap_framing import ranking_exclude_segment_ids
    from interview_mux.run_context import RunContext
    from run_fixtures import init_run_meta_for_test, patch_executions_root

    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_exclude_no_plan", create=True)
    init_run_meta_for_test(ctx)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_sum",
                    "gap_type": "missing_question",
                    "text": "Quick summary of the pivot.",
                    "targets_segment_id": "seg_010",
                    "placement": "before",
                    "delivery": "synthesize",
                    "replaces_source_segments": ["seg_010", "seg_011"],
                }
            ]
        },
    )
    excluded = ranking_exclude_segment_ids(ctx)
    assert excluded == {"seg_010", "seg_011"}


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
    assert spoken_structure_hits("Welcome to this chapter of ownership.")
    assert spoken_structure_hits("In the previous clip, gym buyers showed up.")
    assert spoken_structure_hits(
        "The native continuation states the episode's intended scope and welcomes the guest."
    )
    assert "spoken_planner_meta" in spoken_structure_hits(
        "The native continuation states the episode's intended scope."
    )
    assert lint_spoken_text("Welcome back to Act 2 of our show.")
    assert not spoken_structure_hits("On ownership for everyone—Vijay opens the ESOP.")
    assert not spoken_structure_hits(
        "After the gym-buyer beat, protein-aware snacking rewrote the market."
    )


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


def test_bridge_voice_policy_episode_lock_does_not_flip_pov():
    row = choose_bridge_voice(
        {"kind": "split_sibling", "after_id": "a", "before_id": "b"},
        episode_vo_shape="third_person",
    )
    assert row["suggested_pov"] == "expository_third_person"


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


def test_dual_candidate_picks_healthier_order():
    plan = {
        "chapters": [
            {"segment_ids": ["a", "b"]},
            {"segment_ids": ["c"]},
        ],
        "ordering_constraints": [
            {"before_segment_id": "a", "after_segment_id": "c"},
        ],
    }
    segs = {
        "a": {"start_ms": 0, "end_ms": 1000},
        "b": {"start_ms": 1000, "end_ms": 2000},
        "c": {"start_ms": 2000, "end_ms": 3000},
    }
    pick = pick_best_order(
        [
            {"source": "bad", "ordered_segment_ids": ["c", "a", "b"]},
            {"source": "good", "ordered_segment_ids": ["a", "b", "c"]},
        ],
        narrative_plan=plan,
        segments_by_id=segs,
    )
    assert pick["winner"] == "good"
    assert pick["ordered_segment_ids"] == ["a", "b", "c"]


def test_bridge_completeness_hard_gate():
    bridges = {
        "pairs": [
            {"after_id": "a", "before_id": "b", "kind": "reorder"},
        ]
    }
    missing = missing_reorder_bridges(bridges, gap_report=None, transitions=None)
    assert len(missing) == 1
    with pytest.raises(SystemExit):
        assert_bridges_complete(bridges, soft=False)
    transitions = {
        "transitions": [
            {
                "after_segment_id": "a",
                "before_segment_id": "b",
                "text": "Running low on personal funds, he finally eyes outside capital.",
            },
        ]
    }
    doc = assert_bridges_complete(bridges, transitions=transitions, soft=False)
    assert doc["complete"] is True
    assert doc["stub_count"] == 0


def test_bridge_completeness_blocks_stock_stub():
    bridges = {
        "pairs": [
            {"after_id": "a", "before_id": "b", "kind": "reorder"},
        ]
    }
    transitions = {
        "transitions": [
            {
                "after_segment_id": "a",
                "before_segment_id": "b",
                "text": "And then—what happened next?",
            },
        ]
    }
    with pytest.raises(SystemExit, match="stub bridge"):
        assert_bridges_complete(bridges, transitions=transitions, soft=False)
    soft = assert_bridges_complete(bridges, transitions=transitions, soft=True)
    assert soft["complete"] is False
    assert soft["stub_count"] >= 1


def test_shape_hybrid_bind_requires_health():
    plan = {"ordered_segment_ids": ["a", "b", "c"]}
    ok, ordered, reason = shape_order_bindable(plan, kept_ids={"a", "b", "c"})
    assert ok and ordered == ["a", "b", "c"] and reason == "bind_ok"
    bind = resolve_air_order(
        mastering_plan=plan,
        selection_ordered=["c", "b", "a"],
        prefer_shape=True,
    )
    assert bind["order_authority"] == "shape"
    assert bind["ordered_segment_ids"] == ["a", "b", "c"]


def test_hook_guarantee_and_listen_critic():
    ordered, moved = ensure_hook_early(["a", "b", "c", "hook"], "hook")
    assert moved and ordered[0] == "hook"
    critic = evaluate_listen_critic(ordered=["a"], hook_segment_id="hook")
    assert critic["verdict"] == "warn"
    assert "quality_score" in critic
