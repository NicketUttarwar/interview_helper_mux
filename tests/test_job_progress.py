"""gui_job intra-stage progress for long local stages."""

from __future__ import annotations

import json
import time
from pathlib import Path

from interview_mux.operator_subprocess import JobProgressReporter, touch_job_progress
from run_fixtures import isolated_run_ctx


def _write_running_job(ctx) -> None:
    ctx.write_json(
        "gui_job.json",
        {
            "status": "running",
            "stage": "disfluency_extract",
            "current_stage": "disfluency_extract",
            "message": "Running Disfluency extract… (1/1)",
        },
    )


def test_touch_job_progress_updates_step_fields(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_job_progress")
    _write_running_job(ctx)

    touch_job_progress(
        ctx,
        "Checking gap 12/389 for voice activity…",
        phase="gap_scan",
        step_index=12,
        step_total=389,
    )

    job = json.loads((ctx.run_dir / "gui_job.json").read_text(encoding="utf-8"))
    assert job["message"] == "Checking gap 12/389 for voice activity…"
    assert job["phase"] == "gap_scan"
    assert job["step_index"] == 12
    assert job["step_total"] == 389
    assert job.get("updated_at")


def test_touch_job_progress_ignores_non_running_job(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_job_progress_idle")
    ctx.write_json(
        "gui_job.json",
        {"status": "complete", "message": "Done", "step_index": 1, "step_total": 9},
    )

    touch_job_progress(ctx, "Should not apply", phase="gap_scan", step_index=2, step_total=9)

    job = json.loads((ctx.run_dir / "gui_job.json").read_text(encoding="utf-8"))
    assert job["message"] == "Done"
    assert job["step_index"] == 1


def test_job_progress_reporter_throttles_ticks(tmp_path: Path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_job_progress_throttle")
    _write_running_job(ctx)
    reporter = JobProgressReporter(
        ctx,
        stage="disfluency_extract",
        phase="gap_scan",
        step_total=10,
    )

    times = iter([0.0, 0.5, 3.0, 6.0])
    monkeypatch.setattr(time, "monotonic", lambda: next(times))

    reporter.tick(1, "first")
    reporter.tick(2, "second")
    reporter.tick(3, "third", force=True)

    job = json.loads((ctx.run_dir / "gui_job.json").read_text(encoding="utf-8"))
    assert job["message"] == "third"
    assert job["step_index"] == 3
