"""Tier A of the VO contract ladder does nothing before a layup plan exists (ISSUES 156).

exec_015: the delivery invariant ran tier_a_publish_orientation before
nugget_layup_compose; publishing an empty plan raised
hosted_vo_floor_unsatisfiable (active_synthetic=0, eligible_nuggets=0) at error level.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx


def test_no_plan_no_publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux import execution_contract as ec

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "exec_tier_a")
    monkeypatch.setattr("interview_mux.seat_authority.gate_seat_mutation", lambda *a, **k: True)
    called: list[str] = []
    monkeypatch.setattr(
        "interview_mux.nugget_layup.publish_layup_plan_to_gap_report",
        lambda c, p: called.append("publish"),
    )
    assert ec._tier_a_publish_orientation(ctx) == []
    assert called == []
