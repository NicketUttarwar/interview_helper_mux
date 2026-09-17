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


def test_persist_inherits_batch_plan_and_marks_previous_done(tmp_path: Path) -> None:
    from interview_mux.web.job_progress import persist_running_stage_progress

    ctx = isolated_run_ctx(tmp_path, "run_job_inherit")
    ctx.write_json(
        "gui_job.json",
        {
            "status": "running",
            "stage": "edl",
            "current_stage": "edl",
            "stage_index": 2,
            "stage_total": 4,
            "stages_planned": ["transitions", "edl", "mix", "junction_snip_qa"],
            "message": "Running EDL… (2/4)",
        },
    )

    persist_running_stage_progress(
        ctx.run_id,
        "mix",
        index=1,
        total=1,
        stages_planned=["mix"],
        ctx=ctx,
    )
    job = json.loads((ctx.run_dir / "gui_job.json").read_text(encoding="utf-8"))
    assert job["current_stage"] == "mix"
    assert job["stage_total"] == 4
    assert job["stage_index"] == 3
    assert job["stages_planned"] == ["transitions", "edl", "mix", "junction_snip_qa"]
    assert job["stages_done"] == ["edl"]
    assert "(3/4)" in job["message"]


def test_hitch_inner_walk_sets_parent_and_keeps_hitch_running(tmp_path: Path) -> None:
    from interview_mux.web.job_progress import persist_running_stage_progress

    ctx = isolated_run_ctx(tmp_path, "run_job_hitch")
    setattr(ctx, "_chapter_close_hitch_inner", True)
    ctx.write_json(
        "gui_job.json",
        {
            "status": "running",
            "stage": "chapter_close_hitch",
            "current_stage": "chapter_close_hitch",
            "stage_index": 10,
            "stage_total": 20,
            "stages_planned": ["nugget_layup", "chapter_close_hitch", "edl", "mix"],
        },
    )

    persist_running_stage_progress(
        ctx.run_id,
        "edl",
        index=1,
        total=1,
        stages_planned=["edl"],
        ctx=ctx,
    )
    job = json.loads((ctx.run_dir / "gui_job.json").read_text(encoding="utf-8"))
    assert job["current_stage"] == "edl"
    assert job["parent_stage"] == "chapter_close_hitch"
    assert "chapter_close_hitch" not in (job.get("stages_done") or [])
    assert "Chapter-close hitch" in job["message"]


def test_overlay_keeps_running_stage_pending_and_upgrades_finished(monkeypatch) -> None:
    from interview_mux.web.job_progress import overlay_stage_list_status

    stages = [
        {"id": "edl", "status": "pending"},
        {"id": "mix", "status": "done"},
        {"id": "transcript_review", "status": "action_required"},
    ]
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _ctx, sid: sid == "edl",
    )
    overlay_stage_list_status(
        None,
        stages,
        job={
            "status": "running",
            "current_stage": "mix",
            "parent_stage": "chapter_close_hitch",
            "stages_planned": ["edl", "mix"],
        },
    )
    assert stages[0]["status"] == "done"
    assert stages[1]["status"] == "pending"
    assert stages[2]["status"] == "action_required"


def test_attach_live_stage_progress_uses_done_markers(tmp_path: Path, monkeypatch) -> None:
    from interview_mux.run_context import RunContext
    from interview_mux.web.job_progress import attach_live_stage_progress
    from run_fixtures import patch_executions_root

    # attach_live_stage_progress re-resolves the run by id, so the ctx under test
    # has to live at the canonical executions path, not beside it.
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("run_job_progress_attach", create=True)
    marker = ctx.final_path(".stage_done", "transitions")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("ok", encoding="utf-8")
    job = attach_live_stage_progress(
        ctx.run_id,
        {
            "status": "running",
            "current_stage": "edl",
            "parent_stage": "chapter_close_hitch",
            "stages_planned": ["transitions", "edl", "mix"],
            "stages_done": ["transitions"],
        },
    )
    by_id = {row["id"]: row["status"] for row in job["stage_progress"]}
    assert by_id["transitions"] == "done"
    assert by_id["edl"] == "running"
    assert by_id["mix"] == "pending"

