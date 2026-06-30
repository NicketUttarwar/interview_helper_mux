from __future__ import annotations

import pytest

from interview_mux.adaptation_itr_bridge import BridgeOutcome, bridge_adaptation_to_itr
from interview_mux.write_staging import write_pending_content
from run_fixtures import isolated_run_ctx, patch_merged_config


def test_bridge_failed_without_staged_artifact(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"analysis": {"artifact_issue_triage": {"enabled": True}}})
    ctx = isolated_run_ctx(tmp_path, "bridge_no_staged")
    result = bridge_adaptation_to_itr(
        ctx,
        "boundary_detection",
        strategy_key="lint_retry_boundary_detection",
        lint_errors=["duplicate segment_id seg_001"],
    )
    assert result.outcome == BridgeOutcome.FAILED


def test_bridge_partial_sets_clarification_gate(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.operator_clarifications_store import upsert_items

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "journey_ui": {"require_write_approval_per_stage": True},
            "analysis": {"artifact_issue_triage": {"enabled": True}},
        },
    )
    ctx = isolated_run_ctx(tmp_path, "bridge_partial")
    write_pending_content(
        ctx,
        "boundary_detection",
        "segments/boundaries.json",
        data={
            "boundaries": [
                {"segment_id": "seg_001", "start_ms": 0, "end_ms": 1000, "type": "interview"},
            ]
        },
    )
    upsert_items(
        ctx,
        [
            {
                "id": "itr_open",
                "stage_key": "boundary_detection",
                "message": "needs operator",
                "status": "open",
                "blocking": True,
                "severity": "critical",
                "kind": "other",
            }
        ],
    )
    ctx.write_json(
        "gui_job.json",
        {"status": "running", "stage": "boundary_detection"},
        skip_handoff=True,
    )
    result = bridge_adaptation_to_itr(
        ctx,
        "boundary_detection",
        strategy_key="lint_retry_boundary_detection",
        lint_errors=["non-repairable lint"],
    )
    assert result.outcome == BridgeOutcome.PARTIAL
    job = ctx.read_json("gui_job.json")
    assert job["status"] == "needs_clarification"
    assert job["stage"] == "boundary_detection"
