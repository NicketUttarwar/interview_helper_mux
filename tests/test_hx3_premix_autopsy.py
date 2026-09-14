"""HX-3: pre_mix reads live seam autopsy blocking_reasons.

master/seam_autopsy.json first, mastering/ fallback. Residual-view miss must
not greenwash mix. Heal pins junction_snip_qa. HX-5 G-Listen stays later.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.heal_routing import classify_heal_error, resume_stage_for_error_class
from interview_mux.publishability_boundary import (
    PublishabilityViolation,
    validate_publishability,
    violation_playbook,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import producer_pin_for_token
from interview_mux.thrash_hardening import heal_navigate
from run_fixtures import isolated_run_ctx

_REASON = "critical_incomplete_cut_residuals"


def _write_raw(ctx: RunContext, rel: str, data: dict) -> None:
    path = ctx.final_path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _plant_keep(ctx: RunContext) -> None:
    _write_raw(
        ctx,
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_001"],
            "timeline_duration_ms": 1000,
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_001",
                    "source_start_ms": 0,
                    "source_end_ms": 1000,
                    "duration_ms": 1000,
                    "timeline_start_ms": 0,
                }
            ],
        },
    )
    _write_raw(
        ctx,
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001"], "excluded_segment_ids": []},
    )


def _autopsy(*, reasons: list[str]) -> dict:
    return {
        "version": 1,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "phase": "post_junction",
        "commitment": {"status": "pending"},
        "scores": {
            "continuity": 0.5,
            "finishability": 0.5,
            "sonic_density_fit": 0.5,
            "information_clarity": 0.5,
            "music_completeness": 0.5,
        },
        "seams": [],
        "blocking_reasons": reasons,
    }


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hx3_autopsy")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.has_critical_residuals",
        lambda _ctx: False,
    )
    _plant_keep(run)
    return run


def test_hx3_live_master_autopsy_blocks_pre_mix(ctx: RunContext) -> None:
    _write_raw(ctx, "master/seam_autopsy.json", _autopsy(reasons=[_REASON]))
    report = validate_publishability(ctx, checkpoint="pre_mix")
    autopsy_v = next(v for v in report.violations if v.code == "seam_autopsy_blocking")
    assert autopsy_v.error_class == "incomplete_cut_unresolved"
    assert violation_playbook(autopsy_v).resume_stage == "junction_snip_qa"


def test_hx3_mastering_fallback_when_master_missing(ctx: RunContext) -> None:
    _write_raw(ctx, "mastering/seam_autopsy.json", _autopsy(reasons=[_REASON]))
    report = validate_publishability(ctx, checkpoint="pre_mix")
    assert any(v.code == "seam_autopsy_blocking" for v in report.violations)


def test_hx3_live_master_wins_over_mastering(ctx: RunContext) -> None:
    _write_raw(ctx, "master/seam_autopsy.json", _autopsy(reasons=[]))
    _write_raw(ctx, "mastering/seam_autopsy.json", _autopsy(reasons=[_REASON]))
    report = validate_publishability(ctx, checkpoint="pre_mix")
    assert not any(v.code == "seam_autopsy_blocking" for v in report.violations)


def test_hx3_empty_autopsy_does_not_block(ctx: RunContext) -> None:
    _write_raw(ctx, "master/seam_autopsy.json", _autopsy(reasons=[]))
    report = validate_publishability(ctx, checkpoint="pre_mix")
    assert not any(v.error_class == "incomplete_cut_unresolved" for v in report.violations)


def test_hx3_heal_pins_junction_not_mix(ctx: RunContext) -> None:
    err = (
        "publishability blocked at pre_mix: incomplete_cut_unresolved — "
        "seam_autopsy_blocking: critical_incomplete_cut_residuals"
    )
    route = classify_heal_error(err, ctx, stage="mix")
    assert route is not None
    assert route.from_stage == "junction_snip_qa"
    assert route.from_stage != "mix"
    assert producer_pin_for_token(err, ctx=ctx) == "junction_snip_qa"
    assert resume_stage_for_error_class("seam_autopsy_blocking") == "junction_snip_qa"
    spec = violation_playbook(
        PublishabilityViolation(
            error_class="incomplete_cut_unresolved",
            code="seam_autopsy_blocking",
            detail=_REASON,
        )
    )
    assert spec.resume_stage == "junction_snip_qa"
    nav = heal_navigate(ctx, error=err, stage="mix")
    assert nav["from_stage"] == "junction_snip_qa"
    assert nav["from_stage"] != "mix"
