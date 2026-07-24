"""Tests for gap framing gates, succinct-master helpers, and skip paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.gap_framing import (
    build_gap_framing_plan,
    infer_line_category,
    normalize_interviewer_line,
    ranking_exclude_segment_ids,
    validate_line_word_limits,
    word_limit_for_category,
)
from interview_mux.gap_vo_gates import (
    check_gap_framing_decision_pending,
    gap_framing_enabled,
    set_gap_framing_enabled,
    set_gap_vo_delivery,
)
from interview_mux.run_context import RunContext
from interview_mux.stages.gaps import gap_compose_stage_done
from run_fixtures import init_run_meta_for_test, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_gap_framing", create=True)
    init_run_meta_for_test(run)
    run.write_json("understanding/source_topology.json", {"topology_class": "one_on_one_asymmetric"})
    run.mark_done("source_topology_build", force=True)
    return run


def test_default_gap_framing_disabled_without_decision(ctx: RunContext) -> None:
    assert gap_framing_enabled(ctx) is False


def test_gap_framing_decision_pending_after_topology(ctx: RunContext) -> None:
    from interview_mux.v2.config import ANALYSIS_ORDER

    idx = ANALYSIS_ORDER.index("missing_framing")
    for sid in ANALYSIS_ORDER[:idx]:
        ctx.mark_done(sid, force=True)
    assert check_gap_framing_decision_pending(ctx) is True


def test_set_gap_framing_no_skips_compose_stage(ctx: RunContext) -> None:
    set_gap_framing_enabled(ctx, False)
    assert gap_framing_enabled(ctx) is False
    assert ctx.is_done("missing_framing")
    assert ctx.is_done("gap_framing_compose")
    assert gap_compose_stage_done(ctx)


def test_line_category_word_limits() -> None:
    assert word_limit_for_category("framing_question") == 60
    assert word_limit_for_category("segment_summary") == 80
    errors = validate_line_word_limits(
        [
            {
                "line_id": "vo_q",
                "line_category": "framing_question",
                "text": " ".join(["word"] * 65),
            }
        ]
    )
    assert errors


def test_infer_line_category_from_gap_type() -> None:
    assert infer_line_category({"gap_type": "missing_setup"}) == "context_setup"
    assert infer_line_category({"line_category": "episode_preface"}) == "episode_preface"


def test_build_gap_framing_plan_and_ranking_exclude(ctx: RunContext) -> None:
    lines = [
        normalize_interviewer_line(
            {
                "line_id": "vo_sum_1",
                "line_category": "segment_summary",
                "gap_type": "missing_setup",
                "placement": "before",
                "text": "Host summarizes the guest background.",
                "targets_segment_id": "seg_002",
                "replaces_source_segments": ["seg_001"],
            },
            eligible="spk_0",
            delivery="synthesize",
        )
    ]
    plan = build_gap_framing_plan(ctx, lines)
    assert plan["succinct_master_intent"] is True
    ctx.write_json("understanding/gap_framing_plan.json", plan)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": lines},
    )
    excluded = ranking_exclude_segment_ids(ctx)
    assert "seg_001" in excluded


def test_gap_vo_delivery_persisted(ctx: RunContext) -> None:
    set_gap_framing_enabled(ctx, True)
    set_gap_vo_delivery(ctx, "chatterbox")
    meta = ctx.read_json("run_meta.json")
    assert meta.get("gap_vo_delivery") == "chatterbox"


def test_dedupe_transitions_for_framing() -> None:
    from interview_mux.gap_framing import dedupe_transitions_for_framing

    gap_report = {
        "interviewer_lines": [
            {
                "line_id": "vo_br",
                "line_category": "story_bridge",
                "targets_segment_id": "seg_b",
                "placement": "before",
            }
        ]
    }
    transitions = {
        "transitions": [
            {"after_segment_id": "seg_a", "before_segment_id": "seg_b", "text": "bridge"},
        ]
    }
    out = dedupe_transitions_for_framing(gap_report, transitions)
    assert out.get("transitions") == []
    assert out.get("framing_deduped_count") == 1

