"""Operator gate view — GUI/backend parity for G1 and framing."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.operator_gate_view import (
    build_operator_gates,
    g1_journey_clear,
    resolve_g1_vo_gate,
)
from run_fixtures import isolated_run_ctx


def _gap_line(**overrides: object) -> dict:
    base = {
        "line_id": "vo_line_1",
        "delivery": "synthesize",
        "severity": "medium",
        "targets_segment_id": "seg_1",
        "gap_type": "missing_framing",
        "text": "Can you expand on that?",
        "placement": "after",
    }
    base.update(overrides)
    return base


def test_g1_optional_journey_clear_without_wav(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("interview_mux.v2.config.v2_g1_optional", lambda: True)
    ctx = isolated_run_ctx(tmp_path, "run_g1_auto")
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [_gap_line()]},
    )
    meta = {
        "partial_auto": True,
        "partial_auto_driver_active": True,
        "gap_framing_enabled": True,
        "gap_vo_delivery": "chatterbox",
        "voice_reference_approved_at": "2026-01-01T00:00:00Z",
    }
    ctx.write_json("run_meta.json", meta)
    view = resolve_g1_vo_gate(ctx, None, meta)
    assert view.severity == "automation_pending"
    assert view.operator_must_act is False
    assert g1_journey_clear(ctx, meta)


def test_g1_hard_block_when_not_optional(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("interview_mux.v2.config.v2_g1_optional", lambda: False)
    ctx = isolated_run_ctx(tmp_path, "run_g1_hard")
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [_gap_line(delivery="record", severity="high")]},
    )
    view = resolve_g1_vo_gate(ctx, None, {})
    assert view.operator_must_act is True
    assert view.stage_status == "action_required"
    assert not g1_journey_clear(ctx, {})


def test_framing_decision_action_required(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_framing")
    ctx.write_json("run_meta.json", {"gap_framing_enabled": True})
    gates = build_operator_gates(ctx, None, {"gap_framing_enabled": True})
    framing = gates["missing_framing"]
    assert framing["stage_status"] in {"action_required", "automation_pending", "pending"}
