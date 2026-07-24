"""Tests for deterministic framing ranking guards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.framing_coverage_guard import enforce_framing_ranking, validate_framing_ranking
from interview_mux.gap_framing import build_gap_framing_plan, normalize_interviewer_line
from interview_mux.run_context import RunContext
from run_fixtures import init_run_meta_for_test, minimal_gap_line, minimal_manifest, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_framing_guard", create=True)
    init_run_meta_for_test(run)
    run.write_json("segments/manifest.json", minimal_manifest("seg_001", "seg_002", "seg_003"), skip_handoff=True)
    lines = [
        normalize_interviewer_line(
            {
                "line_id": "vo_sum_1",
                "line_category": "segment_summary",
                "text": "Summary of setup.",
                "targets_segment_id": "seg_002",
                "replaces_source_segments": ["seg_001"],
            },
            eligible="spk_0",
            delivery="synthesize",
        )
    ]
    plan = build_gap_framing_plan(run, lines)
    run.path("understanding").mkdir(parents=True, exist_ok=True)
    run.path("master").mkdir(parents=True, exist_ok=True)
    run.path("understanding", "gap_framing_plan.json").write_text(
        json.dumps(plan) + "\n", encoding="utf-8"
    )
    run.path("understanding", "gap_report.json").write_text(
        json.dumps({"interviewer_lines": lines}) + "\n", encoding="utf-8"
    )
    run.path("master", "coverage_audit.json").write_text(
        json.dumps({"topic_segment_map": [{"topic_id": "origins", "segment_ids": ["seg_001"]}]})
        + "\n",
        encoding="utf-8",
    )
    return run


def test_validate_blocks_primary_impact_exclusion(ctx: RunContext) -> None:
    selection = {
        "ordered_segment_ids": ["seg_002"],
        "excluded_segment_ids": [{"segment_id": "seg_002", "reason": "covered_by_framing_vo"}],
    }
    issues = validate_framing_ranking(ctx, selection)
    assert any("never_exclude_primary_impact" in i for i in issues)


def test_enforce_raises_on_primary_lock(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.config.merged_config",
        lambda: {"analysis": {"flow_hardening": {"strict_critical_stages": True}}},
    )
    selection = {
        "ordered_segment_ids": ["seg_003"],
        "excluded_segment_ids": [{"segment_id": "seg_002", "reason": "covered_by_framing_vo"}],
    }
    with pytest.raises(ValueError, match="framing_coverage_guard"):
        enforce_framing_ranking(ctx, selection)
