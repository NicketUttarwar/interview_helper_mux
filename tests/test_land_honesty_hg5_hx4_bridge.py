"""Land Honesty bridge: HG-5 heal pin + HX-4 mix lease must not bypass unpaid remaster.

Ownership until clear_remaster; junction/promote blocked while remaster owed.
MUX_FORENSICS=0.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

import pytest

from interview_mux.delivery_guardrails import (
    MUSIC_BEFORE_MIX,
    premature_cap_hard_pin,
    promote_complete_orphan_stage_done,
)
from interview_mux.done_authority import (
    unpaid_land_blocks_promote,
    unpaid_land_reason,
)
from interview_mux.mix_junction_seat import (
    begin_remaster,
    clear_remaster,
    remaster_in_flight,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import high_gap_heal_resume_stage
from interview_mux.thrash_hardening import expensive_stage_lease_active
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "land_honesty_hg5_hx4")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _write_assembly(ctx: RunContext) -> None:
    path = ctx.path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)


def _mock_seated_and_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _sid: True,
    )


def test_bridge_apis_importable_and_unpaid_land_blocks_promote() -> None:
    """HG-5 / HX-4 pin helpers stay importable; unpaid_land_blocks_promote is the choke."""
    assert callable(high_gap_heal_resume_stage)
    assert callable(premature_cap_hard_pin)
    assert callable(expensive_stage_lease_active)
    assert callable(unpaid_land_blocks_promote)
    assert callable(unpaid_land_reason)


def test_unpaid_remaster_blocks_mix_promote(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Land Honesty: remaster owed → unpaid_land_blocks_promote; orphan promote skips mix."""
    begin_remaster(ctx, owner="music_epoch")
    _write_assembly(ctx)
    _mock_seated_and_present(monkeypatch)

    assert remaster_in_flight(ctx) is True
    assert unpaid_land_reason(ctx, "mix") is not None
    assert unpaid_land_blocks_promote(ctx, "mix") is True
    assert unpaid_land_blocks_promote(ctx, "junction_snip_qa") is True

    promoted = promote_complete_orphan_stage_done(ctx, ("mix",))
    assert promoted == []
    assert not ctx.is_done("mix")

    clear_remaster(ctx)
    assert unpaid_land_blocks_promote(ctx, "mix") is False


def test_hx4_mix_lease_pins_music_without_bypassing_unpaid_remaster(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HX-4 music pin while lease held; unpaid remaster still blocks promote."""
    ctx.write_json(
        "gui_job.json",
        {"status": "running", "current_stage": "mix"},
        skip_handoff=True,
    )
    leased, stage = expensive_stage_lease_active(ctx)
    assert leased and stage == "mix"
    pin = premature_cap_hard_pin(ctx, "mix")
    assert pin in MUSIC_BEFORE_MIX
    assert pin != "mix"

    begin_remaster(ctx, owner="music_epoch")
    _write_assembly(ctx)
    _mock_seated_and_present(monkeypatch)
    assert unpaid_land_blocks_promote(ctx, "mix") is True
    assert promote_complete_orphan_stage_done(ctx, ("mix",)) == []


def test_hg5_heal_pin_does_not_bypass_unpaid_mix_land(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HG-5 resume pin stays compose/layup; does not clear unpaid mix remaster."""
    assert high_gap_heal_resume_stage(ctx) == "gap_framing_compose"
    ctx.write_json(
        "understanding/nugget_layup_plan.json",
        {"ordered_segment_ids": ["seg_001"], "layups": []},
        skip_handoff=True,
    )
    assert high_gap_heal_resume_stage(ctx) == "nugget_layup_compose"

    begin_remaster(ctx, owner="music_epoch")
    assert unpaid_land_blocks_promote(ctx, "mix") is True
    # Heal pin API must not pay remaster land.
    assert high_gap_heal_resume_stage(ctx) == "nugget_layup_compose"
    assert remaster_in_flight(ctx) is True
    assert unpaid_land_reason(ctx, "mix") is not None
