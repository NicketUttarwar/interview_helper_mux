from __future__ import annotations

import pytest

from interview_mux.lint_repair_bridge import (
    RepairOutcome,
    lint_errors_structurally_repairable,
    try_staged_structural_repair,
)
from interview_mux.write_staging import write_pending_content
from run_fixtures import isolated_run_ctx, patch_merged_config


def test_lint_errors_structurally_repairable_patterns() -> None:
    assert lint_errors_structurally_repairable(["duplicate segment_id seg_001"])
    assert lint_errors_structurally_repairable(["manifest times not monotonic"])
    assert not lint_errors_structurally_repairable(["no boundaries"])


def test_try_staged_structural_repair_dedupes(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"artifact_issue_triage": {"enabled": True}}},
    )
    monkeypatch.setattr(
        "interview_mux.interview_spine.config.spine_enabled",
        lambda *_a, **_k: False,
    )
    ctx = isolated_run_ctx(tmp_path, "repair_bridge")
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
                {
                    "segment_id": "seg_001",
                    "start_ms": 500,
                    "end_ms": 1500,
                    "type": "interview",
                    "proposed_split_reason": "topic_shift",
                },
                {
                    "segment_id": "seg_002",
                    "start_ms": 1500,
                    "end_ms": 2500,
                    "type": "interview",
                    "proposed_split_reason": "topic_shift",
                },
            ]
        },
    )
    repair = try_staged_structural_repair(
        ctx,
        "boundary_detection",
        ["duplicate segment_id seg_001"],
    )
    assert repair.outcome in (RepairOutcome.REPAIRED_OK, RepairOutcome.REPAIRED_PARTIAL)
    assert repair.repaired
