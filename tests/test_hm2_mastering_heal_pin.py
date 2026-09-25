"""HM-2: mastering heal pins rollup / sonic-palettes producer, never edl or reanchor-by-default.

Do not start a run. HM-1 schema-hollow and HM-4 sonic hollow-done stay open.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.heal_routing import classify_heal_error, resume_stage_for_error_class
from interview_mux.mastering_research import run_research_rollup
from interview_mux.recovery_controller import resolve_fingerprint_heal_resume
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    incompleteness_resume_stage,
    mastering_heal_resume_stage,
    producer_pin_for_token,
)
from interview_mux.thrash_hardening import heal_navigate
from interview_mux.unattended_resume import resume_producer_for_block
from run_fixtures import isolated_run_ctx, plant_seed_complete_through


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hm2_mastering")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_hm2_shape_core_thin_pins_rollup_not_edl_or_consumer(ctx: RunContext) -> None:
    plant_seed_complete_through(ctx, "mastering_research_rollup")
    run_research_rollup(ctx)
    ctx.write_json(
        "mastering/mastering_plan.json",
        {"plan_status": "degraded", "narrative_mode": "sparse_source"},
        skip_handoff=True,
    )
    assert (
        incompleteness_resume_stage(ctx, "mastering_plan_synthesize")
        == "mastering_research_rollup"
    )
    assert (
        incompleteness_resume_stage(ctx, "missing_framing")
        == "mastering_research_rollup"
    )
    nav = heal_navigate(
        ctx,
        error="research shape-core thin — not ready for Shape/gap consumers",
        stage="mastering_plan_synthesize",
    )
    assert nav["from_stage"] in {"mastering_research_rollup", "mastering_plan_synthesize"}
    assert nav["from_stage"] not in {"edl", "content_brief_reanchor"}
    route = classify_heal_error(
        "research shape-core thin — not ready for Shape/gap consumers",
        ctx,
        stage="mastering_plan_synthesize",
    )
    assert route is not None
    assert route.from_stage == "mastering_research_rollup"
    assert resume_stage_for_error_class("research_shape_core_thin") == "mastering_research_rollup"
    assert producer_pin_for_token("shape-core thin") == "mastering_research_rollup"


def test_hm2_rollup_self_pin_does_not_fall_through_to_edl(ctx: RunContext) -> None:
    run_research_rollup(ctx)
    ctx.write_json(
        "mastering/mastering_plan.json",
        {"plan_status": "degraded"},
        skip_handoff=True,
    )
    nav = heal_navigate(
        ctx,
        error="research dossier shape-core thin — resume mastering_research_rollup:",
        stage="mastering_research_rollup",
    )
    assert nav["from_stage"] == "mastering_research_rollup"


def test_hm2_sonic_fingerprint_self_pins_unless_brief_named() -> None:
    assert (
        resolve_fingerprint_heal_resume(
            message="fingerprint mismatch on upstream artifact",
            gate_stage="sonic_context_build",
        )
        == "sonic_context_build"
    )
    assert (
        resolve_fingerprint_heal_resume(
            message="fingerprint mismatch on upstream artifact",
            gate_stage="sound_design_palettes",
        )
        == "sound_design_palettes"
    )
    assert (
        resolve_fingerprint_heal_resume(
            message="understanding/content_brief.json fingerprint mismatch",
            gate_stage="sonic_context_build",
        )
        == "content_brief_reanchor"
    )
    assert (
        mastering_heal_resume_stage(
            error="sonic_context.json fingerprint mismatch",
            stage="sonic_context_build",
        )
        == "sonic_context_build"
    )
    assert (
        mastering_heal_resume_stage(
            error="understanding/content_brief.json fingerprint mismatch",
            stage="sound_design_palettes",
        )
        == "content_brief_reanchor"
    )


def test_hm2_unattended_sonic_self_pin(ctx: RunContext) -> None:
    assert (
        resume_producer_for_block(ctx, consumer_stage="sonic_context_build", message="")
        == "sonic_context_build"
    )
    assert (
        resume_producer_for_block(
            ctx,
            consumer_stage="sound_design_palettes",
            message="understanding/content_brief.json missing",
        )
        == "content_brief_reanchor"
    )


def test_hm2_heal_navigate_sonic_does_not_pin_edl(ctx: RunContext) -> None:
    nav = heal_navigate(
        ctx,
        error="fingerprint mismatch on upstream artifact",
        stage="sonic_context_build",
    )
    assert nav["from_stage"] == "sonic_context_build"
    assert nav["from_stage"] != "edl"
    pal = heal_navigate(
        ctx,
        error="fingerprint mismatch",
        stage="sound_design_palettes",
    )
    assert pal["from_stage"] == "sound_design_palettes"
