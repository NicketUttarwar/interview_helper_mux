"""The sound design plan's producer may land its plan under the soft freeze (ISSUES 116)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.seat_authority import frozen_seat_write_allowed
from run_fixtures import isolated_run_ctx

SDP = "understanding/sound_design_plan.json"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    c = isolated_run_ctx(tmp_path, "sdp_producer_freeze")
    p = c.final_path("understanding", "sound_design_plan.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"_meta": {"producer_stage": "sound_design_palettes"}, "flow_plans": {}}', encoding="utf-8")
    c.write_json("master/selection.json", {"ordered_segment_ids": ["seg_1"]}, skip_handoff=True)
    return c


def _freeze(monkeypatch, *, soft: bool, hard: bool) -> None:
    monkeypatch.setattr("interview_mux.seat_authority.soft_freeze_active", lambda c: soft)
    monkeypatch.setattr("interview_mux.seat_authority.hard_freeze_active", lambda c: hard)


def test_producer_write_allowed_under_soft_freeze_with_a_current_plan_on_disk(ctx, monkeypatch) -> None:
    _freeze(monkeypatch, soft=True, hard=False)
    assert frozen_seat_write_allowed(ctx, SDP, reason="sound_design_plan") is True


def test_producer_write_refused_under_hard_freeze(ctx, monkeypatch) -> None:
    _freeze(monkeypatch, soft=False, hard=True)
    assert frozen_seat_write_allowed(ctx, SDP, reason="sound_design_plan") is False


def test_a_foreign_writer_is_still_refused_under_soft_freeze(ctx, monkeypatch) -> None:
    _freeze(monkeypatch, soft=True, hard=False)
    assert frozen_seat_write_allowed(ctx, SDP, reason="edl") is False
