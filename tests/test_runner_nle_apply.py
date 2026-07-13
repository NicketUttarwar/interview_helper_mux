from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.web.runner import JobRunner
from run_fixtures import init_run_meta_for_test, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run_id = "exec_nle_apply"
    c = RunContext(run_id, create=True)
    init_run_meta_for_test(c)
    c.write_json(
        "segments/nle_edits.json",
        {
            "segment_overrides": {"seg_a": {"start_ms": 100, "end_ms": 4000}},
        },
    )
    return c


def test_nle_apply_stages_trim_only(ctx: RunContext) -> None:
    runner = JobRunner()
    stages = runner._nle_apply_stages(ctx, full_refresh=False)
    assert stages == ["edl", "assembly_preview"]


def test_nle_apply_stages_structural(ctx: RunContext) -> None:
    ctx.write_json(
        "segments/nle_edits.json",
        {
            "sequence_order": ["seg_b", "seg_a"],
            "segment_overrides": {"seg_a": {"excluded": True}},
        },
    )
    runner = JobRunner()
    stages = runner._nle_apply_stages(ctx, full_refresh=False)
    assert "full_master_ranking" in stages
    assert stages[-2:] == ["edl", "assembly_preview"]


def test_nle_apply_stages_empty_without_edits(ctx: RunContext) -> None:
    ctx.write_json("segments/nle_edits.json", {"playhead_ms": 0})
    runner = JobRunner()
    assert runner._nle_apply_stages(ctx, full_refresh=False) == []


def test_nle_apply_stages_trim_only_mode_skips_ranking(ctx: RunContext) -> None:
    ctx.write_json(
        "segments/nle_edits.json",
        {
            "sequence_order": ["seg_b", "seg_a"],
            "segment_overrides": {"seg_a": {"excluded": True}},
        },
    )
    runner = JobRunner()
    stages = runner._nle_apply_stages(ctx, full_refresh=False, apply_mode="trim_only")
    assert stages == ["edl", "assembly_preview"]
    assert "full_master_ranking" not in stages


def test_nle_apply_stages_full_refresh_mode(ctx: RunContext) -> None:
    runner = JobRunner()
    stages = runner._nle_apply_stages(ctx, full_refresh=True, apply_mode="full_refresh")
    assert "transitions" in stages
    assert "edl_narrative_audit" in stages
