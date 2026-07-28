"""LoudStageFailure logs to gui_log and raises."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.loud_fail import LoudStageFailure, raise_loud_failure
from interview_mux.run_context import RunContext
from interview_mux.session_log import read_log
from run_fixtures import init_run_meta_for_test, patch_executions_root


def test_raise_loud_failure_logs_and_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_loud_fail", create=True)
    init_run_meta_for_test(ctx)

    with pytest.raises(LoudStageFailure, match="broken clone"):
        raise_loud_failure(
            ctx,
            "broken clone",
            stage="g1_vo_pickup",
            reason="test_reason",
            detail={"line_id": "line_001"},
            action_id="test.loud_fail",
        )

    errors = [e for e in read_log(ctx.run_dir) if e.get("level") == "error"]
    assert len(errors) >= 1
    assert "broken clone" in errors[-1]["message"]
    assert "hard_stop" in str(errors[-1].get("detail") or "")
