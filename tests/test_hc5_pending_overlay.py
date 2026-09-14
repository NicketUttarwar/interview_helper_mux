"""HC-5: Partial/Full-auto keep automation_pending while the driver owns framing.

Manual Yes/No stays hard_block. Later speaker/voice/delivery sub-gates stay
driver-owned. Do not start a run. HV-5 G1 needs_operator override stays.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.operator_gate_view import resolve_framing_gate
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.gap_fill_was_skipped",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.gap_framing_enabled",
        lambda *_a, **_k: True,
    )
    return isolated_run_ctx(tmp_path, "hc5_framing")


def _patch_pending(
    monkeypatch: pytest.MonkeyPatch,
    *,
    framing: bool = False,
    speaker: bool = False,
    voice: bool = False,
    delivery: bool = False,
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.check_gap_framing_decision_pending",
        lambda *_a, **_k: framing,
    )
    monkeypatch.setattr(
        "interview_mux.source_topology.check_pickup_speaker_pending",
        lambda *_a, **_k: speaker,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.check_voice_reference_pending",
        lambda *_a, **_k: voice,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.check_gap_delivery_pending",
        lambda *_a, **_k: delivery,
    )


def test_hc5_partial_framing_is_automation_pending(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pending(monkeypatch, framing=True)
    meta = {
        "run_mode": "partially-accelerated",
        "partial_auto": True,
        "partial_auto_driver_active": True,
    }
    view = resolve_framing_gate(ctx, meta)
    assert view.severity == "automation_pending"
    assert view.operator_must_act is False
    assert view.blocks_journey is False


def test_hc5_full_auto_framing_is_automation_pending(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pending(monkeypatch, framing=True)
    meta = {"run_mode": "full-auto", "full_auto": True}
    view = resolve_framing_gate(ctx, meta)
    assert view.severity == "automation_pending"
    assert view.operator_must_act is False


def test_hc5_manual_framing_is_hard_block(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pending(monkeypatch, framing=True)
    view = resolve_framing_gate(ctx, {"run_mode": "manual"})
    assert view.severity == "hard_block"
    assert view.operator_must_act is True
    assert view.blocks_journey is True
    assert view.ui_mode == "framing_choice"


def test_hc5_partial_speaker_stays_automation_pending(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pending(monkeypatch, speaker=True)
    meta = {
        "run_mode": "partially-accelerated",
        "partial_auto_driver_active": True,
    }
    view = resolve_framing_gate(ctx, meta)
    assert view.severity == "automation_pending"
    assert view.operator_must_act is False


def test_hc5_partial_voice_and_delivery_stay_automation_pending(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pending(monkeypatch, voice=True)
    meta = {"full_auto": True}
    voice = resolve_framing_gate(ctx, meta)
    assert voice.severity == "automation_pending"
    _patch_pending(monkeypatch, delivery=True)
    delivery = resolve_framing_gate(ctx, meta)
    assert delivery.severity == "automation_pending"


def test_hc5_needs_operator_still_hard_blocks(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pending(monkeypatch, framing=True)
    meta = {
        "partial_auto": True,
        "partial_auto_driver_active": True,
        "needs_operator": True,
        "needs_operator_stage": "missing_framing",
    }
    view = resolve_framing_gate(ctx, meta)
    assert view.severity == "hard_block"
    assert view.operator_must_act is True


def test_hc5_gui_lease_lifts_overlay(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.automation_run import take_gate_advance_lease

    _patch_pending(monkeypatch, framing=True)
    take_gate_advance_lease(ctx, source="gui", gate_id="gap_framing")
    meta = {
        "run_mode": "partially-accelerated",
        "partial_auto": True,
        "partial_auto_driver_active": True,
    }
    view = resolve_framing_gate(ctx, meta)
    assert view.severity != "automation_pending"
    assert view.operator_must_act is True
