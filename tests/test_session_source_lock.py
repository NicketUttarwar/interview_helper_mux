"""GUI session locks source audio after first execution start."""

from __future__ import annotations

from fastapi.testclient import TestClient

from interview_mux.gui_session import clear_active_execution, set_active_execution
from interview_mux.web.server import create_app


def test_create_run_rejected_when_session_active(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    clear_active_execution()
    set_active_execution("exec_001_20260101T000001Z", source_locked=True)

    client = TestClient(create_app())
    res = client.post(
        "/api/runs",
        json={"input_audio_path": "ASSETS/input/interview.wav"},
    )
    assert res.status_code == 409
    assert "already active" in res.json()["detail"].lower()
    clear_active_execution()


def test_reset_new_input_rejected_when_source_locked(tmp_path, monkeypatch) -> None:
    from interview_mux.run_context import RunContext

    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    assets = tmp_path / "ASSETS" / "input"
    assets.mkdir(parents=True)
    wav = assets / "interview.wav"
    wav.write_bytes(b"RIFF")

    ctx = RunContext("exec_002_20260101T000002Z")
    ctx.init_run_meta(str(wav.relative_to(tmp_path)))
    set_active_execution(ctx.run_id, source_locked=True, input_audio_path=str(wav))

    client = TestClient(create_app())
    res = client.post(
        f"/api/runs/{ctx.run_id}/reset",
        json={"new_input_audio_path": "ASSETS/input/other.wav"},
    )
    assert res.status_code == 409
    assert "locked" in res.json()["detail"].lower()
    clear_active_execution()
