"""HV-2: missing seated WAV pins vo_synthesize — never the EDL consumer.

Reuses the exec_5174 seated-hole shape. Does not start a run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.execution_contract import run_edl_vo_coverage_ladder
from interview_mux.heal_routing import classify_heal_error
from interview_mux.remediation_framework import run_classified_ladder
from interview_mux.run_context import RunContext
from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing
from run_fixtures import mark_done_raw, patch_executions_root

_HOLE = Path(__file__).parent / "fixtures" / "exec_5174_vo_coverage_hole" / "manifest.json"
_CONSUMERS = frozenset({"edl", "edl_narrative_audit"})


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("hv2_vo_coverage_pin", create=True)


def _plant_5174_hole(ctx: RunContext, *, hosted: bool = False) -> None:
    doc = json.loads(_HOLE.read_text(encoding="utf-8"))
    ctx.write_json("understanding/gap_report.json", doc["gap_report"])
    ctx.write_json("mastering/mastering_plan.json", doc["mastering_plan"])
    mark_done_raw(ctx, "vo_synthesize")
    if hosted:
        ctx.write_json(
            "understanding/source_topology.json",
            {"speakers": [{"id": "host"}, {"id": "guest"}], "speaker_count": 2},
        )


def _assert_producer_pin(result, ctx: RunContext) -> None:
    assert result.recovered is False
    assert result.resume_stage == "vo_synthesize"
    assert result.resume_stage not in _CONSUMERS
    assert "needs_operator:" not in (result.detail or "")
    assert not ctx.is_done("vo_synthesize")
    assert compact_vo_coverage_stale_or_missing(ctx)
    plan = ctx.read_json("operator/vo_coverage_repair_plan.json")
    assert isinstance(plan, dict)
    assert plan.get("active") is True
    assert not plan.get("completed_at")


def test_hv2_exhaust_pins_vo_synthesize_not_edl(ctx: RunContext) -> None:
    _plant_5174_hole(ctx)
    result = run_edl_vo_coverage_ladder(ctx, consumer_stage="edl_narrative_audit")
    _assert_producer_pin(result, ctx)


def test_hv2_hosted_topology_does_not_pin_edl(ctx: RunContext) -> None:
    _plant_5174_hole(ctx, hosted=True)
    result = run_edl_vo_coverage_ladder(ctx, consumer_stage="edl")
    _assert_producer_pin(result, ctx)


def test_hv2_classified_ladder_honors_vo_synthesize_pin(ctx: RunContext) -> None:
    _plant_5174_hole(ctx)
    outcome = run_classified_ladder(
        ctx,
        consumer_stage="edl_narrative_audit",
        exc=RuntimeError("VO coverage not rendered: ['vo_layup_seg_019']"),
        error_class="vo_seated_coverage",
    )
    assert outcome.resume_stage == "vo_synthesize"
    assert outcome.resume_stage not in _CONSUMERS
    assert outcome.recovered is False


def test_hv2_seed_stage_complete_edl_false_while_missing(ctx: RunContext) -> None:
    _plant_5174_hole(ctx)
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_019"],
            "timeline_duration_ms": 1000,
            "clips": [],
        },
        skip_handoff=True,
    )
    mark_done_raw(ctx, "edl")
    run_edl_vo_coverage_ladder(ctx, consumer_stage="edl")
    assert seed_stage_complete(ctx, "edl") is False
    assert seed_stage_complete(ctx, "vo_synthesize") is False


def test_hv2_classify_heal_coverage_not_rendered_pins_vo_synthesize(
    ctx: RunContext,
) -> None:
    route = classify_heal_error(
        "VO coverage not rendered: ['vo_layup_seg_019']",
        ctx,
        stage="edl_narrative_audit",
    )
    assert route is not None
    assert route.from_stage == "vo_synthesize"
    seated = classify_heal_error(
        "seated synthesize vo_layup_seg_019 missing WAV",
        ctx,
        stage="edl",
    )
    assert seated is not None
    assert seated.from_stage == "vo_synthesize"
