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


def test_ui_fields_do_not_weaken_source_lock(tmp_path, monkeypatch) -> None:
    from interview_mux.run_context import RunContext

    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    assets = tmp_path / "ASSETS" / "input"
    assets.mkdir(parents=True)
    wav = assets / "interview.wav"
    wav.write_bytes(b"RIFF")
    ctx_a = RunContext("exec_003_20260101T000003Z")
    ctx_a.init_run_meta(str(wav.relative_to(tmp_path)))
    ctx_b = RunContext("exec_004_20260101T000004Z")
    ctx_b.init_run_meta(str(wav.relative_to(tmp_path)))

    client = TestClient(create_app())
    set_active_execution(
        ctx_a.run_id,
        source_locked=True,
        active_tab="pipeline",
        pipeline_sub_tab="story",
        selected_stage_id="ingest",
    )
    res = client.put(
        "/api/session/active",
        json={
            "run_id": ctx_b.run_id,
            "active_tab": "executions",
            "pipeline_sub_tab": "stage",
        },
    )
    assert res.status_code == 409
    active = client.get("/api/session").json()["active"]
    assert active["run_id"] == ctx_a.run_id
    assert active["active_tab"] == "pipeline"
    clear_active_execution()
