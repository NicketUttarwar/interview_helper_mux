import pytest

from interview_mux.run_context import RunContext
from interview_mux.web.runner import JobRunner


def test_clear_operator_pause_writes_complete_job(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ASSETS_ROOT", str(tmp_path))
    ctx = RunContext("test_pause", create=True)
    ctx.write_json(
        "gui_job.json",
        {
            "status": "awaiting_write_approval",
            "stage": "ingest",
            "pending_write_stage": "ingest",
            "pending_write_paths": ["ingest/checksums.json"],
        },
    )
    runner = JobRunner()
    runner.clear_operator_pause(ctx, "ingest", message="Ingest: saved 2 file(s) to disk.")
    job = ctx.read_json("gui_job.json")
    assert job["status"] == "complete"
    assert job.get("pending_write_stage") is None
    assert job.get("awaiting_write_approval") is False
