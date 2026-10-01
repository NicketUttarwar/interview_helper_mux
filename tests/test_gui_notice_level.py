"""Browser notices never land at error level in the run log (ISSUES 108)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from run_fixtures import init_run_meta_for_test, patch_executions_root, patch_server_ctx

from interview_mux.run_context import RunContext
from interview_mux.web.server import create_app


def test_a_gui_error_notice_is_recorded_as_a_warning(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_gui_notice_20260101T001000Z", create=True)
    init_run_meta_for_test(ctx)
    patch_server_ctx(monkeypatch, ctx)
    client = TestClient(create_app(), raise_server_exceptions=False)

    res = client.post(
        f"/api/runs/{ctx.run_id}/log",
        json={"message": "Refresh run: Failed to fetch", "level": "error", "stage": "mix", "action_id": "gui.notice"},
    )
    assert res.status_code == 200, res.text
    rows = [
        json.loads(line)
        for line in (ctx.run_dir / "gui_log.jsonl").read_text(encoding="utf-8").splitlines()
        if "Failed to fetch" in line
    ]
    assert rows and rows[-1]["level"] == "warning"
    detail = rows[-1].get("detail")
    detail = json.loads(detail) if isinstance(detail, str) else detail
    assert detail.get("gui_level") == "error" and detail.get("origin") == "gui"
