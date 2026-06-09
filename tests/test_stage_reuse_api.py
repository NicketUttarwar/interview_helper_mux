"""HTTP API for stage execution reuse offers."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.web.server import create_app
from run_fixtures import init_run_meta_for_test, patch_executions_root, patch_server_ctx


def _patch_executions_root(monkeypatch, tmp_path: Path) -> None:
    journey = dict(merged_config().get("journey_ui") or {})
    journey["require_write_approval_per_stage"] = False
    patch_executions_root(monkeypatch, tmp_path, journey_ui=journey)


def _setup_pair(tmp_path: Path) -> tuple:
    prior = RunContext("exec_100_20260101T000100Z", create=True)
    current = RunContext("exec_101_20260101T000101Z", create=True)
    init_run_meta_for_test(prior)
    init_run_meta_for_test(current)
    prior.write_json("transcript/full.json", {"segments": []})
    prior.write_json("transcript/speakers.json", {"speakers": []})
    prior.mark_done("transcribe")
    return prior, current


def test_reuse_offers_api(tmp_path: Path, monkeypatch) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    _, current = _setup_pair(tmp_path)
    patch_server_ctx(monkeypatch, current)
    client = TestClient(create_app())
    res = client.get("/api/runs/exec_101_20260101T000101Z/stages/transcribe/reuse-offers")
    assert res.status_code == 200
    body = res.json()
    assert body["eligible"] is True
    assert body["candidates"][0]["run_id"] == "exec_100_20260101T000100Z"


def test_reuse_accept_api(tmp_path: Path, monkeypatch) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    _, current = _setup_pair(tmp_path)
    patch_server_ctx(monkeypatch, current)
    client = TestClient(create_app())
    res = client.post(
        "/api/runs/exec_101_20260101T000101Z/stages/transcribe/reuse",
        json={"action": "accept", "source_run_id": "exec_100_20260101T000100Z"},
    )
    assert res.status_code == 200
    assert res.json()["stage_done"] is True
    assert current.is_done("transcribe")


def test_reuse_decline_api(tmp_path: Path, monkeypatch) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    _, current = _setup_pair(tmp_path)
    patch_server_ctx(monkeypatch, current)
    client = TestClient(create_app())
    res = client.post(
        "/api/runs/exec_101_20260101T000101Z/stages/transcribe/reuse",
        json={"action": "decline"},
    )
    assert res.status_code == 200
    meta = current.read_json("run_meta.json")
    assert meta["stage_reuse"]["transcribe"]["action"] == "decline"


def test_stage_list_awaiting_write_approval_status(tmp_path: Path, monkeypatch) -> None:
    journey = dict(merged_config().get("journey_ui") or {})
    journey["require_write_approval_per_stage"] = True
    patch_executions_root(monkeypatch, tmp_path, journey_ui=journey)
    current = RunContext("exec_101_20260101T000101Z", create=True)
    init_run_meta_for_test(current)
    patch_server_ctx(monkeypatch, current)
    from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

    enter_stage_staging("ingest")
    note = current.path("ingest/checksums.json")
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("{}", encoding="utf-8")
    exit_stage_staging()
    client = TestClient(create_app())
    res = client.get("/api/runs/exec_101_20260101T000101Z")
    assert res.status_code == 200
    stages = res.json()["stages"]
    ingest = next(s for s in stages if s["id"] == "ingest")
    assert ingest["status"] == "awaiting_write_approval"


def test_reuse_accept_invalid_source(tmp_path: Path, monkeypatch) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    _, current = _setup_pair(tmp_path)
    patch_server_ctx(monkeypatch, current)
    client = TestClient(create_app())
    res = client.post(
        "/api/runs/exec_101_20260101T000101Z/stages/transcribe/reuse",
        json={"action": "accept", "source_run_id": "exec_999_20260101T999999Z"},
    )
    assert res.status_code == 404
