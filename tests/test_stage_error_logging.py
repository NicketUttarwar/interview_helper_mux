"""Stage wrapper logs failures to gui_log.jsonl via operator_trace."""

from __future__ import annotations

import json

import pytest

from interview_mux.run_context import RunContext
from interview_mux.session_log import read_log
from interview_mux.write_staging import run_wrapped_stage
from run_fixtures import isolated_run_ctx, patch_merged_config


def test_run_wrapped_stage_logs_stage_error(tmp_path, monkeypatch) -> None:
    patch_merged_config(monkeypatch, {"journey_ui": {"require_write_approval_per_stage": False}})
    ctx = isolated_run_ctx(tmp_path, "run_stage_err")
    ctx.write_json("run_meta.json", {"execution_id": ctx.run_id}, skip_handoff=True)

    with pytest.raises(RuntimeError, match="stage boom"):
        run_wrapped_stage(ctx, "ingest", lambda: (_ for _ in ()).throw(RuntimeError("stage boom")))

    entries = read_log(ctx.run_dir, tail=10)
    fail = next(e for e in entries if "Failed: Stage ingest" in e.get("message", ""))
    detail = json.loads(fail["detail"])
    assert detail["event"] == "substep_fail"
    assert detail["error_class"] == "RuntimeError"
    assert "stage boom" in detail["traceback"]


def test_run_wrapped_stage_success_logs_finish(tmp_path, monkeypatch) -> None:
    patch_merged_config(monkeypatch, {"journey_ui": {"require_write_approval_per_stage": False}})
    ctx = isolated_run_ctx(tmp_path, "run_stage_ok")
    ctx.write_json("run_meta.json", {"execution_id": ctx.run_id}, skip_handoff=True)

    run_wrapped_stage(ctx, "ingest", lambda: None)

    entries = read_log(ctx.run_dir, tail=10)
    messages = [e.get("message") for e in entries]
    assert "Stage finished: ingest" in messages
