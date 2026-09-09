"""Succession unlocks — slim Pass-2 (gap recompose + framing apply only)."""

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
from run_fixtures import isolated_run_ctx, patch_executions_root, patch_merged_config, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return isolated_run_ctx(tmp_path, "exec_succession_test")


def _raw_write(ctx: RunContext, rel: str, data: dict[str, Any]) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_active_passes_are_open_by_default(ctx: RunContext) -> None:
    assert is_unlocked(ctx, "gap_framing_recompose") is True
    assert is_unlocked(ctx, "selection_framing_apply") is True


def test_gap_path_resolved_via_gap_fill_skip_marker(ctx: RunContext) -> None:
    assert gap_path_resolved(ctx) is False
    _raw_write(ctx, "understanding/gap_fill_skip.json", {"reason": "not_eligible"})
    assert gap_path_resolved(ctx) is True


def test_gap_path_resolved_via_refinement_skip_copy_marker(ctx: RunContext) -> None:
    assert gap_path_resolved(ctx) is False
    _raw_write(ctx, "understanding/refinement_skip_copy.json", {"reason": "pass2_skipped"})
    assert gap_path_resolved(ctx) is True


def test_priority_order_slim_pass2(ctx: RunContext) -> None:
    order = priority_order()
    assert order[0] == "gap_framing_recompose"
    assert order == ["gap_framing_recompose", "selection_framing_apply"]


def test_legacy_unlock_rules_still_honored_when_configured(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Legacy *_refine stubs can still use succession if an operator re-enables them."""
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "refinement_passes": {
                    "succession": {
                        "unlocks": [
                            {
                                "after_accept_or_skip_copy": "gap_framing_recompose",
                                "unlock": "transitions_refine",
                            },
                            {"after_signal": "post_gap_topic_holes", "unlock": "ranking_refine"},
                        ],
                        "mutex": [
                            {
                                "passes": ["narrative_arc_refine", "ranking_refine"],
                                "when": "both_would_reorder",
                            }
                        ],
                        "priority": [
                            "gap_framing_recompose",
                            "selection_framing_apply",
                            "ranking_refine",
                        ],
                    }
                }
            }
        },
    )
    # Re-import path reads patched config via interview_mux.config — also patch catalog module.
    monkeypatch.setattr(
        "interview_mux.refinement_succession.refinement_cfg",
        lambda: {
            "succession": {
                "unlocks": [
                    {
                        "after_accept_or_skip_copy": "gap_framing_recompose",
                        "unlock": "transitions_refine",
                    },
                    {"after_signal": "post_gap_topic_holes", "unlock": "ranking_refine"},
                ],
                "mutex": [
                    {
                        "passes": ["narrative_arc_refine", "ranking_refine"],
                        "when": "both_would_reorder",
                    }
                ],
                "priority": [
                    "gap_framing_recompose",
                    "selection_framing_apply",
                    "ranking_refine",
                ],
            }
        },
    )
    assert is_unlocked(ctx, "transitions_refine") is False
    mark_done_raw(ctx, "gap_framing_recompose")
    assert is_unlocked(ctx, "transitions_refine") is True
    assert is_unlocked(ctx, "ranking_refine") is False
    _raw_write(ctx, "master/coverage_audit.json", {"uncovered_topics": ["topic_1"]})
    assert is_unlocked(ctx, "ranking_refine") is True
    assert mutex_blocked(ctx, "narrative_arc_refine") is False
    mark_done_raw(ctx, "ranking_refine")
    assert mutex_blocked(ctx, "narrative_arc_refine") is True
