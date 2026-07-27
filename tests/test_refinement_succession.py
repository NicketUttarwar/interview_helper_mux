"""Succession unlocks and mutual exclusion between refinement passes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from interview_mux.refinement_succession import (
    gap_path_resolved,
    is_unlocked,
    mutex_blocked,
    priority_order,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return isolated_run_ctx(tmp_path, "exec_succession_test")


def _raw_write(ctx: RunContext, rel: str, data: dict[str, Any]) -> None:
    """Write JSON straight to disk, bypassing schema validation for test fixtures."""
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_pass_with_no_unlock_rule_is_open_by_default(ctx: RunContext) -> None:
    # gap_framing_recompose has no unlock rule targeting it — succession never locks it.
    assert is_unlocked(ctx, "gap_framing_recompose") is True


def test_transitions_refine_locked_until_gap_path_resolved(ctx: RunContext) -> None:
    assert gap_path_resolved(ctx) is False
    assert is_unlocked(ctx, "transitions_refine") is False


def test_transitions_refine_unlocked_after_gap_framing_recompose_done(ctx: RunContext) -> None:
    ctx.mark_done("gap_framing_recompose", force=True)
    assert gap_path_resolved(ctx) is True
    assert is_unlocked(ctx, "transitions_refine") is True


def test_gap_path_resolved_via_gap_fill_skip_marker(ctx: RunContext) -> None:
    assert gap_path_resolved(ctx) is False
    _raw_write(ctx, "understanding/gap_fill_skip.json", {"reason": "not_eligible"})
    assert gap_path_resolved(ctx) is True
    assert is_unlocked(ctx, "sdp_intent_refine") is True


def test_gap_path_resolved_via_refinement_skip_copy_marker(ctx: RunContext) -> None:
    assert gap_path_resolved(ctx) is False
    _raw_write(ctx, "understanding/refinement_skip_copy.json", {"reason": "pass2_skipped"})
    assert gap_path_resolved(ctx) is True


def test_ranking_refine_unlocked_only_when_topic_holes_present(ctx: RunContext) -> None:
    assert is_unlocked(ctx, "ranking_refine") is False
    _raw_write(ctx, "master/coverage_audit.json", {"uncovered_topics": ["topic_1"]})
    assert is_unlocked(ctx, "ranking_refine") is True


def test_ranking_refine_stays_locked_when_coverage_audit_has_no_holes(ctx: RunContext) -> None:
    _raw_write(ctx, "master/coverage_audit.json", {"uncovered_topics": []})
    assert is_unlocked(ctx, "ranking_refine") is False


def test_mutex_blocks_narrative_arc_refine_when_ranking_refine_done(ctx: RunContext) -> None:
    assert mutex_blocked(ctx, "narrative_arc_refine") is False
    ctx.mark_done("ranking_refine", force=True)
    assert mutex_blocked(ctx, "narrative_arc_refine") is True


def test_mutex_blocks_ranking_refine_when_narrative_arc_refine_activated_in_plan(
    ctx: RunContext,
) -> None:
    ctx.write_json(
        "understanding/refinement_plan.json",
        {
            "run_id": ctx.run_id,
            "schema_version": 1,
            "passes": [
                {
                    "pass_id": "narrative_arc_refine",
                    "status": "activate",
                    "cfi_id": "abc123",
                    "agenda_class": "narrative",
                }
            ],
        },
    )
    assert mutex_blocked(ctx, "ranking_refine") is True


def test_mutex_does_not_block_unrelated_passes(ctx: RunContext) -> None:
    ctx.mark_done("ranking_refine", force=True)
    assert mutex_blocked(ctx, "transitions_refine") is False


def test_priority_order_matches_config_default(ctx: RunContext) -> None:
    order = priority_order()
    assert order[0] == "gap_framing_recompose"
    assert order.index("gap_framing_recompose") < order.index("transitions_refine")
    assert "edl_narrative_refine" in order
