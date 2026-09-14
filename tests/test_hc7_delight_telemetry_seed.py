"""HC-7: seed-order must not skip listen_delight on waived_unattended.

Progress clearance is seed_complete or quality_waived only.
Do not start a run. A-04 music/ship fixtures stay.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import (
    LISTEN_DELIGHT_WAIVER_REL,
    listen_delight_cleared_for_progress,
    listen_delight_waived_unattended,
)
from interview_mux.homunculus.runtime import _seed_prereq_block
from interview_mux.llm_flow_hardening import _earliest_incomplete_seed_stage
from interview_mux.run_context import RunContext
from interview_mux.v2.config import DELIVERY_ORDER
from run_fixtures import isolated_run_ctx, mark_done_raw

_DELIGHT = "listen_delight_audit"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, stage: _ctx.is_done(stage),
    )
    return isolated_run_ctx(tmp_path, "hc7_delight")


def _mark_delivery_before(ctx: RunContext, stop: str) -> None:
    for sid in DELIVERY_ORDER:
        if sid == stop:
            break
        mark_done_raw(ctx, sid)


def test_hc7_waived_unattended_still_blocks_mix(ctx: RunContext) -> None:
    _mark_delivery_before(ctx, _DELIGHT)
    ctx.write_json(
        LISTEN_DELIGHT_WAIVER_REL,
        {"status": "waived_unattended", "stage": _DELIGHT},
        skip_handoff=True,
    )
    assert listen_delight_waived_unattended(ctx) is True
    assert listen_delight_cleared_for_progress(ctx) is False
    assert _earliest_incomplete_seed_stage(ctx, "mix") == _DELIGHT
    assert _seed_prereq_block(ctx, "mix") == _DELIGHT
    assert not ctx.is_done(_DELIGHT)


def test_hc7_seed_walker_does_not_mint_waiver(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.automation_run.automation_driver_run",
        lambda *_a, **_k: True,
    )
    ctx.write_json(
        "run_meta.json",
        {"automation_driver": True, "run_mode": "full-auto"},
        skip_handoff=True,
    )
    _mark_delivery_before(ctx, _DELIGHT)
    dest = ctx.final_path("master", "assembly.wav")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"RIFF" + b"\x00" * 64)
    ctx.write_json(
        "mastering/listen_delight_audit.json",
        {"passed": False, "advisory": True},
        skip_handoff=True,
    )
    assert _earliest_incomplete_seed_stage(ctx, "mix") == _DELIGHT
    assert listen_delight_waived_unattended(ctx) is False
    assert not ctx.artifact_exists(LISTEN_DELIGHT_WAIVER_REL)


def test_hc7_quality_waived_clears_seed_block(ctx: RunContext) -> None:
    _mark_delivery_before(ctx, "mix")
    done = ctx.run_dir / ".stage_done" / _DELIGHT
    if done.is_file():
        done.unlink()
    ctx.write_json(
        LISTEN_DELIGHT_WAIVER_REL,
        {"status": "quality_waived", "stage": _DELIGHT},
        skip_handoff=True,
    )
    assert not ctx.is_done(_DELIGHT)
    assert listen_delight_cleared_for_progress(ctx) is True
    assert _earliest_incomplete_seed_stage(ctx, "mix") is None
    assert _seed_prereq_block(ctx, "mix") is None


def test_hc7_seed_complete_delight_clears_block(ctx: RunContext) -> None:
    _mark_delivery_before(ctx, "mix")
    assert ctx.is_done(_DELIGHT)
    assert listen_delight_cleared_for_progress(ctx) is True
    assert _earliest_incomplete_seed_stage(ctx, "mix") is None
