from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.operator_action_trace import (
    begin_action,
    end_action,
    format_dump_text,
    read_action_trace,
)
from interview_mux.run_context import RunContext


@pytest.fixture
def trace_ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_EXECUTIONS_ROOT", str(tmp_path / "executions"))
    ctx = RunContext("exec_test_trace", create=True)
    return ctx


def test_begin_end_action(trace_ctx):
    tid = begin_action(
        "write_approval.approve",
        run_dir=trace_ctx.run_dir,
        stage="audio_preclean",
        origin="api",
    )
    end_action(tid, run_dir=trace_ctx.run_dir, status="ok", detail={"flushed": ["a.wav"]})
    entries = read_action_trace(trace_ctx.run_dir, tail=10)
    assert len(entries) >= 2
    assert entries[0]["action_id"] == "write_approval.approve"
    assert entries[0]["status"] == "running"


def test_format_dump_text(trace_ctx):
    tid = begin_action(
        "pipeline.execute_stage",
        run_dir=trace_ctx.run_dir,
        stage="ingest",
        origin="pipeline",
        command=["ffmpeg", "-y"],
    )
    end_action(tid, run_dir=trace_ctx.run_dir, status="ok")
    text = format_dump_text(read_action_trace(trace_ctx.run_dir))
    assert "pipeline.execute_stage" in text
    assert "ingest" in text


def test_approve_stage_writes_trace(trace_ctx, monkeypatch):
    from interview_mux.write_staging import approve_stage_writes, write_pending_content

    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled",
        lambda: True,
    )
    write_pending_content(trace_ctx, "audio_preclean", "preclean/lineage.json", data={"v": 1})
    flushed = approve_stage_writes(trace_ctx, "audio_preclean")
    assert flushed
    entries = read_action_trace(trace_ctx.run_dir)
    ids = [e.get("action_id") for e in entries]
    assert "write_approval.approve" in ids
