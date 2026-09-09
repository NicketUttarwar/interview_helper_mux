"""EDL VO coverage ladder tests — Wave 0."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.execution_contract import run_edl_vo_coverage_ladder
from interview_mux.run_context import RunContext
from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing
from interview_mux.vo_synthesis_audit import record_synthesis
from run_fixtures import mark_done_raw, patch_executions_root, write_fixture_vo_wav

FIXTURE = Path(__file__).parent / "fixtures" / "exec_5174_vo_coverage_hole" / "manifest.json"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("edl_vo_ladder_test", create=True)


def _load_5174_hole(ctx: RunContext) -> None:
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ctx.write_json("understanding/gap_report.json", doc["gap_report"])
    ctx.write_json("mastering/mastering_plan.json", doc["mastering_plan"])
    mark_done_raw(ctx, "vo_synthesize")


def test_5174_hole_detects_missing_coverage(ctx: RunContext) -> None:
    _load_5174_hole(ctx)
    missing = compact_vo_coverage_stale_or_missing(ctx)
    assert "vo_layup_seg_019" in missing


def test_ladder_no_op_when_wav_present(ctx: RunContext) -> None:
    doc = json.loads(
        (Path(__file__).parent / "fixtures" / "exec_4741_ship_baseline" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    ctx.write_json("understanding/gap_report.json", doc["gap_report"])
    ctx.write_json("mastering/mastering_plan.json", doc["mastering_plan"])
    line = next(
        row
        for row in (doc["gap_report"].get("interviewer_lines") or [])
        if isinstance(row, dict) and row.get("line_id") == "vo_layup_seg_001"
    )
    syn = ctx.final_path("vo_pickup") / "synthesized" / "vo_layup_seg_001.wav"
    syn.parent.mkdir(parents=True, exist_ok=True)
    write_fixture_vo_wav(syn)
    record_synthesis(ctx, line, backend="mlx_audio", out_wav=syn)
    before = list((ctx.run_dir / ".stage_done").glob("*"))
    result = run_edl_vo_coverage_ladder(ctx, consumer_stage="edl_narrative_audit")
    after = list((ctx.run_dir / ".stage_done").glob("*"))
    assert result.recovered
    assert result.tier in {"none", "tier_a_backfill"}
    assert len(before) == len(after)


def test_ladder_tier_a_backfill_path(ctx: RunContext) -> None:
    _load_5174_hole(ctx)
    result = run_edl_vo_coverage_ladder(ctx, consumer_stage="edl_narrative_audit")
    assert result.tier in {"tier_a_backfill", "tier_b_vo_seated", "tier_c_adjudicate_heal", "tier_d_operator"}
