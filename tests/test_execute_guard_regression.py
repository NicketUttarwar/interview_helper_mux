"""Regression: execute must start jobs while guarded (not self-busy)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from interview_mux.run_context import RunContext
from interview_mux.web.server import create_app
from run_fixtures import init_run_meta_for_test, patch_executions_root


def test_execute_starts_stage_under_guard(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_guard_start_20260101T001200Z", create=True)
    init_run_meta_for_test(ctx)

    client = TestClient(create_app())
    res = client.post(
        f"/api/runs/{ctx.run_id}/execute",
        json={"mode": "stage", "stage": "audio_preclean"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True, body.get("error")
