from __future__ import annotations

from interview_mux.gui_job_reconcile import reconcile_stale_job, reconcile_stale_jobs
from interview_mux.run_context import RunContext
from interview_mux.session_log import read_log


def _wav_path(tmp_path) -> str:
    assets = tmp_path / "ASSETS" / "input"
    assets.mkdir(parents=True)
    wav = assets / "interview.wav"
    wav.write_bytes(b"RIFF")
    return str(wav.relative_to(tmp_path))


def test_reconcile_stale_running_job(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    ctx = RunContext("exec_010_20260101T000010Z")
    ctx.init_run_meta(_wav_path(tmp_path))
    ctx.write_json(
        "gui_job.json",
        {"status": "running", "stage": "transcribe", "mode": "stage"},
    )

    assert reconcile_stale_job(ctx.run_id) is True
    job = ctx.read_json("gui_job.json")
    assert job["status"] == "interrupted"
    assert "Server restarted" in job["message"]
    entries = read_log(ctx.run_dir, tail=10)
    assert any("Server restarted" in e.get("message", "") for e in entries)


def test_sanitize_gui_job_clears_after_reuse_decision(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    ctx = RunContext("exec_020_20260101T000020Z")
    ctx.init_run_meta(_wav_path(tmp_path))
    meta = ctx.read_json("run_meta.json")
    meta.setdefault("stage_reuse", {})["transcribe"] = {
        "action": "decline",
        "at": "2026-01-01T00:00:00Z",
    }
    ctx.write_json("run_meta.json", meta)
    ctx.write_json(
        "gui_job.json",
        {
            "status": "needs_operator",
            "stage": "transcribe",
            "needs_stage_reuse": True,
            "reuse_candidates": [{"run_id": "exec_old", "paths": []}],
        },
    )

    from interview_mux.gui_job_reconcile import reconcile_job_if_stale

    job = reconcile_job_if_stale(ctx.run_id, lock_held=False)
    assert job.get("needs_stage_reuse") is False
    assert job.get("status") == "complete"
    on_disk = ctx.read_json("gui_job.json")
    assert on_disk.get("needs_stage_reuse") is False


def test_reconcile_stale_jobs_scans_all(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    wav = _wav_path(tmp_path)
    for rid in ("exec_011_20260101T000011Z", "exec_012_20260101T000012Z"):
        ctx = RunContext(rid)
        ctx.init_run_meta(wav)
        ctx.write_json("gui_job.json", {"status": "running", "stage": "ingest"})
    assert reconcile_stale_jobs() == 2


def test_reconcile_does_not_stall_live_subprocess_worker(tmp_path, monkeypatch) -> None:
    import os

    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    ctx = RunContext("exec_031_20260101T000031Z")
    ctx.init_run_meta(_wav_path(tmp_path))
    ctx.write_json(
        "gui_job.json",
        {
            "status": "running",
            "stage": "audio_preclean",
            "worker_pid": os.getpid(),
            "worker_kind": "stage_subprocess",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )

    from interview_mux.gui_job_reconcile import reconcile_job_if_stale

    job = reconcile_job_if_stale(ctx.run_id, lock_held=True)
    assert job["status"] == "running"


def test_reconcile_revives_stalled_when_worker_alive(tmp_path, monkeypatch) -> None:
    import os

    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    ctx = RunContext("exec_032_20260101T000032Z")
    ctx.init_run_meta(_wav_path(tmp_path))
    ctx.write_json(
        "gui_job.json",
        {
            "status": "stalled",
            "stalled": True,
            "stage": "audio_preclean",
            "worker_pid": os.getpid(),
            "worker_kind": "stage_subprocess",
            "message": "Stage stalled — no progress recently. Safe to re-run.",
        },
    )

    from interview_mux.gui_job_reconcile import reconcile_job_if_stale

    job = reconcile_job_if_stale(ctx.run_id, lock_held=False)
    assert job["status"] == "running"
    assert not job.get("stalled")


def test_live_worker_detects_subprocess_pid(tmp_path, monkeypatch) -> None:
    import os

    from interview_mux.gui_job_reconcile import _live_worker

    assert _live_worker({"worker_pid": os.getpid()}) is True
    assert _live_worker({"worker_pid": 999_999_999}) is False
    assert _live_worker({}) is False
