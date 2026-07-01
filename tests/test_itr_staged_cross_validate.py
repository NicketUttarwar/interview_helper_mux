from __future__ import annotations

import json

import pytest

from interview_mux.artifact_auto_resolve import AutoResolveOutcome, auto_resolve_stage
from interview_mux.artifact_cross_validate import validate_cross_artifacts_for_stage
from interview_mux.artifact_issue_triage import (
    apply_clarification_gate_after_pause,
    blocking_issues_remaining,
    revalidate_after_repair,
    run_triage_pipeline,
    set_clarification_gate,
)
from interview_mux.operator_clarifications_store import upsert_items
from interview_mux.write_staging import write_pending_content
from run_fixtures import isolated_run_ctx, patch_merged_config


def _itr_config() -> dict:
    return {
        "analysis": {
            "artifact_issue_triage": {"enabled": True, "max_auto_resolve_attempts_per_stage": 1},
            "flow_hardening": {"enabled": True},
        },
        "journey_ui": {"require_write_approval_per_stage": True},
    }


def test_staged_cross_validate_uses_staged_boundaries(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _itr_config())
    ctx = isolated_run_ctx(tmp_path, "staged_cv")
    boundaries_path = ctx.path("segments", "boundaries.json")
    boundaries_path.parent.mkdir(parents=True, exist_ok=True)
    boundaries_path.write_text(
        json.dumps(
            {
                "boundaries": [
                    {
                        "segment_id": "seg_001",
                        "start_ms": 0,
                        "end_ms": 1000,
                        "speaker_id": "spk_1",
                        "proposed_split_reason": "topic_shift",
                    },
                    {
                        "segment_id": "seg_003",
                        "start_ms": 1000,
                        "end_ms": 2000,
                        "proposed_split_reason": "topic_shift",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    write_pending_content(
        ctx,
        "boundary_detection",
        "segments/boundaries.json",
        data={
            "boundaries": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 2000,
                    "speaker_id": "spk_1",
                    "proposed_split_reason": "topic_shift",
                },
            ]
        },
    )
    committed_errors = validate_cross_artifacts_for_stage(ctx, "boundary_detection", staged=False)
    staged_errors = validate_cross_artifacts_for_stage(ctx, "boundary_detection", staged=True)
    assert committed_errors
    assert staged_errors == []

    ok, repair_errors = revalidate_after_repair(ctx, "boundary_detection", staged=True)
    assert ok, repair_errors


def test_set_clarification_gate_defers_while_running(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _itr_config())
    ctx = isolated_run_ctx(tmp_path, "defer_gate")
    upsert_items(
        ctx,
        [
            {
                "id": "itr_gate",
                "stage_key": "boundary_detection",
                "message": "boundary seg_003 missing speaker_id",
                "status": "open",
                "blocking": True,
                "segment_id": "seg_003",
            }
        ],
    )
    ctx.write_json("gui_job.json", {"status": "running", "stage": "boundary_detection"}, skip_handoff=True)
    set_clarification_gate(ctx, "boundary_detection")
    job = ctx.read_json("gui_job.json")
    assert job["status"] == "running"
    assert job.get("clarification_pending") is True
    assert job.get("itr_blocking_count") == 1

    assert apply_clarification_gate_after_pause(ctx, "boundary_detection")
    job = ctx.read_json("gui_job.json")
    assert job["status"] == "needs_clarification"
    assert "clarification_pending" not in job


def test_auto_resolve_delete_segment_clears_staged_issue(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _itr_config())
    ctx = isolated_run_ctx(tmp_path, "auto_del")
    write_pending_content(
        ctx,
        "boundary_detection",
        "segments/boundaries.json",
        data={
            "boundaries": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "speaker_id": "spk_1",
                    "proposed_split_reason": "topic_shift",
                },
                {
                    "segment_id": "seg_003",
                    "start_ms": 1000,
                    "end_ms": 2000,
                    "proposed_split_reason": "topic_shift",
                },
            ]
        },
    )
    run_triage_pipeline(ctx, "boundary_detection", staged=True)
    upsert_items(
        ctx,
        [
            {
                "id": "itr_del",
                "stage_key": "boundary_detection",
                "message": "boundary seg_003 missing speaker_id",
                "status": "open",
                "blocking": True,
                "segment_id": "seg_003",
                "kind": "cross_validate",
                "options": [
                    {
                        "value": "delete_segment",
                        "label": "Delete missing segment",
                        "confidence": 1.0,
                        "reason": "Missing speaker_id in boundary seg_003",
                    }
                ],
            }
        ],
    )
    assert blocking_issues_remaining(ctx, "boundary_detection") >= 1

    result = auto_resolve_stage(ctx, "boundary_detection")
    assert result.outcome == AutoResolveOutcome.SUCCESS
    assert blocking_issues_remaining(ctx, "boundary_detection") == 0
    ok, errors = revalidate_after_repair(ctx, "boundary_detection", staged=True)
    assert ok, errors


def test_escape_hatch_on_retry_cap(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "artifact_issue_triage": {
                    "enabled": True,
                    "max_auto_resolve_attempts_per_stage": 1,
                    "auto_resolve_min_confidence": 0.99,
                },
                "flow_hardening": {"enabled": True},
            },
            "journey_ui": {"require_write_approval_per_stage": True},
        },
    )
    ctx = isolated_run_ctx(tmp_path, "escape_cap")
    write_pending_content(
        ctx,
        "boundary_detection",
        "segments/boundaries.json",
        data={
            "boundaries": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "speaker_id": "spk_1",
                    "proposed_split_reason": "topic_shift",
                },
                {
                    "segment_id": "seg_003",
                    "start_ms": 1000,
                    "end_ms": 2000,
                    "proposed_split_reason": "topic_shift",
                },
            ]
        },
    )
    upsert_items(
        ctx,
        [
            {
                "id": "itr_stuck",
                "stage_key": "boundary_detection",
                "message": "boundary seg_003 missing speaker_id",
                "status": "open",
                "blocking": True,
                "segment_id": "seg_003",
                "kind": "cross_validate",
                "options": [{"value": "aside", "confidence": 0.4}],
            }
        ],
    )
    ctx.write_json(
        "understanding/analysis_orchestration.json",
        {
            "itr_auto_resolve_attempts_boundary_detection": 1,
            "itr_auto_resolve_signature_boundary_detection": "deadbeef",
        },
        skip_handoff=True,
    )

    result = auto_resolve_stage(ctx, "boundary_detection")
    assert result.outcome == AutoResolveOutcome.SUCCESS
    assert any("escape" in w.lower() for w in result.warnings)
    ok, errors = revalidate_after_repair(ctx, "boundary_detection", staged=True)
    assert ok, errors
    assert blocking_issues_remaining(ctx, "boundary_detection") == 0


