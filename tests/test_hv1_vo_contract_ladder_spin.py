"""HV-1: failed VO-contract ladder must not spin A→D on the same hole."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.execution_contract import (
    VO_CONTRACT_REPAIR_PLAN_REL,
    run_vo_contract_ladder,
)
from interview_mux.run_context import RunContext
from run_fixtures import patch_executions_root

_LINE = "vo_layup_seg_009"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("hv1_vo_contract_spin", create=True)


def _plant_durable_skip_on_seated(ctx: RunContext) -> None:
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": [_LINE],
                    "omitted_line_ids": [],
                    "orientation_id": None,
                }
            }
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": _LINE,
                    "delivery": "synthesize",
                    "skipped_optional": True,
                    "air_script_omit": True,
                    "text": "Leftover seated skip/omit.",
                    "placement": "before",
                    "targets_segment_id": "seg_009",
                }
            ]
        },
        skip_handoff=True,
    )


def _freeze_tiers(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    def _noop(name: str):
        def _inner(_ctx, *_a, **_k):
            calls.append(name)
            return []

        return _inner

    monkeypatch.setattr(
        "interview_mux.execution_contract._tier_a_publish_orientation",
        _noop("a"),
    )
    monkeypatch.setattr(
        "interview_mux.execution_contract._tier_b_gap_recompose",
        _noop("b"),
    )
    monkeypatch.setattr(
        "interview_mux.execution_contract._tier_c_opening_omit_unseat",
        _noop("c"),
    )
    monkeypatch.setattr(
        "interview_mux.execution_contract._tier_d_logged_waive",
        _noop("d"),
    )


def test_hv1_exhaust_pins_vo_synthesize_and_keeps_plan_open(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_durable_skip_on_seated(ctx)
    calls: list[str] = []
    _freeze_tiers(monkeypatch, calls)
    first = run_vo_contract_ladder(ctx, consumer_stage="nugget_layup_compose")
    assert first.recovered is False
    assert first.contract_ok is False
    assert first.resume_stage == "vo_synthesize"
    assert first.resume_stage != "nugget_layup_compose"
    plan = ctx.read_json(VO_CONTRACT_REPAIR_PLAN_REL)
    assert plan.get("active") is True
    assert plan.get("completed") is not True
    assert plan.get("last_outcome") == "tiers_exhausted"
    assert calls == ["a", "b", "c", "d"]


def test_hv1_same_fingerprint_does_not_reenter_tiers(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_durable_skip_on_seated(ctx)
    calls: list[str] = []
    _freeze_tiers(monkeypatch, calls)
    first = run_vo_contract_ladder(ctx, consumer_stage="nugget_layup_compose")
    gap = ctx.read_json("understanding/gap_report.json")
    gap["note"] = "file-size-only change"
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)
    second = run_vo_contract_ladder(ctx, consumer_stage="edl_narrative_audit")
    assert second.resume_stage == "vo_synthesize"
    assert second.recovered is False
    assert second.detail == first.detail or second.tier == first.tier
    assert calls == ["a", "b", "c", "d"]


def test_hv1_fingerprint_change_allows_another_walk(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_durable_skip_on_seated(ctx)
    calls: list[str] = []
    _freeze_tiers(monkeypatch, calls)
    run_vo_contract_ladder(ctx, consumer_stage="vo_synthesize")
    plan = ctx.read_json("mastering/mastering_plan.json")
    script = dict(plan.get("air_script") or {})
    seats = dict(script.get("vo_seats") or {})
    seats["seated_line_ids"] = [_LINE, "vo_other"]
    script["vo_seats"] = seats
    plan["air_script"] = script
    ctx.write_json("mastering/mastering_plan.json", plan, skip_handoff=True)
    run_vo_contract_ladder(ctx, consumer_stage="vo_synthesize")
    assert calls == ["a", "b", "c", "d", "a", "b", "c", "d"]
