"""Tests for E2E final report rendering."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

E2E_SRC = Path(__file__).resolve().parents[1] / "E2E_RUN" / "src"
if str(E2E_SRC) not in sys.path:
    sys.path.insert(0, str(E2E_SRC))

from e2e_runner.final_report import render_report  # noqa: E402
from e2e_runner.types import IncidentRecord  # noqa: E402


def test_render_report_clean_run():
    now = datetime.now(timezone.utc)
    text = render_report(
        session_id="20260101T000000Z",
        input_audio="ASSETS/input/interview.wav",
        flows=("flow1", "flow2", "flow3"),
        outcome="passed",
        run_ids=["exec_001"],
        incidents=[],
        clean_flows=["flow1", "flow2", "flow3"],
        residual=[],
        started_at=now,
        ended_at=now,
    )
    assert "No heal incidents" in text
    assert "flow1" in text
