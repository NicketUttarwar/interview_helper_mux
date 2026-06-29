from __future__ import annotations

import pytest

from interview_mux.operator_clarifications_store import upsert_items
from interview_mux.write_staging import (
    WriteApprovalBlockedError,
    assert_write_approval_allowed,
    is_stage_gate_blocked,
    write_pending_content,
)
from run_fixtures import isolated_run_ctx, minimal_manifest, patch_merged_config


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
    with pytest.raises(WriteApprovalBlockedError, match="artifact issue"):
        assert_write_approval_allowed(ctx, "segment_classification")


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
