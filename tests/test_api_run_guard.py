"""HTTP 409 run_busy when operator mutations race background jobs."""

from __future__ import annotations

from fastapi.testclient import TestClient

from interview_mux.run_context import RunContext
from interview_mux.web import server
from interview_mux.web.server import create_app
from run_fixtures import init_run_meta_for_test, patch_executions_root, patch_server_ctx


def test_guarded_route_returns_409_run_busy(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_guard_api_20260101T001000Z", create=True)
    init_run_meta_for_test(ctx)
    patch_server_ctx(monkeypatch, ctx)

    runner = server.runner
    assert runner._acquire_thread_lock(ctx.run_id)
    try:
        client = TestClient(create_app(), raise_server_exceptions=False)
        res = client.put(
            f"/api/runs/{ctx.run_id}/artifact",
            json={"path": "run_meta.json", "data": {"execution_id": ctx.run_id}},
        )
        assert res.status_code == 409
        body = res.json()
        detail = body.get("detail")
        if isinstance(detail, dict):
            assert detail.get("error") == "run_busy"
        elif detail is not None:
            assert "busy" in str(detail).lower()
    finally:
        lock = runner._lock_for(ctx.run_id)
        runner._release_thread_lock(ctx.run_id, lock)


def test_execute_returns_structured_run_busy(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_guard_exec_20260101T001001Z", create=True)
    init_run_meta_for_test(ctx)
    patch_server_ctx(monkeypatch, ctx)

    runner = server.runner
    assert runner._acquire_thread_lock(ctx.run_id)
    try:
        client = TestClient(create_app(), raise_server_exceptions=False)
        res = client.post(
            f"/api/runs/{ctx.run_id}/execute",
            json={"mode": "stage", "stage": "ingest"},
        )
        assert res.status_code == 409
        body = res.json()
        detail = body.get("detail")
        if isinstance(detail, dict):
            assert detail.get("error") == "run_busy"
    finally:
        lock = runner._lock_for(ctx.run_id)
        runner._release_thread_lock(ctx.run_id, lock)
