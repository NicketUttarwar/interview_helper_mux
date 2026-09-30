"""A frozen seat doc that does not exist yet may be produced under the soft freeze (ISSUES 96)."""

from __future__ import annotations

import json

from run_fixtures import isolated_run_ctx

from interview_mux.seat_authority import frozen_seat_write_allowed, stamp_soft_seat_freeze


def test_first_production_of_transitions_lands_under_soft_freeze(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_freeze_first_write")
    stamp_soft_seat_freeze(ctx, reason="air_contract_sanitize")
    assert not ctx.artifact_exists("master/transitions.json")
    assert frozen_seat_write_allowed(ctx, "master/transitions.json", reason="transitions") is True


def test_a_rewrite_of_an_existing_seat_doc_is_still_refused(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_freeze_rewrite")
    stamp_soft_seat_freeze(ctx, reason="air_contract_sanitize")
    path = ctx.final_path("master", "transitions.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "transitions": []}), encoding="utf-8")
    assert frozen_seat_write_allowed(ctx, "master/transitions.json", reason="transitions") is False


def test_end_a_actions_are_unchanged(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_freeze_end_a")
    stamp_soft_seat_freeze(ctx, reason="air_contract_sanitize")
    path = ctx.final_path("understanding", "gap_report.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"interviewer_lines": []}), encoding="utf-8")
    assert frozen_seat_write_allowed(
        ctx, "understanding/gap_report.json", reason="stamp_gap_omit_flags"
    ) is True
