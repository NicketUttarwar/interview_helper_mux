from __future__ import annotations

from fastapi.testclient import TestClient

from interview_mux.api_providers import all_provider_grants
from interview_mux.run_context import RunContext
from interview_mux.web.server import create_app
from run_fixtures import init_run_meta_for_test, patch_executions_root, patch_server_ctx


def test_session_api_consent_includes_auto_grants(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "interview_mux.web.server.load_persisted_consents",
        lambda: {},
    )
    client = TestClient(create_app())
    res = client.get("/api/session/api-consent")
    assert res.status_code == 200
    body = res.json()
    assert "openai" in {p["id"] for p in body["providers"]}
    assert body["grants"].get("openai") is True
    assert "aws" not in body["grants"]


def test_all_provider_grants_auto_true() -> None:
    grants = all_provider_grants()
    assert grants.get("openai") is True
    assert "aws" not in grants


def test_execute_not_blocked_by_consent(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_consent_20260101T001100Z", create=True)
    init_run_meta_for_test(ctx)
    patch_server_ctx(monkeypatch, ctx)

    client = TestClient(create_app())
    res = client.post(
        f"/api/runs/{ctx.run_id}/execute",
        json={"mode": "stage", "stage": "speaker_roles", "api_consents": {}},
    )
    assert res.status_code == 200
    payload = res.json()
    assert not payload.get("needs_api_consent")
