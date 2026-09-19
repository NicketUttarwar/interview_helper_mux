"""Category B WS2: one high-gap VO seat authority."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.high_gap_vo import resolve_seats, targeted_segment_ids
from interview_mux.run_context import RunContext
from run_fixtures import init_run_meta_for_test, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_category_b_ws2", create=True)
    init_run_meta_for_test(run)
    run.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": "seg_003",
                    "severity": "high",
                    "self_explanatory": False,
                    "gap_type": "missing_setup",
                    "listener_confusion": "needs framing",
                }
            ]
        },
        skip_handoff=True,
    )
    return run


def test_targeted_segments_are_on_air_only(ctx: RunContext) -> None:
    lines = [
        {"targets_segment_id": "seg_001", "text": ""},
        {
            "targets_segment_id": "seg_002",
            "text": "omitted",
            "air_script_omit": True,
        },
        {
            "targets_segment_id": "seg_003",
            "text": "skipped",
            "skipped_optional": True,
        },
        {"targets_segment_id": "seg_004", "text": "Audible bridge."},
    ]
    assert targeted_segment_ids(lines, ctx) == {"seg_004"}


def test_compose_resolution_demotes_omitted_reference(ctx: RunContext) -> None:
    result = resolve_seats(
        ctx,
        intent="compose_persist",
        gap_report={
            "interviewer_lines": [
                {
                    "targets_segment_id": "seg_003",
                    "text": "Not aired.",
                    "air_script_omit": True,
                }
            ]
        },
    )
    assert result.demoted == 1
    assert result.seats[0].action == "demoted"
    row = ctx.read_json("understanding/gap_evaluations.json")["evaluations"][0]
    assert row["severity_demotion_reason"] == "high_gap_seat:compose_persist"


def test_heal_protects_only_while_fill_is_budgeted(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines", lambda _ctx: 3
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.budget.identity_exhausted", lambda *_a: False
    )
    protected = resolve_seats(
        ctx, intent="heal_floor_protect", gap_report={"interviewer_lines": []}
    )
    assert protected.demoted == 0
    assert protected.floor_protected == 1

    stamps: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "interview_mux.homunculus.budget.identity_exhausted", lambda *_a: True
    )
    monkeypatch.setattr(
        "interview_mux.vo_contract.ensure_hosted_framing_vo_seats", lambda _ctx: []
    )
    monkeypatch.setattr(
        "interview_mux.vo_contract._record_hosted_floor_unmet",
        lambda _ctx, *, need, active, cta_only=False: stamps.append((need, active)),
    )
    demoted = resolve_seats(
        ctx, intent="heal_floor_protect", gap_report={"interviewer_lines": []}
    )
    assert demoted.demoted == 1
    assert demoted.floor_unmet is True
    assert stamps == [(3, 0)]


def test_invalid_intent_is_rejected(ctx: RunContext) -> None:
    with pytest.raises(ValueError, match="unknown high-gap seat intent"):
        resolve_seats(ctx, intent="legacy_origin")  # type: ignore[arg-type]
