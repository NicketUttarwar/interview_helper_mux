"""Continue at the final sign-off defers packaging to the engine that owns the run (ISSUES 99)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from run_fixtures import init_run_meta_for_test, patch_executions_root, patch_server_ctx

from interview_mux.run_context import RunContext
from interview_mux.web import server
from interview_mux.web.server import create_app


def _run(tmp_path, monkeypatch, run_id: str) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext(run_id, create=True)
    init_run_meta_for_test(ctx)
    patch_server_ctx(monkeypatch, ctx)
    return ctx


def test_continue_under_the_engine_clears_the_gate_and_starts_no_job(tmp_path, monkeypatch) -> None:
    ctx = _run(tmp_path, monkeypatch, "exec_gpub_defer_20260101T001000Z")
    monkeypatch.setattr(
        "interview_mux.orchestrator.orchestrator_owns_run",
        lambda c: {"pid": 4242, "mode": "partially-accelerated"},
    )
    started: list[dict] = []
    monkeypatch.setattr(server.runner, "start", lambda *a, **k: started.append(k) or {"ok": True})

    client = TestClient(create_app(), raise_server_exceptions=False)
    res = client.post(f"/api/runs/{ctx.run_id}/g-publish/continue")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["cleared"] is True
    assert body["started"] is False and body["deferred"] is True
    assert body["reason"] == "orchestrator_owns_run"
    assert started == []
    assert ctx.read_json("run_meta.json").get("g_publish_cleared") is True


def test_continue_without_an_engine_still_starts_the_packaging_job(tmp_path, monkeypatch) -> None:
    ctx = _run(tmp_path, monkeypatch, "exec_gpub_job_20260101T001000Z")
    monkeypatch.setattr("interview_mux.orchestrator.orchestrator_owns_run", lambda c: None)
    started: list[dict] = []
    monkeypatch.setattr(server.runner, "start", lambda *a, **k: started.append(k) or {"ok": True})

    client = TestClient(create_app(), raise_server_exceptions=False)
    res = client.post(f"/api/runs/{ctx.run_id}/g-publish/continue")

    assert res.status_code == 200, res.text
    assert res.json()["started"] is True
    assert started and started[0].get("until_stage") == "podcast_publish"
