"""A stale ordering complaint is demoted once the committed plan holds on air (ISSUES 48)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_repairs import (
    _edl_issue_contradicted_by_disk,
    _ordering_constraints_satisfied,
)
from interview_mux.run_context import RunContext
from run_fixtures import minimal_narrative_plan


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, order, constraints) -> RunContext:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_order_audit", create=True)
    ctx.write_json("master/selection.json", {"ordered_segment_ids": list(order)})
    ctx.write_json(
        "master/narrative_plan.json",
        minimal_narrative_plan(
            ordering_constraints=[
                {"before_segment_id": b, "after_segment_id": a, "reason": "r"}
                for b, a in constraints
            ]
        ),
    )
    return ctx


ROW = {
    "code": "ordering_constraint_broken",
    "issue": "The selected air order breaks two active narrative-plan constraints; "
    "the constraint graph is cyclic across selected material.",
    "evidence": ["narrative_plan.ordering_constraints: seg_007 before seg_004"],
}


def test_satisfied_constraints_demote_the_complaint(tmp_path, monkeypatch) -> None:
    # exec_049: the aligned plan held on air, the audit still said cyclic.
    ctx = _ctx(
        tmp_path,
        monkeypatch,
        ["seg_001", "seg_006", "seg_004", "seg_005", "seg_007"],
        [("seg_001", "seg_007"), ("seg_004", "seg_005"), ("seg_006", "seg_007")],
    )
    assert _ordering_constraints_satisfied(ctx) is True
    assert _edl_issue_contradicted_by_disk(ctx, ROW) is True


def test_violated_constraint_keeps_the_complaint(tmp_path, monkeypatch) -> None:
    ctx = _ctx(
        tmp_path,
        monkeypatch,
        ["seg_001", "seg_006", "seg_004", "seg_005", "seg_007"],
        [("seg_007", "seg_004")],
    )
    assert _ordering_constraints_satisfied(ctx) is False
    assert _edl_issue_contradicted_by_disk(ctx, ROW) is False


def test_missing_plan_never_demotes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_order_audit_missing", create=True)
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_001"]})
    assert _ordering_constraints_satisfied(ctx) is False
    assert _edl_issue_contradicted_by_disk(ctx, ROW) is False


def test_off_air_segment_is_vacuous(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, ["seg_001", "seg_002"], [("seg_009", "seg_001")])
    assert _ordering_constraints_satisfied(ctx) is True
