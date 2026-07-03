from __future__ import annotations

import pytest

from interview_mux.operator_clarifications_store import upsert_items
from interview_mux.write_staging import (
    WriteApprovalBlockedError,
    assert_write_approval_allowed,
    is_itr_clarification_blocked,
    is_llm_gate_blocked,
    is_stage_gate_blocked,
    write_pending_content,
)
from run_fixtures import isolated_run_ctx, minimal_content_brief, minimal_manifest, patch_merged_config


def test_itr_blocks_write_approval(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "journey_ui": {"require_write_approval_per_stage": True},
            "analysis": {"artifact_issue_triage": {"enabled": True}},
        },
    )
    ctx = isolated_run_ctx(tmp_path, "itr_write_gate")
    ctx.write_json("understanding/content_brief.json", minimal_content_brief(), skip_handoff=True)
    write_pending_content(
        ctx,
        "segment_classification",
        "segments/manifest.json",
        data=minimal_manifest("seg_001"),
    )
    upsert_items(
        ctx,
        [
            {
                "id": "itr_block_save",
                "stage_key": "segment_classification",
                "message": "manifest times not monotonic at seg_002",
                "status": "open",
                "blocking": True,
                "severity": "critical",
                "kind": "overlap",
            }
        ],
    )
    ctx.write_json(
        "gui_job.json",
        {
            "status": "needs_clarification",
            "stage": "segment_classification",
            "itr_blocking_count": 1,
        },
        skip_handoff=True,
    )
    assert is_stage_gate_blocked(ctx, "segment_classification")
    assert is_itr_clarification_blocked(ctx, "segment_classification")
    assert not is_llm_gate_blocked(ctx, "segment_classification")
    with pytest.raises(WriteApprovalBlockedError, match="artifact issue"):
        assert_write_approval_allowed(ctx, "segment_classification")


def test_clarification_gate_sets_can_fix_all(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.artifact_issue_triage import set_clarification_gate
    from interview_mux.operator_clarifications_store import upsert_items

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "journey_ui": {"require_write_approval_per_stage": True, "full_autopilot": False},
            "analysis": {"artifact_issue_triage": {"enabled": True}},
        },
    )
    ctx = isolated_run_ctx(tmp_path, "itr_can_fix")
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
                    "type": "interview",
                    "proposed_split_reason": "topic_shift",
                },
            ]
        },
    )
    upsert_items(
        ctx,
        [
            {
                "id": "itr_dup",
                "stage_key": "boundary_detection",
                "message": "duplicate segment_id seg_001",
                "status": "open",
                "blocking": True,
                "severity": "critical",
                "kind": "overlap",
            }
        ],
    )
    ctx.write_json("gui_job.json", {"status": "running", "stage": "boundary_detection"}, skip_handoff=True)
    set_clarification_gate(ctx, "boundary_detection")
    job = ctx.read_json("gui_job.json")
    assert job["status"] == "running"
    assert job.get("clarification_pending") is True
    assert "can_fix_all" in job


def test_llm_gate_blocked_without_itr(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "journey_ui": {"require_write_approval_per_stage": True},
            "analysis": {"artifact_issue_triage": {"enabled": True}},
        },
    )
    ctx = isolated_run_ctx(tmp_path, "llm_gate_only")
    ctx.write_json(
        "gui_job.json",
        {
            "status": "gate",
            "stage": "boundary_detection",
            "message": "LLM stage gate (boundary_detection): adaptation loop",
        },
        skip_handoff=True,
    )
    assert is_llm_gate_blocked(ctx, "boundary_detection")
    assert not is_itr_clarification_blocked(ctx, "boundary_detection")
    assert is_stage_gate_blocked(ctx, "boundary_detection")


def test_itr_unblocks_after_resolve(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.artifact_issue_triage import resolve_issue

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "journey_ui": {"require_write_approval_per_stage": True},
            "analysis": {"artifact_issue_triage": {"enabled": True}},
        },
    )
    ctx = isolated_run_ctx(tmp_path, "itr_unblock")
    write_pending_content(
        ctx,
        "segment_classification",
        "segments/manifest.json",
        data=minimal_manifest("seg_001"),
    )
    upsert_items(
        ctx,
        [
            {
                "id": "itr_unblock_item",
                "stage_key": "segment_classification",
                "message": "minor lint noise",
                "status": "open",
                "blocking": True,
                "severity": "important",
                "kind": "other",
            }
        ],
    )
    resolve_issue(ctx, "segment_classification", "itr_unblock_item", "dismiss")
    from interview_mux.artifact_issue_triage import blocking_issues_remaining

    assert blocking_issues_remaining(ctx, "segment_classification") == 0


def test_after_stage_write_check_gates_p0_without_staged_files(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.write_staging import after_stage_write_check

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "journey_ui": {"require_write_approval_per_stage": True},
            "analysis": {"flow_hardening": {"enabled": True}},
        },
    )
    ctx = isolated_run_ctx(tmp_path, "empty_staged_gate")
    ctx.write_json("gui_job.json", {"status": "running", "stage": "boundary_detection"}, skip_handoff=True)
    with pytest.raises(SystemExit, match="no staged outputs"):
        after_stage_write_check(ctx, "boundary_detection")
    job = ctx.read_json("gui_job.json")
    assert job["status"] == "gate"
    assert job["stage"] == "boundary_detection"


def test_write_approval_allows_first_save_with_staged_boundaries_only(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pending staged files must not fail committed-only downstream cross-validation."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "journey_ui": {"require_write_approval_per_stage": True},
            "analysis": {"artifact_issue_triage": {"enabled": True}},
        },
    )
    ctx = isolated_run_ctx(tmp_path, "first_save_overlay")
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
    assert not ctx.final_path("segments", "boundaries.json").is_file()
    assert_write_approval_allowed(ctx, "boundary_detection")


def test_write_approval_allows_first_save_with_staged_manifest_only(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "journey_ui": {"require_write_approval_per_stage": True},
            "analysis": {"artifact_issue_triage": {"enabled": True}},
        },
    )
    ctx = isolated_run_ctx(tmp_path, "first_manifest_overlay")
    ctx.write_json("understanding/content_brief.json", minimal_content_brief(), skip_handoff=True)
    ctx.write_json(
        "segments/boundaries.json",
        {
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
        skip_handoff=True,
    )
    write_pending_content(
        ctx,
        "segment_classification",
        "segments/manifest.json",
        data=minimal_manifest("seg_001"),
    )
    assert not ctx.final_path("segments", "manifest.json").is_file()
    assert_write_approval_allowed(ctx, "segment_classification")

