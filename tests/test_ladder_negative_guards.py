"""Negative guard tests — ladders must NOT waive required lines or archive layup."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.execution_contract import run_edl_vo_coverage_ladder, run_vo_contract_ladder
from interview_mux.remediation_framework import remediation_plan_mutex_allows
from interview_mux.run_context import RunContext
from run_fixtures import patch_executions_root, mark_done_raw

BASELINE = Path(__file__).parent / "fixtures" / "exec_4741_ship_baseline" / "manifest.json"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("negative_guards", create=True)


def _healthy_vo(ctx: RunContext) -> None:
    from interview_mux.vo_synthesis_audit import record_synthesis
    from run_fixtures import write_fixture_vo_wav

    doc = json.loads(BASELINE.read_text(encoding="utf-8"))
    ctx.write_json("understanding/gap_report.json", doc["gap_report"])
    ctx.write_json("mastering/mastering_plan.json", doc["mastering_plan"])
    line = next(
        row
        for row in (doc["gap_report"].get("interviewer_lines") or [])
        if isinstance(row, dict) and row.get("line_id") == "vo_layup_seg_001"
    )
    wav = ctx.final_path("vo_pickup") / "synthesized" / "vo_layup_seg_001.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    write_fixture_vo_wav(wav)
    record_synthesis(ctx, line, backend="mlx_audio", out_wav=wav)


def test_ladder_no_op_when_healthy(ctx: RunContext) -> None:
    """MUST_NOT mutate stage_done when coverage already valid."""
    _healthy_vo(ctx)
    mark_done_raw(ctx, "nugget_layup_compose")
    mark_done_raw(ctx, "edl_narrative_audit")
    result = run_edl_vo_coverage_ladder(ctx)
    assert result.recovered
    assert ctx.is_done("nugget_layup_compose")


def test_vo_contract_no_op_when_valid(ctx: RunContext) -> None:
    _healthy_vo(ctx)
    mark_done_raw(ctx, "nugget_layup_compose")
    result = run_vo_contract_ladder(ctx, consumer_stage="nugget_layup_compose")
    assert result.recovered
    assert result.contract_ok


def test_dual_ladder_mutex(ctx: RunContext) -> None:
    from interview_mux.remediation_framework import RemediationPlan, write_remediation_plan

    write_remediation_plan(
        ctx,
        RemediationPlan(
            error_class="vo_contract_repair",
            consumer_stage="nugget_layup_compose",
            allowed_rerun_stages=["vo_line_adjudicate"],
        ),
    )
    assert not remediation_plan_mutex_allows(ctx, "vo_seated_coverage")


def test_vo_coverage_ladder_preserves_layup_marker(ctx: RunContext) -> None:
    """MUST_NOT clear nugget_layup_compose on vo_coverage heal."""
    doc = json.loads(
        (Path(__file__).parent / "fixtures" / "exec_5174_vo_coverage_hole" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    ctx.write_json("understanding/gap_report.json", doc["gap_report"])
    ctx.write_json("mastering/mastering_plan.json", doc["mastering_plan"])
    mark_done_raw(ctx, "nugget_layup_compose")
    mark_done_raw(ctx, "vo_synthesize")
    run_edl_vo_coverage_ladder(ctx)
    assert ctx.is_done("nugget_layup_compose")
