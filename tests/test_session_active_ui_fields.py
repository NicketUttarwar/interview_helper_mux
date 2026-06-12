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


def test_active_tab_and_pipeline_sub_tab_round_trip(tmp_path, monkeypatch) -> None:
    client, run_id = _client_with_run(tmp_path, monkeypatch)
    res = client.put(
        "/api/session/active",
        json={
            "run_id": run_id,
            "selected_stage_id": "transcribe",
            "active_tab": "logs",
            "pipeline_sub_tab": "timeline",
        },
    )
    assert res.status_code == 200
    active = res.json()
    assert active["active_tab"] == "logs"
    assert active["pipeline_sub_tab"] == "timeline"
    assert active["selected_stage_id"] == "transcribe"

    session = client.get("/api/session").json()
    assert session["active"]["active_tab"] == "logs"
    assert session["active"]["pipeline_sub_tab"] == "timeline"


def test_merge_partial_ui_update_preserves_run_id(tmp_path, monkeypatch) -> None:
    client, run_id = _client_with_run(tmp_path, monkeypatch)
    client.put(
        "/api/session/active",
        json={"run_id": run_id, "active_tab": "pipeline"},
    )
    res = client.put(
        "/api/session/active",
        json={"selected_stage_id": "ingest", "active_tab": "pipeline", "pipeline_sub_tab": "stage"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["run_id"] == run_id
    assert body["selected_stage_id"] == "ingest"


def test_activity_log_tab_and_collapsed_round_trip(tmp_path, monkeypatch) -> None:
    client, run_id = _client_with_run(tmp_path, monkeypatch)
    res = client.put(
        "/api/session/active",
        json={
            "run_id": run_id,
            "activity_log_tab": "step",
            "activity_log_collapsed": True,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["activity_log_tab"] == "step"
    assert body["activity_log_collapsed"] is True

    session = client.get("/api/session").json()
    assert session["active"]["activity_log_tab"] == "step"
    assert session["active"]["activity_log_collapsed"] is True


def test_invalid_activity_log_tab_rejected(tmp_path, monkeypatch) -> None:
    client, run_id = _client_with_run(tmp_path, monkeypatch)
    res = client.put(
        "/api/session/active",
        json={"run_id": run_id, "activity_log_tab": "invalid"},
    )
    assert res.status_code == 400
