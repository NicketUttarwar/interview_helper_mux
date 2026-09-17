"""Stage Clinic Wave 2: disabled low_conf_island_scan must write + heal."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.stages.low_conf_fuse_stages import run_low_conf_island_scan
from run_fixtures import patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("low_conf_disabled", create=True)


def test_low_conf_disabled_writes_skip_and_marks_done(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.stages.low_conf_fuse_stages.low_conf_selection_cfg",
        lambda: {"enabled": False},
    )
    monkeypatch.setattr(
        "interview_mux.low_conf_islands.low_conf_selection_cfg",
        lambda _cfg=None: {"enabled": False},
    )
    run_low_conf_island_scan(ctx)
    assert ctx.artifact_exists("analysis/low_conf_islands.json")
    doc = ctx.read_json("analysis/low_conf_islands.json")
    assert doc.get("skip_reason") == "disabled"
    assert ctx.is_done("low_conf_island_scan")
