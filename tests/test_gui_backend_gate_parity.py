"""GUI and operator_gate_view agree on operator_must_act."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.operator_gate_view import build_operator_gates, g1_journey_clear
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


def test_g1_journey_clear_matches_operator_gates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("interview_mux.v2.config.v2_g1_optional", lambda: True)
    ctx = isolated_run_ctx(tmp_path, "run_parity")
    meta = {
        "partial_auto": True,
        "partial_auto_driver_active": True,
        "gap_framing_enabled": True,
        "gap_vo_delivery": "chatterbox",
        "voice_reference_approved_at": "2026-01-01T00:00:00Z",
    }
    ctx.write_json("run_meta.json", meta)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [_gap_line()]},
    )
    gates = build_operator_gates(ctx, None, meta)
    g1 = gates["g1_vo_pickup"]
    assert g1["operator_must_act"] is False
    assert g1_journey_clear(ctx, meta) is True
