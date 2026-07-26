from __future__ import annotations

import pytest

from interview_mux.artifact_auto_resolve import (
    AutoResolveOutcome,
    auto_resolve_stage,
    blocking_issues_remaining,
    can_auto_resolve_issue,
    get_stage_issues_summary,
    pick_recommended_choice,
    run_triage_pipeline,
    stage_capabilities,
)
from interview_mux.operator_clarifications_store import upsert_items
from interview_mux.write_staging import write_pending_content
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment, patch_merged_config


def _itr_config() -> dict:
    return {
        "analysis": {
            "artifact_issue_triage": {"enabled": True},
            "flow_hardening": {"enabled": True},
        },
    }


def test_pick_recommended_choice_confidence_gate() -> None:
    item = {
        "status": "open",
        "blocking": True,
        "options": [
            {"value": "interview", "confidence": 0.9},
            {"value": "aside", "confidence": 0.5},
        ],
    }
    assert pick_recommended_choice(item) == "interview"


def test_pick_recommended_choice_low_confidence() -> None:
    item = {
        "status": "open",
        "blocking": True,
        "options": [
            {"value": "interview", "confidence": 0.5},
            {"value": "aside", "confidence": 0.48},
        ],
    }
    assert pick_recommended_choice(item) is None


def test_can_auto_resolve_issue_merge_overlap() -> None:
    item = {
        "status": "open",
        "blocking": True,
        "repair_strategy": "merge_overlap",
        "options": [],
    }
    assert can_auto_resolve_issue(item)


def test_stage_capabilities_boundary_full_tier() -> None:
    caps = stage_capabilities("boundary_detection")
    assert caps["tier"] == "full"
    assert caps["step_label"] == "Fix all & continue"


def test_auto_resolve_idempotent_when_clear(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _itr_config())
    ctx = isolated_run_ctx(tmp_path, "itr_idempotent")
    seg = minimal_manifest_segment("seg_001")
    manifest = minimal_manifest([seg])
    write_pending_content(ctx, "segment_classification", "segments/manifest.json", data=manifest)
    assert blocking_issues_remaining(ctx, "segment_classification") == 0
    result = auto_resolve_stage(ctx, "segment_classification")
    assert result.outcome == AutoResolveOutcome.SUCCESS
    assert result.can_advance_pipeline


def test_auto_resolve_applies_recommended_choice(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _itr_config())
    ctx = isolated_run_ctx(tmp_path, "itr_apply_rec")
    seg = minimal_manifest_segment("seg_001", topic_tags=None)
    seg["topic_tags"] = None
    manifest = {"segments": [seg]}
    write_pending_content(ctx, "segment_classification", "segments/manifest.json", data=manifest)
    run_triage_pipeline(ctx, "segment_classification", staged=True)
    upsert_items(
        ctx,
        [
            {
                "id": "test_issue",
                "stage_key": "segment_classification",
                "status": "open",
                "blocking": True,
                "message": "topic_tags is null on seg_001",
                "segment_id": "seg_001",
                "repair_strategy": "fill_null",
                "options": [{"value": [], "confidence": 0.95}],
            }
        ],
    )
    result = auto_resolve_stage(ctx, "segment_classification")
    assert result.resolved_count >= 0
    assert result.outcome in (AutoResolveOutcome.SUCCESS, AutoResolveOutcome.MANUAL_REQUIRED, AutoResolveOutcome.PARTIAL)


def test_stage_issues_summary_never_offers_bridge(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The lint-repair bridge is gone in v2 — summaries must never advertise it."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _itr_config())
    ctx = isolated_run_ctx(tmp_path, "itr_bridge_off")
    summary = get_stage_issues_summary(ctx, "segment_classification")
    assert summary["bridge_eligible"] is False
    assert summary["open_blocking"] == 0