def test_autopilot_force_complete_duplicate_segment_ids(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Autopilot mode repairs duplicate ids and missing speaker_id without operator clicks."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _itr_config())
    ctx = isolated_run_ctx(tmp_path, "autopilot_dup")
    ctx.write_json(
        "understanding/speakers.json",
        {"speakers": [{"speaker_id": "spk_1", "role": "interviewer", "confidence": 0.9}]},
        skip_handoff=True,
    )
    write_pending_content(
        ctx,
        "boundary_detection",
        "segments/boundaries.json",
        data={
            "boundaries": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "proposed_split_reason": "topic_shift",
                },
                {
                    "segment_id": "seg_001",
                    "start_ms": 1000,
                    "end_ms": 2000,
                    "speaker_id": "spk_1",
                    "proposed_split_reason": "topic_shift",
                },
                {
                    "segment_id": "seg_002",
                    "start_ms": 2000,
                    "end_ms": 3000,
                    "speaker_id": "spk_1",
                    "proposed_split_reason": "topic_shift",
                },
                {
                    "segment_id": "seg_002",
                    "start_ms": 3000,
                    "end_ms": 4000,
                    "speaker_id": "spk_1",
                    "proposed_split_reason": "topic_shift",
                },
            ]
        },
    )
    run_triage_pipeline(ctx, "boundary_detection", staged=True)
    assert blocking_issues_remaining(ctx, "boundary_detection") >= 1

    result = auto_resolve_stage(ctx, "boundary_detection", autopilot=True)
    assert result.outcome == AutoResolveOutcome.SUCCESS
    assert blocking_issues_remaining(ctx, "boundary_detection") == 0
    ok, errors = revalidate_after_repair(ctx, "boundary_detection", staged=True)
    assert ok, errors
