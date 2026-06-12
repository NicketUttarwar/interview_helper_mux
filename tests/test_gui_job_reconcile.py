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


def test_reconcile_stale_jobs_scans_all(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    wav = _wav_path(tmp_path)
    for rid in ("exec_011_20260101T000011Z", "exec_012_20260101T000012Z"):
        ctx = RunContext(rid)
        ctx.init_run_meta(wav)
        ctx.write_json("gui_job.json", {"status": "running", "stage": "ingest"})
    assert reconcile_stale_jobs() == 2
