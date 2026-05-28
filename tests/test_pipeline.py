from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from interview_mux import pipeline
from interview_mux.run_context import RunContext


def _ctx_from_fixture(tmp_path: Path) -> RunContext:
    fixture = Path(__file__).parent / "fixtures" / "runs" / "base_smoke"
    run_dir = tmp_path / "run_fixture"
    shutil.copytree(fixture, run_dir)
    ctx = RunContext("exec_999_20260101T000000Z", create=False)
    ctx.run_dir = run_dir
    return ctx


def test_run_single_stage_transcript_review_build_pauses_when_queue_exists(tmp_path, monkeypatch):
    ctx = _ctx_from_fixture(tmp_path)
    monkeypatch.setattr(
        pipeline,
        "_analysis_stage_fns",
        lambda _ctx: {"transcript_review_build": lambda: None},
    )
    with pytest.raises(SystemExit, match="Transcript review required"):
        pipeline.run_single_stage(ctx, "transcript_review_build")


def test_run_flow1_smoke_uses_fixture_run_dir_without_external_calls(tmp_path, monkeypatch):
    ctx = _ctx_from_fixture(tmp_path)
    called: list[str] = []

    monkeypatch.setattr(
        pipeline.analysis_flow1_extended,
        "run_topic_coverage",
        lambda _ctx: called.append("topic_coverage_audit"),
    )
    monkeypatch.setattr(
        pipeline.analysis_flow1_extended,
        "run_narrative_arc",
        lambda _ctx: called.append("narrative_arc_plan"),
    )
    monkeypatch.setattr(
        pipeline.selection_flow1,
        "run_full_master_ranking",
        lambda _ctx: called.append("full_master_ranking"),
    )
    monkeypatch.setattr(
        pipeline.selection_flow1,
        "run_transitions",
        lambda _ctx: called.append("transitions"),
    )
    monkeypatch.setattr(
        pipeline.sound_design_stages,
        "run_sound_design_plan_flow1",
        lambda _ctx: called.append("sound_design_plan_flow1"),
    )
    monkeypatch.setattr(
        pipeline.assembly_flow1,
        "run_edl",
        lambda _ctx: called.append("edl_flow1"),
    )
    monkeypatch.setattr(
        pipeline.assembly_flow1,
        "run_preview",
        lambda _ctx: called.append("assembly_preview"),
    )
    monkeypatch.setattr(
        pipeline.sound_design_stages,
        "run_elevenlabs_prompt_craft",
        lambda _ctx: called.append("elevenlabs_prompt_craft"),
    )
    monkeypatch.setattr(
        pipeline.sfx_elevenlabs,
        "run_sfx_generation",
        lambda _ctx, profile: called.append(f"elevenlabs_sfx_{profile}"),
    )
    monkeypatch.setattr(
        pipeline.assembly_flow1,
        "run_mux",
        lambda _ctx: called.append("mux_flow1"),
    )
    monkeypatch.setattr(
        pipeline.mastering,
        "run_master_flow1",
        lambda _ctx: called.append("master_flow1"),
    )

    pipeline.run_flow1(ctx)

    assert called == [
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "transitions",
        "sound_design_plan_flow1",
        "edl_flow1",
        "assembly_preview",
        "elevenlabs_prompt_craft",
        "elevenlabs_sfx_podcast",
        "mux_flow1",
        "master_flow1",
    ]
