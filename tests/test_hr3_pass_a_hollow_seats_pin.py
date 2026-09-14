"""HR-3: air_script_compose (Pass A) is markable without VO seats.

Seats are Pass B (F-04 / seams). Do not start a run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.air_script import empty_air_script, run_air_script_compose, write_plan
from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.mastering_plan_loader import forced_sparse_plan, load_plan_raw
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    stage_artifact_incompleteness,
)
from run_fixtures import isolated_run_ctx, mark_done_raw

_LINE = "vo_live_1"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr("interview_mux.air_script.air_script_enabled", lambda: True)
    return isolated_run_ctx(tmp_path, "hr3_pass_a")


def _plant_live_vo(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": _LINE,
                    "text": "What happened next?",
                    "delivery": "synthesize",
                }
            ]
        },
        skip_handoff=True,
    )


def _plant_plan(ctx: RunContext, *, air_script: dict | None) -> None:
    doc = forced_sparse_plan(reason="hr3")
    if air_script is not None:
        doc["air_script"] = air_script
    ctx.write_json("mastering/mastering_plan.json", doc, skip_handoff=True)


def _pass_a_script(*, beats: bool = True) -> dict:
    script = empty_air_script(pass_name="pass_a")
    if beats:
        script["beats"] = [
            {
                "id": "beat_001",
                "segment_id": "seg_001",
                "montage_move": "native_handoff",
            }
        ]
    return script


def test_hr3_pass_a_complete_with_empty_seats_and_live_vo(ctx: RunContext) -> None:
    _plant_live_vo(ctx)
    _plant_plan(ctx, air_script=_pass_a_script())
    reason = stage_artifact_incompleteness(ctx, "air_script_compose")
    assert reason is None
    seams = stage_artifact_incompleteness(ctx, "air_script_seams")
    assert seams is not None
    assert "hollow seats" in seams


def test_hr3_compose_refuses_without_pass_a_script(ctx: RunContext) -> None:
    _plant_live_vo(ctx)
    _plant_plan(ctx, air_script=None)
    reason = stage_artifact_incompleteness(ctx, "air_script_compose")
    assert reason is not None
    assert "air_script_incomplete" in reason
    assert "hollow seats" not in reason


def test_hr3_heal_marks_after_pass_a_write(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    _plant_live_vo(ctx)
    _plant_plan(ctx, air_script=None)
    monkeypatch.setattr(
        "interview_mux.air_script.air_script_cfg",
        lambda: {"enable": True, "fail_open": True},
    )

    def _write_pass_a(_ctx: RunContext) -> dict:
        plan = dict(load_plan_raw(_ctx) or {})
        plan["air_script"] = _pass_a_script()
        write_plan(_ctx, plan)
        return plan

    monkeypatch.setattr("interview_mux.air_script.compose_pass_a", _write_pass_a)
    run_air_script_compose(ctx)
    assert ctx.is_done("air_script_compose")
    assert seed_stage_complete(ctx, "air_script_compose") is True
    seats = ((load_plan_raw(ctx) or {}).get("air_script") or {}).get("vo_seats") or {}
    assert not (seats.get("seated_line_ids") or [])
    assert seed_stage_complete(ctx, "air_script_seams") is False


def test_hr3_fail_open_refuses_done_without_pass_a(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_live_vo(ctx)
    _plant_plan(ctx, air_script=None)
    monkeypatch.setattr(
        "interview_mux.air_script.air_script_cfg",
        lambda: {"enable": True, "fail_open": True},
    )
    monkeypatch.setattr(
        "interview_mux.air_script.compose_pass_a",
        lambda _c: (_ for _ in ()).throw(RuntimeError("compose_boom")),
    )
    run_air_script_compose(ctx)
    assert not ctx.is_done("air_script_compose")
    reason = stage_artifact_incompleteness(ctx, "air_script_compose")
    assert reason is not None
    assert "air_script_incomplete" in reason


def test_hr3_raw_done_seed_leaves_when_pass_a_present(ctx: RunContext) -> None:
    _plant_live_vo(ctx)
    _plant_plan(ctx, air_script=_pass_a_script())
    mark_done_raw(ctx, "air_script_compose")
    assert seed_stage_complete(ctx, "air_script_compose") is True
    out = heal_or_refuse_mark(ctx, "air_script_compose")
    assert out.get("refused") is not True
    assert ctx.is_done("air_script_compose")
    assert seed_stage_complete(ctx, "air_script_seams") is False


def test_hr3_raw_done_unmarked_without_pass_a(ctx: RunContext) -> None:
    _plant_live_vo(ctx)
    _plant_plan(ctx, air_script=None)
    mark_done_raw(ctx, "air_script_compose")
    assert seed_stage_complete(ctx, "air_script_compose") is False
    out = heal_or_refuse_mark(ctx, "air_script_compose")
    assert out.get("unmarked") is True or not ctx.is_done("air_script_compose")
    assert seed_stage_complete(ctx, "air_script_compose") is False


def test_hr3_pass_b_script_still_completes_compose(ctx: RunContext) -> None:
    _plant_live_vo(ctx)
    script = empty_air_script(pass_name="pass_b")
    script["beats"] = [{"id": "beat_001", "segment_id": "seg_001"}]
    script["vo_seats"] = {"seated_line_ids": [_LINE], "omitted_line_ids": []}
    _plant_plan(ctx, air_script=script)
    assert stage_artifact_incompleteness(ctx, "air_script_compose") is None
