"""Seat repairs land on the mastering plan under the seat owner's key and an End-A reason (ISSUES 101)."""

from __future__ import annotations

import json

from run_fixtures import isolated_run_ctx

from interview_mux import vo_contract
from interview_mux.seat_authority import END_A_CORE_ACTIONS


def _seed(ctx, seated: list[str], gap_lines: list[dict]) -> None:
    plan = ctx.final_path("mastering", "mastering_plan.json")
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(
        json.dumps({"air_script": {"vo_seats": {"seated_line_ids": seated, "omitted_line_ids": []}}}),
        encoding="utf-8",
    )
    gap = ctx.final_path("understanding", "gap_report.json")
    gap.parent.mkdir(parents=True, exist_ok=True)
    gap.write_text(json.dumps({"version": 1, "interviewer_lines": gap_lines}), encoding="utf-8")


def test_unseating_an_ineligible_line_uses_the_owner_key(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_seat_repair_ineligible")
    _seed(
        ctx,
        seated=["vo_a"],
        gap_lines=[{"line_id": "vo_a", "text": "So,", "skipped_optional": True, "air_script_omit": True}],
    )
    monkeypatch.setattr(vo_contract, "gap_line_air_eligible", lambda row, **_k: False, raising=False)
    monkeypatch.setattr("interview_mux.air_script.gap_line_air_eligible", lambda row, **_k: False)
    calls: list[dict] = []
    monkeypatch.setattr(
        "interview_mux.seat_authority.persist_frozen_seat_doc",
        lambda c, rel, doc, **kw: calls.append({"rel": rel, "doc": doc, **kw}) or True,
    )

    dropped = vo_contract._unseat_ineligible_plan_seats(ctx)

    assert dropped == ["vo_a"]
    assert calls and calls[0]["rel"] == "mastering/mastering_plan.json"
    assert calls[0]["stage_key"] == "air_contract_sanitize"
    assert calls[0]["reason"] == "air_script_gap_omit_sync"
    assert calls[0]["reason"] in END_A_CORE_ACTIONS
    assert calls[0]["doc"]["air_script"]["vo_seats"]["seated_line_ids"] == []
    assert calls[0]["doc"]["air_script"]["vo_seats"]["omitted_line_ids"] == ["vo_a"]


def test_the_orphan_unseat_reason_is_end_a_too() -> None:
    assert "drop_seated_missing_from_gap" in END_A_CORE_ACTIONS
    assert "hosted_vo_disposition_apply" in END_A_CORE_ACTIONS
    assert "catastrophe_seated_bind_synth_failed" in END_A_CORE_ACTIONS
