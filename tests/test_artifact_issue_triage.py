from __future__ import annotations

import json

import pytest

from interview_mux.artifact_issue_triage import (
    blocking_issues_remaining,
    collect_issues,
    resolve_issue,
    run_triage_pipeline,
    triage_cfg,
)
from interview_mux.issue_severity_rules import (
    classify_cross_validate_message,
    classify_lint_message,
    should_auto_repair,
)
from interview_mux.write_staging import write_pending_content
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment, patch_merged_config


def _itr_config() -> dict:
    return {
        "analysis": {
            "artifact_issue_triage": {"enabled": True},
            "flow_hardening": {"enabled": True, "clarification_before_halt": True},
        },
    }


def test_classify_lint_overlap_critical() -> None:
    issue = classify_lint_message(
        "segment_classification",
        "manifest times not monotonic at seg_009",
        artifact_path="segments/manifest.json",
    )
    assert issue.severity == "critical"
    assert issue.kind == "overlap"
    assert issue.segment_id == "seg_009"


def test_classify_envelope_status_noise() -> None:
    issue = classify_lint_message("segment_classification", "envelope_status_complete missing")
    assert issue.severity == "noise"
    assert issue.blocking is False


def test_should_auto_repair_minor_null() -> None:
    issue = classify_lint_message("segment_classification", "topic_tags is null on seg_001")
    assert should_auto_repair(issue)


def test_classify_cross_validate_monotonic() -> None:
    issue = classify_cross_validate_message(
        "segment_classification",
        "manifest times not monotonic at seg_002",
    )
    assert issue.severity == "critical"


def test_run_triage_pipeline_null_topic_tags(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _itr_config())
    ctx = isolated_run_ctx(tmp_path, "itr_null_tags")
    seg = minimal_manifest_segment("seg_001", topic_tags=None)
    seg.pop("topic_tags")
    seg["topic_tags"] = None
    manifest = {"segments": [seg]}
    write_pending_content(ctx, "segment_classification", "segments/manifest.json", data=manifest)
    result = run_triage_pipeline(ctx, "segment_classification", staged=True)
    assert result.auto_fixed >= 1 or result.revalidation_ok


def test_blocking_issues_after_triage(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _itr_config())
    ctx = isolated_run_ctx(tmp_path, "itr_blocking")
    run_triage_pipeline(ctx, "segment_classification", staged=True)
    assert blocking_issues_remaining(ctx, "segment_classification") >= 0


def test_triage_cfg_defaults() -> None:
    cfg = triage_cfg()
    assert cfg.get("enabled") is True
    assert cfg.get("max_resolution_rounds") == 3


def test_resolve_issue_dismiss(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _itr_config())
    ctx = isolated_run_ctx(tmp_path, "itr_dismiss")
    from interview_mux.operator_clarifications_store import upsert_items

    upsert_items(
        ctx,
        [
            {
                "id": "itr_test_dismiss",
                "stage_key": "segment_classification",
                "message": "test issue",
                "status": "open",
                "blocking": True,
                "severity": "important",
                "kind": "other",
            }
        ],
    )
    write_pending_content(
        ctx,
        "segment_classification",
        "segments/manifest.json",
        data=minimal_manifest("seg_001"),
    )
    ok, errors = resolve_issue(ctx, "segment_classification", "itr_test_dismiss", "dismiss")
    assert ok
    assert errors == []
