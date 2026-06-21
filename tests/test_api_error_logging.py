"""FastAPI global exception handler and GET run last_error enrichment."""

from __future__ import annotations

from fastapi.testclient import TestClient

from interview_mux.run_context import RunContext
from interview_mux.session_log import read_log
from interview_mux.web import server
from interview_mux.web.server import create_app
from run_fixtures import init_run_meta_for_test, patch_executions_root, patch_server_ctx


def test_unhandled_api_error_appends_gui_log(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_900_20260101T000900Z", create=True)
    init_run_meta_for_test(ctx)
    patch_server_ctx(monkeypatch, ctx)

    def _boom(*_a, **_k):
        raise RuntimeError("handler boom")

    monkeypatch.setattr(server, "read_log", _boom)

    client = TestClient(create_app(), raise_server_exceptions=False)
    res = client.get(f"/api/runs/{ctx.run_id}")
    assert res.status_code == 500

    entries = read_log(ctx.run_dir, tail=10)
    assert any("API 500" in e.get("message", "") and "handler boom" in e.get("message", "") for e in entries)
    api_entry = next(e for e in entries if e.get("stage") == "api")
    assert api_entry["level"] == "error"


def test_get_run_enriches_last_error_from_job(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_901_20260101T000901Z", create=True)
    init_run_meta_for_test(ctx)
    tb = "Traceback (most recent call last):\n  RuntimeError: AWS failed\n"
    ctx.write_json(
        "gui_job.json",
        {
            "status": "error",
            "stage": "transcribe",
            "message": "AWS failed",
            "traceback": tb,
            "last_error": {
                "message": "AWS failed",
                "stage": "transcribe",
                "error_class": "RuntimeError",
                "traceback_excerpt": tb[:2000],
            },
        },
    )
    patch_server_ctx(monkeypatch, ctx)

    client = TestClient(create_app())
    payload = client.get(f"/api/runs/{ctx.run_id}").json()
    last_error = payload["job"]["last_error"]
    assert last_error["message"] == "AWS failed"
    assert last_error["stage"] == "transcribe"
    assert last_error["error_class"] == "RuntimeError"
    assert last_error["traceback_excerpt"] == tb[:2000]


def test_get_run_synthesizes_last_error_when_missing(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_902_20260101T000902Z", create=True)
    init_run_meta_for_test(ctx)
    ctx.write_json(
        "gui_job.json",
        {
            "status": "error",
            "stage": "ingest",
            "message": "Normalize failed",
            "traceback": "Traceback…",
        },
    )
    patch_server_ctx(monkeypatch, ctx)

    client = TestClient(create_app())
    last_error = client.get(f"/api/runs/{ctx.run_id}").json()["job"]["last_error"]
    assert last_error["message"] == "Normalize failed"
    assert last_error["stage"] == "ingest"
    assert last_error["traceback_excerpt"] == "Traceback…"
