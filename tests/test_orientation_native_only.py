"""Gap framing disabled resolves the orientation contract to a durable omit (ISSUES 51)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.opening_orientation import (
    ensure_episode_orientation_body,
    orientation_omitted,
)
from interview_mux.publishability_boundary import _orientation_demand_applies
from interview_mux.run_context import RunContext


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool) -> RunContext:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_orientation_native_only", create=True)
    monkeypatch.setattr("interview_mux.gap_vo_gates.gap_framing_enabled", lambda c: enabled)
    return ctx


def test_body_records_omit_when_framing_disabled(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, enabled=False)
    report = {"interviewer_lines": [], "gaps": [], "skipped": True, "empty_ok": True}
    out, actions = ensure_episode_orientation_body(ctx, report, ["seg_001", "seg_004"])
    assert orientation_omitted(out) is True
    assert out["opening_orientation"]["omit_reason"] == "gap_framing_disabled"
    assert out["opening_orientation"]["target_segment_id"] == "seg_001"
    assert actions and actions[0]["action"] == "omit_episode_orientation"


def test_body_keeps_an_existing_omit(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, enabled=False)
    meta = {"omitted": True, "required": False, "omit_reason": "operator"}
    report = {"interviewer_lines": [], "opening_orientation": meta}
    out, actions = ensure_episode_orientation_body(ctx, report, ["seg_001"])
    assert out["opening_orientation"] == meta
    assert actions == []


def test_publishability_does_not_demand_a_line_nobody_may_mint(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, enabled=False)
    assert _orientation_demand_applies(ctx, {"interviewer_lines": []}) is False


def test_publishability_still_validates_a_line_that_exists(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, enabled=False)
    line = {"line_id": "vo_preface_episode_orientation", "line_category": "episode_preface", "text": "x"}
    assert _orientation_demand_applies(ctx, {"interviewer_lines": [line]}) is True


def test_publishability_demands_when_framing_enabled(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, enabled=True)
    assert _orientation_demand_applies(ctx, {"interviewer_lines": []}) is True
