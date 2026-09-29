from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from interview_mux.config import repo_root as real_repo_root
from interview_mux.gui_session import set_active_execution
from interview_mux.web.server import create_app

# _seed_assets supplies its own INTERVIEW_MUX_ROOT; the asset paths asserted here
# are relative to that root, so the conftest redirect must stay out of the way.
pytestmark = pytest.mark.real_executions_root


def _seed_assets(tmp_path, monkeypatch) -> TestClient:
    from run_fixtures import copy_shipped_config
    copy_shipped_config(tmp_path)
    monkeypatch.setenv("INTERVIEW_MUX_ROOT", str(tmp_path))

    assets = tmp_path / "ASSETS"
    (assets / "input").mkdir(parents=True)
    (assets / "executions" / "exec_bad").mkdir(parents=True)
    (assets / "baba1_Vocals.wav").write_bytes(b"RIFF")
    (assets / "input" / "interview.wav").write_bytes(b"RIFF")
    (assets / "input" / "interview.mp3").write_bytes(b"fake-mp3")
    (assets / "executions" / "exec_bad" / "ingest.wav").write_bytes(b"RIFF")

    return TestClient(create_app())


def test_list_assets_excludes_executions_and_gui(tmp_path, monkeypatch) -> None:
    client = _seed_assets(tmp_path, monkeypatch)
    res = client.get("/api/assets")
    assert res.status_code == 200
    body = res.json()
    paths = {f["path"] for f in body["files"]}
    assert body["assets_root"] == "ASSETS/input"
    assert paths == {"ASSETS/input/interview.wav", "ASSETS/input/interview.mp3"}
    assert not any("executions" in p for p in paths)
    assert not any("baba1_Vocals" in p for p in paths)


def test_list_assets_ignores_recursive_request_outside_input_drop_zone(tmp_path, monkeypatch) -> None:
    client = _seed_assets(tmp_path, monkeypatch)
    res = client.get("/api/assets?recursive=1")
    assert res.status_code == 200
    paths = {f["path"] for f in res.json()["files"]}
    assert "ASSETS/input/interview.wav" in paths
    assert "ASSETS/input/interview.mp3" in paths
    assert "ASSETS/baba1_Vocals.wav" not in paths
    assert not any("executions" in p for p in paths)


def test_create_run_rejects_audio_outside_input_drop_zone(tmp_path, monkeypatch) -> None:
    client = _seed_assets(tmp_path, monkeypatch)

    res = client.post("/api/runs", json={"input_audio_path": "ASSETS/baba1_Vocals.wav"})

    assert res.status_code == 400
    assert "ASSETS/input" in res.json()["detail"]


def test_list_runs_default_skips_stage_enrichment(tmp_path, monkeypatch) -> None:
    client = _seed_assets(tmp_path, monkeypatch)
    run_dir = tmp_path / "ASSETS" / "executions" / "exec_100_20260101T000100Z"
    run_dir.mkdir(parents=True)
    (run_dir / "run_meta.json").write_text(
        '{"execution_number": 100, "created_at": "2026-01-01T00:00:00Z"}',
        encoding="utf-8",
    )
    set_active_execution("exec_100_20260101T000100Z")

    res = client.get("/api/runs")
    assert res.status_code == 200
    runs = res.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["run_id"] == "exec_100_20260101T000100Z"
    assert "progress" not in runs[0]


def test_list_runs_session_scope_excludes_unscoped_runs(tmp_path, monkeypatch) -> None:
    client = _seed_assets(tmp_path, monkeypatch)
    run_dir = tmp_path / "ASSETS" / "executions" / "exec_100_20260101T000100Z"
    run_dir.mkdir(parents=True)
    (run_dir / "run_meta.json").write_text(
        '{"execution_number": 100, "created_at": "2026-01-01T00:00:00Z"}',
        encoding="utf-8",
    )

    res = client.get("/api/runs")
    assert res.status_code == 200
    assert res.json()["runs"] == []


def test_list_runs_all_runs_escape_hatch(tmp_path, monkeypatch) -> None:
    client = _seed_assets(tmp_path, monkeypatch)
    run_dir = tmp_path / "ASSETS" / "executions" / "exec_100_20260101T000100Z"
    run_dir.mkdir(parents=True)
    (run_dir / "run_meta.json").write_text(
        '{"execution_number": 100, "created_at": "2026-01-01T00:00:00Z"}',
        encoding="utf-8",
    )

    res = client.get("/api/runs?all_runs=1")
    assert res.status_code == 200
    run_ids = {r["run_id"] for r in res.json()["runs"]}
    assert "exec_100_20260101T000100Z" in run_ids


def test_list_runs_enrich_includes_journey_fields(tmp_path, monkeypatch) -> None:
    client = _seed_assets(tmp_path, monkeypatch)
    run_dir = tmp_path / "ASSETS" / "executions" / "exec_101_20260101T000200Z"
    run_dir.mkdir(parents=True)
    (run_dir / "run_meta.json").write_text(
        '{"execution_number": 101, "created_at": "2026-01-01T00:02:00Z", "operator_phase": "prepare"}',
        encoding="utf-8",
    )
    set_active_execution("exec_101_20260101T000200Z")

    res = client.get("/api/runs?enrich=1")
    assert res.status_code == 200
    runs = res.json()["runs"]
    assert len(runs) == 1
    row = runs[0]
    assert row["run_id"] == "exec_101_20260101T000200Z"
    assert "operator_phase" in row
    assert "next_action" in row
    assert "attention_count" in row


def test_list_assets_survives_corrupt_run_summary(tmp_path, monkeypatch) -> None:
    client = _seed_assets(tmp_path, monkeypatch)
    bad_run = tmp_path / "ASSETS" / "executions" / "exec_099_20260101T000099Z"
    bad_run.mkdir(parents=True)
    (bad_run / "run_meta.json").write_text("{not json", encoding="utf-8")

    assets_res = client.get("/api/assets")
    runs_res = client.get("/api/runs?all_runs=1")
    assert assets_res.status_code == 200
    assert runs_res.status_code == 200
    assert len(assets_res.json()["files"]) == 2
    run_ids = {r["run_id"] for r in runs_res.json()["runs"]}
    assert "exec_099_20260101T000099Z" in run_ids
