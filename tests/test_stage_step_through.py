"""Legacy step-through cleanup helpers."""

from __future__ import annotations

from interview_mux.stage_step_through import clear_step_through_from, reset_step_through_session
from interview_mux.run_context import RunContext


def test_clear_step_through_from(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.run_context.repo_root",
        lambda: tmp_path,
    )
    ctx = RunContext("exec_001_20260101T000001Z")
    ctx.init_run_meta("ASSETS/input/interview.wav")
    meta = ctx.read_json("run_meta.json")
    meta["step_through"] = {
        "pending": {"stage_id": "ingest"},
        "approved": {"checksum": "proceed", "ingest": "proceed"},
    }
    ctx.write_json("run_meta.json", meta, skip_handoff=True)

    clear_step_through_from(ctx, "ingest", ["checksum", "ingest", "transcribe"])

    updated = ctx.read_json("run_meta.json")
    assert "step_through" not in updated or "pending" not in (updated.get("step_through") or {})


def test_reset_step_through_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.run_context.repo_root",
        lambda: tmp_path,
    )
    ctx = RunContext("exec_002_20260101T000002Z")
    ctx.init_run_meta("ASSETS/input/interview.wav")
    meta = ctx.read_json("run_meta.json")
    meta["step_through"] = {"pending": {"stage_id": "ingest"}}
    ctx.write_json("run_meta.json", meta, skip_handoff=True)

    reset_step_through_session(ctx)

    updated = ctx.read_json("run_meta.json")
    assert "step_through" not in updated
