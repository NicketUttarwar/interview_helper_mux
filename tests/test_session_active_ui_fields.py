from __future__ import annotations

from fastapi.testclient import TestClient

from interview_mux.gui_session import clear_active_execution
from interview_mux.run_context import RunContext
from interview_mux.web.server import create_app


def _client_with_run(tmp_path, monkeypatch) -> tuple[TestClient, str]:
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    assets = tmp_path / "ASSETS" / "input"
    assets.mkdir(parents=True)
    wav = assets / "interview.wav"
    wav.write_bytes(b"RIFF")
    ctx = RunContext("exec_020_20260101T000020Z")
    ctx.init_run_meta(str(wav.relative_to(tmp_path)))
    clear_active_execution()
    return TestClient(create_app()), ctx.run_id


def test_active_body_pipeline_prefs_round_trip(tmp_path, monkeypatch) -> None:
    client, run_id = _client_with_run(tmp_path, monkeypatch)
    res = client.put(
        "/api/session/active",
        json={
            "run_id": run_id,
            "pipeline_collapsed_stages": ["ingest", "transcribe"],
            "pipeline_expanded_done_stages": ["audio_preclean"],
            "pipeline_filter_needs_you": True,
            "source_locked": True,
            "input_audio_path": "ASSETS/input/interview.wav",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["pipeline_collapsed_stages"] == ["ingest", "transcribe"]
    assert body["pipeline_expanded_done_stages"] == ["audio_preclean"]
    assert body["pipeline_filter_needs_you"] is True

    session = client.get("/api/session").json()
    active = session["active"]
    assert active["pipeline_collapsed_stages"] == ["ingest", "transcribe"]
    assert active["source_locked"] is True or session.get("source", {}).get("source_locked")


def test_get_session_includes_working_dir(tmp_path, monkeypatch) -> None:
    client, run_id = _client_with_run(tmp_path, monkeypatch)
    client.put("/api/session/active", json={"run_id": run_id})
    session = client.get("/api/session").json()
    summary = session.get("run_summary") or {}
    assert summary.get("run_id") == run_id
    assert "working_dir" in summary
    run = client.get(f"/api/runs/{run_id}").json()
    assert "working_dir" in run
    assert run["working_dir"]
