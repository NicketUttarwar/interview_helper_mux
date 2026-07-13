from __future__ import annotations

import pytest

from interview_mux.artifact_root_cause import (
    build_recovery_actions,
    compute_stale_downstream,
    resolve_upstream_for_issue,
)
from interview_mux.issue_severity_rules import ClassifiedIssue, classify_lint_message
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment, patch_merged_config


def test_overlap_maps_to_boundary_detection() -> None:
    issue = classify_lint_message(
        "segment_classification",
        "manifest times not monotonic at seg_009",
    )
    assert resolve_upstream_for_issue(issue, "segment_classification", None) == "boundary_detection"


def test_build_recovery_actions_includes_rerun() -> None:
    issue = classify_lint_message(
        "segment_classification",
        "manifest times not monotonic at seg_009",
    )
    actions = build_recovery_actions(issue, "segment_classification", None)
    types = [a["type"] for a in actions]
    assert "apply_repair" in types
    assert "rerun_upstream" in types


def test_compute_stale_downstream_after_segment_fix(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"artifact_issue_triage": {"enabled": True}}},
    )
    ctx = isolated_run_ctx(tmp_path, "prop_plan")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_001")),
        stage_key="segment_classification",
    )
    ctx.mark_done("segment_classification", force=True)
    ctx.mark_done("content_brief_reanchor", force=True)
    plan = compute_stale_downstream(ctx, "segment_classification")
    assert plan.invalidate_from == "content_brief_reanchor"
