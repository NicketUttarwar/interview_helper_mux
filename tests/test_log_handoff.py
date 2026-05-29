"""Structured handoff logging."""

from __future__ import annotations

import json

from interview_mux.run_context import RunContext
from interview_mux.session_log import read_log


def test_log_handoff_writes_json_detail(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ASSETS" / "executions").mkdir(parents=True)
    ctx = RunContext(create=True)
    ctx.path("understanding/speakers.json").parent.mkdir(parents=True, exist_ok=True)
    ctx.path("understanding/speakers.json").write_text("{}", encoding="utf-8")
    ctx.log_handoff("speaker_roles", ["understanding/speakers.json"], audit_path=None)
    entries = read_log(ctx.run_dir)
    assert entries
    last = entries[-1]
    assert last["level"] == "success"
    detail = json.loads(last["detail"])
    assert "understanding/speakers.json" in detail["handoff"]
