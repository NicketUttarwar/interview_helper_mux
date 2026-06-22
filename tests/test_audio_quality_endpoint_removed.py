from __future__ import annotations

from fastapi.testclient import TestClient

from interview_mux.gui_session import clear_active_execution
from interview_mux.run_context import RunContext
from interview_mux.web.server import create_app


def test_audio_quality_endpoint_removed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    assets = tmp_path / "ASSETS" / "input"
    assets.mkdir(parents=True)
    wav = assets / "interview.wav"
    wav.write_bytes(b"RIFF")
    ctx = RunContext("exec_001_20260101T000000Z")
    ctx.init_run_meta(str(wav.relative_to(tmp_path)))
    clear_active_execution()
    client = TestClient(create_app())
    res = client.get(f"/api/runs/{ctx.run_id}/audio-quality")
    assert res.status_code == 404
