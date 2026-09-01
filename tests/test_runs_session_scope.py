"""Session-scoped runs API — active + immediate previous only."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from interview_mux.gui_session import set_active_execution
from interview_mux.run_context import RunContext
from interview_mux.web.server import create_app
from run_fixtures import init_run_meta_for_test, patch_executions_root, patch_server_ctx


def test_session_scope_returns_active_and_previous(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    prior = RunContext("exec_100_20260101T000100Z", create=True)
    current = RunContext("exec_101_20260101T000101Z", create=True)
    init_run_meta_for_test(prior)
    init_run_meta_for_test(current)
    current.mutate_run_meta(
        lambda m: m.update(
            {
                "execution_number": 101,
                "immediate_previous_run_id": prior.run_id,
            }
        )
    )
    prior.mutate_run_meta(lambda m: m.update({"execution_number": 100}))
    set_active_execution(current.run_id)
    patch_server_ctx(monkeypatch, current)

    client = TestClient(create_app())
    res = client.get("/api/runs/session-scope")
    assert res.status_code == 200
    body = res.json()
    assert body["active_run_id"] == current.run_id
    assert body["immediate_previous_run_id"] == prior.run_id
    assert len(body["runs"]) == 2
    run_ids = {r["run_id"] for r in body["runs"]}
    assert run_ids == {prior.run_id, current.run_id}


def test_session_scope_empty_without_active_run(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    orphan = RunContext("exec_200_20260101T000200Z", create=True)
    init_run_meta_for_test(orphan)
    patch_server_ctx(monkeypatch, orphan)

    client = TestClient(create_app())
    res = client.get("/api/runs/session-scope")
    assert res.status_code == 200
    body = res.json()
    assert body["active_run_id"] is None
    assert body["runs"] == []
