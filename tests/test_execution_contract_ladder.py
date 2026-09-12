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
    # Post-reconcile must not reseat a waived orientation (skip/omit + seated).
    assert not any("has skip/omit flags" in v for v in validate_vo_contract(ctx))


def test_tier_d_waive_orientation_survives_reconcile(ctx: RunContext) -> None:
    """exec_5177 class: seated + skip/omit orientation must stay unseated after tier D."""
    from interview_mux.air_script import seated_vo_line_ids
    from interview_mux.execution_contract import _tier_d_logged_waive, classify_vo_violation
    from interview_mux.mastering_plan_loader import load_plan_raw

    lid = "vo_preface_precision_oncology"
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "beats": [],
                "vo_seats": {
                    "seated_line_ids": [lid],
                    "omitted_line_ids": [],
                    "orientation_id": lid,
                },
            }
        },
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": lid,
                    "delivery": "synthesize",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "line_category": "episode_preface",
                    "episode_orientation": True,
                    "skipped_optional": True,
                    "air_script_omit": True,
                    "text": "Cancer treatment decisions often rely on incomplete signals.",
                }
            ]
        },
    )
    assert any("has skip/omit flags" in v for v in validate_vo_contract(ctx))
    violation = classify_vo_violation(
        f"seated synthesize {lid} has skip/omit flags"
    )
    assert violation.line_id == lid
    _tier_d_logged_waive(ctx, violation)
    reconcile_execution_contract(ctx, reason="post_tier_d")
    assert validate_vo_contract(ctx) == []
    plan = load_plan_raw(ctx) or {}
    seats = (plan.get("air_script") or {}).get("vo_seats") or {}
    assert lid not in (seats.get("seated_line_ids") or [])
    assert lid in (seats.get("omitted_line_ids") or [])
    assert seats.get("orientation_id") in {None, ""}
    assert lid not in seated_vo_line_ids(plan)
    gap = ctx.read_json("understanding/gap_report.json")
    meta = gap.get("opening_orientation") or {}
    assert meta.get("omitted") is True
    assert meta.get("required") is False


def test_tier_d_waive_missing_line_no_schema_invalid_stub(ctx: RunContext) -> None:
    """exec_11165: tier-D must not mint omit stubs missing gap_type/text/targets/placement."""
    from interview_mux.execution_contract import _tier_d_logged_waive, classify_vo_violation
    from interview_mux.prompt_validation import validate_artifact_write

    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "beats": [],
                "vo_seats": {
                    "seated_line_ids": [ORIENTATION_LINE_ID],
                    "omitted_line_ids": [],
                    "orientation_id": ORIENTATION_LINE_ID,
                },
            }
        },
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_question_seg_001",
                    "delivery": "synthesize",
                    "gap_type": "missing_question",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "text": "What changed in the trial design?",
                }
            ]
        },
    )
    violation = classify_vo_violation(
        f"seated synthesize {ORIENTATION_LINE_ID} missing from gap_report"
    )
    _tier_d_logged_waive(ctx, violation)
    gap = ctx.read_json("understanding/gap_report.json")
    lines = gap.get("interviewer_lines") or []
    assert not any(
        isinstance(ln, dict) and str(ln.get("line_id") or "") == ORIENTATION_LINE_ID
        for ln in lines
    )
    meta = gap.get("opening_orientation") or {}
    assert meta.get("omitted") is True
    assert meta.get("waived_line_id") == ORIENTATION_LINE_ID
    errs = validate_artifact_write("understanding/gap_report.json", gap)
    assert not errs, errs


def test_mark_gap_line_not_on_air_fills_schema_required() -> None:
    from interview_mux.vo_contract import mark_gap_line_not_on_air

    row = mark_gap_line_not_on_air(
        {"line_id": "vo_preface_episode_orientation", "delivery": "synthesize"},
        reason_code="execution_contract_waive",
        compensating_path="tier_d_logged_waive",
    )
    for key in ("gap_type", "text", "targets_segment_id", "placement", "delivery"):
        assert key in row
    assert row["placement"] in {"before", "after"}
    assert row["skipped_optional"] is True
    assert row["air_script_omit"] is True


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
