"""HX-4: mix/junction/finalize leases must not pin mix while music is incomplete.

premature_cap_hard_pin ignores those three leases until music_epoch_complete
and pins MUSIC_BEFORE_MIX. Music/VO leases stay. Mix seating (HX-2) later.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import (
    MUSIC_BEFORE_MIX,
    premature_cap_hard_pin,
)
from interview_mux.run_context import RunContext
from interview_mux.thrash_hardening import expensive_stage_lease_active
from run_fixtures import MINIMAL_WAV_BYTES, isolated_run_ctx


_MIX_LEASE = ("mix", "junction_snip_qa", "master_finalize")


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hx4_mix_lease")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _job(ctx: RunContext, *, status: str, stage: str) -> None:
    ctx.write_json(
        "gui_job.json",
        {"status": status, "current_stage": stage},
        skip_handoff=True,
    )


def _assembly_wav(ctx: RunContext) -> None:
    dest = ctx.final_path("master", "assembly.wav")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(MINIMAL_WAV_BYTES)


def test_hx4_running_mix_lease_pins_music_not_mix(ctx: RunContext) -> None:
    _job(ctx, status="running", stage="mix")
    leased, stage = expensive_stage_lease_active(ctx)
    assert leased and stage == "mix"
    pin = premature_cap_hard_pin(ctx, "mix")
    assert pin in MUSIC_BEFORE_MIX
    assert pin != "mix"
    assert premature_cap_hard_pin(ctx, "edl_narrative_audit") in MUSIC_BEFORE_MIX


@pytest.mark.parametrize("lease_stage", _MIX_LEASE)
def test_hx4_mix_family_running_leases_pin_music(
    ctx: RunContext, lease_stage: str
) -> None:
    _job(ctx, status="starting", stage=lease_stage)
    leased, held = expensive_stage_lease_active(ctx)
    assert leased and held == lease_stage
    pin = premature_cap_hard_pin(ctx, lease_stage)
    assert pin in MUSIC_BEFORE_MIX
    assert pin not in _MIX_LEASE


def test_hx4_error_mix_growth_lease_pins_music(ctx: RunContext) -> None:
    _job(ctx, status="error", stage="mix")
    _assembly_wav(ctx)
    leased, stage = expensive_stage_lease_active(ctx)
    assert leased and stage == "mix"
    pin = premature_cap_hard_pin(ctx, "mix")
    assert pin in MUSIC_BEFORE_MIX
    assert pin != "mix"


def test_hx4_pending_writes_mix_lease_pins_music(ctx: RunContext) -> None:
    pending = ctx.run_dir / ".pending_writes" / "mix"
    pending.mkdir(parents=True)
    (pending / "stub.txt").write_text("x", encoding="utf-8")
    _assembly_wav(ctx)
    leased, stage = expensive_stage_lease_active(ctx)
    assert leased and stage == "mix"
    pin = premature_cap_hard_pin(ctx, "junction_snip_qa")
    assert pin in MUSIC_BEFORE_MIX
    assert pin != "mix"


def test_hx4_mmaudio_lease_still_holds_while_music_incomplete(ctx: RunContext) -> None:
    _job(ctx, status="running", stage="mmaudio_sfx")
    leased, stage = expensive_stage_lease_active(ctx)
    assert leased and stage == "mmaudio_sfx"
    assert premature_cap_hard_pin(ctx, "mix") == "mmaudio_sfx"
    assert premature_cap_hard_pin(ctx, "edl_narrative_audit") == "mmaudio_sfx"


def test_hx4_mix_lease_holds_after_music_complete(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _job(ctx, status="running", stage="mix")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _ctx: True,
    )
    leased, stage = expensive_stage_lease_active(ctx)
    assert leased and stage == "mix"
    assert premature_cap_hard_pin(ctx, "mix") == "mix"
    assert premature_cap_hard_pin(ctx, "master_finalize") == "mix"
