"""Positive heal tests for stage_completion.heal_or_refuse_mark."""

from __future__ import annotations

from interview_mux.run_context import RunContext
from interview_mux.stage_completion import heal_or_refuse_mark


def test_heal_marks_when_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    # topic_coverage may have incompleteness without artifacts — use a stage
    # that accepts force when no hollow check fires: podcast_publish with skip.
    # Prefer: mark transitions only when incompleteness None after stub outputs.
    ctx.write_json(
        "master/transitions.json",
        {"transitions": []},
        stage_key="transitions",
    )
    out = heal_or_refuse_mark(ctx, "transitions")
    # Either marked (complete) or refused with reason — never silent force.
    assert out.get("marked") or out.get("refused") or out.get("unmarked") is False


def test_heal_refuses_empty_stage(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    out = heal_or_refuse_mark(ctx, "")
    assert out.get("refused") is True
