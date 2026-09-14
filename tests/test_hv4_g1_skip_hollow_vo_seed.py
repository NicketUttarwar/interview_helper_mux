"""HV-4: G1 optional skip waives record, not a hollow VO seed.

Do not start a run. C-04 hosted floor waive stays as-is.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.gap_fill_eligibility import hosted_framing_requires_synthetic_vo
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
    return isolated_run_ctx(tmp_path, "hv4_g1_hollow")


def _plant_vo_seed(
    ctx: RunContext,
    *,
    seated: list[str],
    skip_g1: bool = True,
    severity: str = "low",
) -> None:
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": _LINE,
                    "text": "Unverified leftover copy.",
                    "delivery": "synthesize",
                    "severity": severity,
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
                "beats": [{"beat_id": "b1"}],
                "vo_seats": {"seated_line_ids": list(seated), "omitted_line_ids": []},
            },
        },
        skip_handoff=True,
    )
    ctx.write_json("mastering/vo_synthesize.json", {"version": 1, "lines": []}, skip_handoff=True)
    ctx.write_json("master/transitions.json", {"version": 1, "transitions": []}, skip_handoff=True)
    if skip_g1:
        ctx.write_json(
            "run_meta.json",
            {
                "g1_vo_skipped_optional": True,
                "hosted_framing_floor_waived": True,
            },
            skip_handoff=True,
        )


def test_hv4_hollow_seats_incompleteness_on_vo_synthesize(ctx: RunContext) -> None:
    _plant_vo_seed(ctx, seated=[])
    reason = stage_artifact_incompleteness(ctx, "vo_synthesize")
    assert reason is not None
    assert "hollow seats" in reason
    assert seed_stage_complete(ctx, "vo_synthesize") is False
    air = stage_artifact_incompleteness(ctx, "air_script_seams")
    assert air is not None
    assert "hollow seats" in air
    adjudicate = stage_artifact_incompleteness(ctx, "vo_line_adjudicate")
    assert adjudicate is None or "hollow seats" not in adjudicate


def test_hv4_g1_skip_refuses_allow_stub_when_seats_empty(ctx: RunContext) -> None:
    _plant_vo_seed(ctx, seated=[])
    out = heal_or_refuse_mark(ctx, "vo_synthesize", force=True)
    assert out.get("marked") is not True
    assert out.get("allow_stub") is not True
    assert out.get("refused") is True
    assert not ctx.is_done("vo_synthesize")
    adj = heal_or_refuse_mark(ctx, "vo_line_adjudicate", force=True)
    if adj.get("reason") and "hollow seats" in str(stage_artifact_incompleteness(ctx, "vo_synthesize")):
        assert adj.get("allow_stub") is not True


def test_hv4_g1_skip_allow_stub_when_seats_present(ctx: RunContext) -> None:
    _plant_vo_seed(ctx, seated=[_LINE], severity="medium")
    reason = stage_artifact_incompleteness(ctx, "vo_synthesize")
    assert reason is not None
    assert "hollow seats" not in reason
    out = heal_or_refuse_mark(ctx, "vo_synthesize", force=True)
    assert out.get("allow_stub") is True
    assert out.get("marked") is True
    assert ctx.is_done("vo_synthesize")


def test_hv4_c04_hosted_floor_still_waived(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/source_topology.json",
        {"topology_class": "hosted_1to1"},
        skip_handoff=True,
    )
    _plant_vo_seed(ctx, seated=[])
    assert hosted_framing_requires_synthetic_vo(ctx) is False


def test_hv4_seed_complete_false_after_raw_done(ctx: RunContext) -> None:
    _plant_vo_seed(ctx, seated=[])
    mark_done_raw(ctx, "vo_synthesize")
    assert seed_stage_complete(ctx, "vo_synthesize") is False
