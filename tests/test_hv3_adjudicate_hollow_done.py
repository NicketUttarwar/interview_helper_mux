"""HV-3: vo_line_adjudicate done requires a written adjudication primary.

0.1.0 skip/settled paths write a stub. G1 allow-stub still honors HV-4.
Do not start a run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    stage_artifact_incompleteness,
)
from interview_mux.stages.vo_line_adjudicate import run_vo_line_adjudicate
from interview_mux.vo_line_adjudicate import (
    ADJUDICATION_REL,
    run_vo_line_adjudicate_stage,
)
from run_fixtures import isolated_run_ctx, mark_done_raw

_LINE = "vo_live_1"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "hv3_adjudicate")


def _plant_010(ctx: RunContext, **extra: object) -> None:
    meta = {"homunculus_version": "0.1.0"}
    meta.update(extra)
    ctx.write_json("run_meta.json", meta, skip_handoff=True)


def test_hv3_no_gap_writes_stub_and_marks(ctx: RunContext) -> None:
    _plant_010(ctx)
    run_vo_line_adjudicate_stage(ctx)
    assert ctx.artifact_exists(ADJUDICATION_REL)
    doc = ctx.read_json(ADJUDICATION_REL)
    assert doc.get("lines") == []
    assert doc.get("skip_reason") == "no_gap_report"
    assert ctx.is_done("vo_line_adjudicate")
    assert seed_stage_complete(ctx, "vo_line_adjudicate") is True


def test_hv3_invalid_gap_writes_stub_and_marks(ctx: RunContext) -> None:
    _plant_010(ctx)
    path = ctx.path("understanding", "gap_report.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]", encoding="utf-8")
    run_vo_line_adjudicate_stage(ctx)
    doc = ctx.read_json(ADJUDICATION_REL)
    assert doc.get("skip_reason") == "invalid_gap_report"
    assert ctx.is_done("vo_line_adjudicate")
    assert seed_stage_complete(ctx, "vo_line_adjudicate") is True


def test_hv3_zero_body_lines_writes_stub(ctx: RunContext) -> None:
    _plant_010(ctx)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [{"line_id": "vo_skip", "delivery": "record"}]},
        skip_handoff=True,
    )
    run_vo_line_adjudicate_stage(ctx)
    doc = ctx.read_json(ADJUDICATION_REL)
    assert doc.get("lines") == []
    assert doc.get("skip_reason") == "zero_body_synthesize_lines"
    assert ctx.is_done("vo_line_adjudicate")
    assert seed_stage_complete(ctx, "vo_line_adjudicate") is True


def test_hv3_settled_lines_no_invented_action(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_010(ctx)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": _LINE,
                    "text": "Already settled copy.",
                    "delivery": "synthesize",
                    "targets_segment_id": "seg_001",
                }
            ]
        },
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.vo_line_adjudicate.lines_needing_adjudication",
        lambda *_a, **_k: [],
    )
    run_vo_line_adjudicate_stage(ctx)
    doc = ctx.read_json(ADJUDICATION_REL)
    assert doc.get("skip_reason") == "unchanged_or_flow_ok"
    assert doc.get("settled_line_ids") == [_LINE]
    assert doc.get("lines") == []
    assert all("action" not in row for row in (doc.get("lines") or []))
    assert ctx.is_done("vo_line_adjudicate")
    assert seed_stage_complete(ctx, "vo_line_adjudicate") is True


def test_hv3_config_off_writes_stub(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    _plant_010(ctx)
    monkeypatch.setattr(
        "interview_mux.vo_line_adjudicate.adjudicate_before_synth_enabled",
        lambda: False,
    )
    run_vo_line_adjudicate(ctx)
    doc = ctx.read_json(ADJUDICATION_REL)
    assert doc.get("skip_reason") == "adjudicate_before_synth_disabled"
    assert ctx.is_done("vo_line_adjudicate")
    assert seed_stage_complete(ctx, "vo_line_adjudicate") is True


def test_hv3_g1_skip_writes_stub_when_seats_present(ctx: RunContext) -> None:
    _plant_010(ctx, g1_vo_skipped_optional=True, hosted_framing_floor_waived=True)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": _LINE,
                    "text": "Seated line.",
                    "delivery": "synthesize",
                    "severity": "medium",
                    "placement": "before",
                    "targets_segment_id": "seg_001",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "version": 1,
            "plan_status": "complete",
            "air_script": {
                "beats": [{"id": "b1"}],
                "vo_seats": {"seated_line_ids": [_LINE], "omitted_line_ids": []},
            },
        },
        skip_handoff=True,
    )
    out = heal_or_refuse_mark(ctx, "vo_line_adjudicate", force=True)
    assert out.get("marked") is True
    doc = ctx.read_json(ADJUDICATION_REL)
    assert doc.get("skip_reason") == "g1_skipped_optional"
    assert ctx.is_done("vo_line_adjudicate")


def test_hv3_g1_skip_refuses_when_hv4_hollow_seats(ctx: RunContext) -> None:
    _plant_010(ctx, g1_vo_skipped_optional=True, hosted_framing_floor_waived=True)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": _LINE,
                    "text": "Unverified leftover copy.",
                    "delivery": "synthesize",
                    "severity": "low",
                    "placement": "before",
                    "targets_segment_id": "seg_001",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "version": 1,
            "plan_status": "complete",
            "air_script": {
                "beats": [{"id": "b1"}],
                "vo_seats": {"seated_line_ids": [], "omitted_line_ids": []},
            },
        },
        skip_handoff=True,
    )
    out = heal_or_refuse_mark(ctx, "vo_line_adjudicate", force=True)
    assert out.get("allow_stub") is not True
    assert out.get("marked") is not True
    assert not ctx.artifact_exists(ADJUDICATION_REL)
    assert not ctx.is_done("vo_line_adjudicate")


def test_hv3_raw_done_without_primary_is_incomplete(ctx: RunContext) -> None:
    _plant_010(ctx)
    mark_done_raw(ctx, "vo_line_adjudicate")
    reason = stage_artifact_incompleteness(ctx, "vo_line_adjudicate")
    assert reason is not None
    assert "vo_line_adjudication.json" in reason
    assert seed_stage_complete(ctx, "vo_line_adjudicate") is False
    out = heal_or_refuse_mark(ctx, "vo_line_adjudicate")
    assert out.get("unmarked") is True or not ctx.is_done("vo_line_adjudicate")
