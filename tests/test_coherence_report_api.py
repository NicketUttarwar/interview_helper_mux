from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from interview_mux.run_context import RunContext
from interview_mux.web.server import create_app
from run_fixtures import init_run_meta_for_test, patch_executions_root


def _client_with_run(tmp_path: Path, monkeypatch) -> tuple[TestClient, str]:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_coherence_api", create=True)
    init_run_meta_for_test(ctx)
    return TestClient(create_app()), ctx.run_id


def test_coherence_report_missing_returns_inactive_stub_200(
    tmp_path: Path, monkeypatch
) -> None:
    client, run_id = _client_with_run(tmp_path, monkeypatch)
    res = client.get(f"/api/runs/{run_id}/coherence-report")
    assert res.status_code == 200
    body = res.json()
    assert body["gate"]["activated"] is False
    assert body["risks"] == []
    assert body["summary"]["topic_drift_count"] == 0


def test_coherence_report_returns_persisted_document(
    tmp_path: Path, monkeypatch
) -> None:
    client, run_id = _client_with_run(tmp_path, monkeypatch)
    ctx = RunContext(run_id)
    doc = {
        "schema_version": 1,
        "gate": {"activated": True, "duration_ms": 1_800_000},
        "risks": [{"risk_id": "r1", "kind": "drift", "status": "open"}],
        "summary": {
            "topic_drift_count": 1,
            "claim_contradiction_count": 0,
            "missing_callback_count": 0,
        },
    }
    ctx.write_json("understanding/coherence_report.json", doc)
    res = client.get(f"/api/runs/{run_id}/coherence-report")
    assert res.status_code == 200
    assert res.json()["risks"][0]["risk_id"] == "r1"
