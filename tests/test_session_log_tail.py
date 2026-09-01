"""Efficient tail reads for gui_log.jsonl."""

from __future__ import annotations

import json

from interview_mux.run_context import RunContext
from interview_mux.session_log import append_log, read_log
from run_fixtures import init_run_meta_for_test, patch_executions_root


def test_read_log_tail_returns_last_lines_without_full_scan(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_log_tail", create=True)
    init_run_meta_for_test(ctx)
    for i in range(200):
        append_log(ctx.run_dir, f"line-{i}", level="info")

    entries = read_log(ctx.run_dir, tail=5)
    assert len(entries) == 5
    assert entries[-1]["message"] == "line-199"
    assert entries[0]["message"] == "line-195"


def test_read_log_tail_handles_large_file(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_log_big", create=True)
    init_run_meta_for_test(ctx)
    path = ctx.run_dir / "gui_log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for i in range(5000):
            f.write(json.dumps({"ts": f"t{i}", "level": "info", "message": f"m{i}"}) + "\n")

    entries = read_log(ctx.run_dir, tail=3)
    assert [e["message"] for e in entries] == ["m4997", "m4998", "m4999"]
