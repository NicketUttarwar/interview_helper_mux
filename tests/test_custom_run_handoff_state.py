"""Handoff ack rules: write-approve auto-ack vs HandoffPanel."""

from __future__ import annotations

from interview_mux.custom_run_handoff import (
    STAGES_REQUIRING_HANDOFF_REVIEW,
    handoff_acknowledged,
    handoff_state_for_run,
)
from interview_mux.run_context import RunContext


def test_handoff_state_for_run_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    ctx.write_json("run_meta.json", {"handoff_ack": {"speaker_roles": "2020-01-01T00:00:00Z"}}, skip_handoff=True)
    state = handoff_state_for_run(ctx)
    assert state["handoff_ack"]["speaker_roles"]
    assert "handoff_between_stages_enabled" in state


def test_write_approve_skips_auto_ack_for_custom_run_stages(tmp_path, monkeypatch):
    """Custom-run handoff stages must not auto-ack on write-approve."""
    assert "speaker_roles" in STAGES_REQUIRING_HANDOFF_REVIEW
