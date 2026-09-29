"""The delivery conductor is re-entered while it keeps landing stages (ISSUES 47)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.pipeline import _run_delivery_conductor_until_stalled
from interview_mux.run_context import RunContext
from interview_mux.v2.config import DELIVERY_ORDER


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_conductor_loop", create=True)
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    # The loop counts land-honest stages; these fakes land bare markers only.
    monkeypatch.setattr(
        "interview_mux.done_authority.may_skip_as_complete", lambda c, s: c.is_done(s)
    )
    return ctx


def test_loop_re_enters_while_each_pass_lands_one_stage(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    order = list(DELIVERY_ORDER[:4])
    calls: list[int] = []

    def fake_phase(c: RunContext, phase: str, planned: list[str]) -> dict:
        # One producer per pass, exactly how the seed-front pin behaves.
        left = [s for s in order if not c.is_done(s)]
        calls.append(len(left))
        (c.run_dir / ".stage_done" / left[0]).touch()
        return {"remaining_after": left[1:]}

    result = _run_delivery_conductor_until_stalled(ctx, order, fake_phase)
    assert result["remaining_after"] == []
    assert calls == [4, 3, 2, 1]
    assert all(ctx.is_done(s) for s in order)


def test_loop_stops_on_the_first_pass_that_lands_nothing(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    order = list(DELIVERY_ORDER[:3])
    calls: list[str] = []

    def fake_phase(c: RunContext, phase: str, planned: list[str]) -> dict:
        calls.append(phase)
        if len(calls) == 1:
            (c.run_dir / ".stage_done" / order[0]).touch()
        return {"remaining_after": order[1:]}

    result = _run_delivery_conductor_until_stalled(ctx, order, fake_phase)
    # Pass 1 landed a stage, pass 2 landed nothing: hand back to the caller.
    assert calls == ["delivery", "delivery"]
    assert result["remaining_after"] == order[1:]


def test_loop_returns_at_once_when_blocked_on_analysis(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    calls: list[int] = []

    def fake_phase(c: RunContext, phase: str, planned: list[str]) -> dict:
        calls.append(1)
        (c.run_dir / ".stage_done" / DELIVERY_ORDER[0]).touch()
        return {"conductor": {"blocked_on_analysis": ["missing_framing"]}, "remaining_after": ["edl"]}

    result = _run_delivery_conductor_until_stalled(ctx, list(DELIVERY_ORDER[:2]), fake_phase)
    assert len(calls) == 1
    assert result["conductor"]["blocked_on_analysis"] == ["missing_framing"]
