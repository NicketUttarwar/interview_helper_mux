"""Tests for execution contract ladder and seated VO policy."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.air_script import seated_vo_line_ids
from interview_mux.execution_contract import (
    classify_vo_violation,
    reconcile_execution_contract,
    run_vo_contract_ladder,
)
from interview_mux.opening_orientation import ORIENTATION_LINE_ID
from interview_mux.run_context import RunContext
from interview_mux.vo_contract import validate_vo_contract
from run_fixtures import patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("exec_contract_ladder", create=True)


def test_seated_vo_line_ids_no_implicit_orientation_when_null(ctx: RunContext) -> None:
    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": [],
                "omitted_line_ids": [],
                "orientation_id": None,
            }
        }
    }
    assert ORIENTATION_LINE_ID not in seated_vo_line_ids(plan)


def test_classify_vo_violation_missing_from_gap() -> None:
    v = classify_vo_violation("seated line vo_preface_episode_orientation missing from gap_report")
    assert v.kind == "missing_from_gap"
    assert v.line_id == "vo_preface_episode_orientation"


def test_exec_5175_hole_tier_d_waive(ctx: RunContext) -> None:
    """Gap without orientation; empty vo_seats — ladder tier D clears implicit contract hole."""
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": [],
                    "omitted_line_ids": [],
                    "orientation_id": None,
                }
            }
        },
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_001",
                    "delivery": "synthesize",
                    "required": True,
                    "targets_segment_id": "seg_001",
                    "gap_type": "layup",
                    "text": "Setup line.",
                    "placement": "before",
                }
            ]
        },
    )
    # Simulate stale implicit seat by writing contract snapshot with violation message
    violations_before = validate_vo_contract(ctx)
    if not violations_before:
        ctx.write_json(
            "mastering/mastering_plan.json",
            {
                "air_script": {
                    "vo_seats": {
                        "seated_line_ids": [ORIENTATION_LINE_ID],
                        "omitted_line_ids": [],
                        "orientation_id": ORIENTATION_LINE_ID,
                    }
                }
            },
        )
        violations_before = validate_vo_contract(ctx)
    assert violations_before

    result = run_vo_contract_ladder(ctx, consumer_stage="nugget_layup_compose")
    assert result.contract_ok or not validate_vo_contract(ctx)
    snapshot = reconcile_execution_contract(ctx, reason="test")
    assert isinstance(snapshot, dict)


def test_policy_cascade_suppresses_identical_failure(ctx: RunContext) -> None:
    from interview_mux.execution_contract import failure_in_active_policy_cascade
    from interview_mux.identical_failures import record_class_failure

    ctx.write_json(
        "operator/vo_contract_repair_plan.json",
        {
            "version": 1,
            "active": True,
            "error_class": "vo_contract_repair",
            "invalidate_set": ["vo_line_adjudicate"],
            "cascade_error_classes": ["vo_contract_repair"],
        },
    )
    assert failure_in_active_policy_cascade(
        ctx, failed_stage="vo_line_adjudicate", producer="vo_contract_repair"
    )
    row = record_class_failure(
        ctx,
        failed_stage="nugget_layup_compose",
        error_class="vo_contract_repair",
    )
    assert not row.get("halt")
