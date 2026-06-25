"""Tests for numbered stage steps in GUI guidance."""

from __future__ import annotations

from interview_mux.stage_guidance import STAGE_UNLOCKS, build_stage_guidance
from interview_mux.stage_steps import attach_steps_to_guidance, build_stage_steps
from interview_mux.web.stages import STAGE_BY_ID
from run_fixtures import init_run_meta_for_test, isolated_run_ctx


def test_every_stage_has_steps(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "steps_all")
    init_run_meta_for_test(ctx)
    for stage_id in STAGE_BY_ID:
        guidance = build_stage_guidance(ctx, stage_id, status="pending")
        attach_steps_to_guidance(ctx, stage_id, guidance, status="pending")
        steps = guidance.get("steps") or []
        assert steps, f"{stage_id} has no steps"
        numbers = [s["number"] for s in steps]
        assert numbers == list(range(1, len(numbers) + 1)), stage_id
        ids = [s["id"] for s in steps]
        assert len(ids) == len(set(ids)), f"{stage_id} duplicate step ids"


def test_stage_unlocks_covers_steps() -> None:
    missing = set(STAGE_BY_ID) - set(STAGE_UNLOCKS)
    assert not missing


def test_ingest_steps_include_run_and_write(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "steps_ingest")
    init_run_meta_for_test(ctx)
    guidance = build_stage_guidance(ctx, "ingest", status="pending")
    steps = build_stage_steps(ctx, "ingest", status="pending", guidance=guidance)
    kinds = {s["kind"] for s in steps}
    assert "info" in kinds
    assert "run" in kinds


def test_g0_gate_steps(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "steps_g0")
    init_run_meta_for_test(ctx)
    guidance = build_stage_guidance(ctx, "transcript_review", status="action_required")
    steps = build_stage_steps(ctx, "transcript_review", status="action_required", guidance=guidance)
    assert len(steps) >= 4
    assert steps[-1]["primary_button"] == "Complete transcript review"


def test_locked_stage_single_step(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "steps_locked")
    init_run_meta_for_test(ctx)
    guidance = build_stage_guidance(ctx, "speaker_roles", status="locked")
    steps = build_stage_steps(ctx, "speaker_roles", status="locked", guidance=guidance)
    assert len(steps) == 1
    assert steps[0]["kind"] == "locked"


def test_done_stage_summary(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "steps_done")
    init_run_meta_for_test(ctx)
    ctx.mark_done("ingest")
    guidance = build_stage_guidance(ctx, "ingest", status="done")
    steps = build_stage_steps(ctx, "ingest", status="done", guidance=guidance)
    assert steps[0]["kind"] == "done"
