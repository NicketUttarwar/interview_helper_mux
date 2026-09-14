"""HC-6: GUI Continues after a gate POST in all modes; dual walk is the lease.

Gate panels must pass the refreshed snapshot. Do not start a run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.automation_run import should_advance_after_gate_post

_REPO = Path(__file__).resolve().parents[1]
_GATES = _REPO / "frontend" / "src" / "components" / "gates"
_HC6_PANELS = (
    "GapFramingGatePanel.tsx",
    "GapDeliveryPanel.tsx",
    "VoiceReferencePanel.tsx",
    "PickupSpeakerPanel.tsx",
    "VoPickupPanel.tsx",
)


@pytest.fixture(autouse=True)
def _forensics_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")


def test_hc6_manual_advances() -> None:
    assert should_advance_after_gate_post({"run_mode": "manual"}) is True
    assert should_advance_after_gate_post(None) is True


def test_hc6_partial_driver_true_does_not_advance() -> None:
    assert (
        should_advance_after_gate_post(
            {
                "run_mode": "partially-accelerated",
                "partial_auto_driver_active": True,
            }
        )
        is True
    )


def test_hc6_partial_driver_false_advances() -> None:
    assert (
        should_advance_after_gate_post(
            {
                "run_mode": "partially-accelerated",
                "partial_auto_driver_active": False,
            }
        )
        is True
    )


def test_hc6_partial_missing_flag_fail_closed() -> None:
    assert should_advance_after_gate_post({"run_mode": "partially-accelerated"}) is True
    assert should_advance_after_gate_post({"partial_auto": True}) is True


def test_hc6_full_auto_gui_advances() -> None:
    assert should_advance_after_gate_post({"run_mode": "full-auto", "full_auto": True}) is True
    assert should_advance_after_gate_post({"full_auto": True}) is True


def test_hc6_panels_use_refreshed_snapshot() -> None:
    for name in _HC6_PANELS:
        text = (_GATES / name).read_text(encoding="utf-8")
        assert "shouldAdvanceAfterGatePost" in text
        assert "shouldAdvanceAfterGatePost(run)" not in text
        assert "shouldAdvanceAfterGatePost(refreshed" in text


def test_hc6_gui_lease_blocks_driver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.automation_run import (
        driver_may_walk,
        gui_holds_fresh_lease,
        take_gate_advance_lease,
    )
    from run_fixtures import isolated_run_ctx

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "hc6_lease")
    take_gate_advance_lease(ctx, source="gui", gate_id="gap_framing")
    assert gui_holds_fresh_lease(ctx) is True
    assert driver_may_walk(ctx) is False


def test_hc6_expired_gui_lease_lets_driver_steal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime, timedelta, timezone

    from interview_mux.automation_run import (
        GATE_ADVANCE_LEASE_REL,
        driver_may_walk,
        gui_holds_fresh_lease,
        read_gate_advance_lease,
        take_gate_advance_lease,
    )
    from run_fixtures import isolated_run_ctx

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "hc6_ttl")
    take_gate_advance_lease(ctx, source="gui", gate_id="g_listen")
    stale = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    ctx.write_json(
        GATE_ADVANCE_LEASE_REL,
        {"source": "gui", "gate_id": "g_listen", "at": stale},
        skip_handoff=True,
    )
    assert gui_holds_fresh_lease(ctx) is False
    assert driver_may_walk(ctx) is True
    lease = read_gate_advance_lease(ctx) or {}
    assert lease.get("source") == "driver"


def test_hc6_driver_walks_without_gui_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.automation_run import driver_may_walk, read_gate_advance_lease
    from run_fixtures import isolated_run_ctx

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "hc6_driver_only")
    assert driver_may_walk(ctx) is True
    lease = read_gate_advance_lease(ctx) or {}
    assert lease.get("source") == "driver"
