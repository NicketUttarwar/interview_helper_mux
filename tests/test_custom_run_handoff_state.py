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


def test_maybe_auto_ack_handoffs_when_disabled(tmp_path, monkeypatch):
    from run_fixtures import minimal_speakers

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.first_try.first_try_mode_enabled",
        lambda cfg=None: True,
    )
    ctx = RunContext(create=True)
    ctx.write_json("run_meta.json", {"handoff_ack": {}}, skip_handoff=True)
    ctx.mark_done("speaker_roles", force=True)
    ctx.write_json(
        "understanding/speakers.json",
        minimal_speakers(),
        skip_handoff=True,
    )
    state = handoff_state_for_run(ctx)
    meta = ctx.read_json("run_meta.json")
    assert meta.get("handoff_ack", {}).get("speaker_roles")
    assert state.get("pending_handoff_stage") is None


def test_write_approve_skips_auto_ack_for_custom_run_stages(tmp_path, monkeypatch):
    """Custom-run handoff stages must not auto-ack on write-approve."""
    assert "speaker_roles" in STAGES_REQUIRING_HANDOFF_REVIEW
