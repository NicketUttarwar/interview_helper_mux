from __future__ import annotations

import shutil

from fastapi.testclient import TestClient

from interview_mux.config import repo_root as real_repo_root
from interview_mux.web.server import create_app


def _seed_assets(tmp_path, monkeypatch) -> TestClient:
    shutil.copytree(real_repo_root() / "config", tmp_path / "config")
    monkeypatch.setenv("INTERVIEW_MUX_ROOT", str(tmp_path))

    assets = tmp_path / "ASSETS"
    (assets / "input").mkdir(parents=True)
    (assets / "executions" / "exec_bad").mkdir(parents=True)
    (assets / "baba1_Vocals.wav").write_bytes(b"RIFF")
    (assets / "input" / "interview.wav").write_bytes(b"RIFF")
    (assets / "executions" / "exec_bad" / "ingest.wav").write_bytes(b"RIFF")

    return TestClient(create_app())


def test_list_assets_excludes_executions_and_gui(tmp_path, monkeypatch) -> None:
    client = _seed_assets(tmp_path, monkeypatch)
    res = client.get("/api/assets")
    assert res.status_code == 200
    body = res.json()
    paths = {f["path"] for f in body["files"]}
    assert paths == {"ASSETS/baba1_Vocals.wav"}
    assert not any("executions" in p for p in paths)
    assert not any("/input/" in p for p in paths)


def test_list_assets_recursive_includes_subfolders(tmp_path, monkeypatch) -> None:
    client = _seed_assets(tmp_path, monkeypatch)
    res = client.get("/api/assets?recursive=1")
    assert res.status_code == 200
    paths = {f["path"] for f in res.json()["files"]}
    assert "ASSETS/baba1_Vocals.wav" in paths
    assert "ASSETS/input/interview.wav" in paths
    assert not any("executions" in p for p in paths)


def test_list_runs_default_skips_stage_enrichment(tmp_path, monkeypatch) -> None:
    client = _seed_assets(tmp_path, monkeypatch)
    run_dir = tmp_path / "ASSETS" / "executions" / "exec_100_20260101T000100Z"
    run_dir.mkdir(parents=True)
    (run_dir / "run_meta.json").write_text(
        '{"execution_number": 100, "created_at": "2026-01-01T00:00:00Z"}',
        encoding="utf-8",
    )

    res = client.get("/api/runs")
    assert res.status_code == 200
    runs = res.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["run_id"] == "exec_100_20260101T000100Z"
    assert "progress" not in runs[0]


def test_list_runs_enrich_includes_journey_fields(tmp_path, monkeypatch) -> None:
    client = _seed_assets(tmp_path, monkeypatch)
    run_dir = tmp_path / "ASSETS" / "executions" / "exec_101_20260101T000200Z"
    run_dir.mkdir(parents=True)
    (run_dir / "run_meta.json").write_text(
        '{"execution_number": 101, "created_at": "2026-01-01T00:02:00Z", "operator_phase": "prepare"}',
        encoding="utf-8",
    )

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
    runs_res = client.get("/api/runs")
    assert assets_res.status_code == 200
    assert runs_res.status_code == 200
    assert len(assets_res.json()["files"]) == 1
    run_ids = {r["run_id"] for r in runs_res.json()["runs"]}
    assert "exec_099_20260101T000099Z" in run_ids
