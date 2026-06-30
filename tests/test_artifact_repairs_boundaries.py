from __future__ import annotations

import pytest

from interview_mux.artifact_repairs import apply_choice_to_boundaries, repair_boundaries
from run_fixtures import isolated_run_ctx, patch_merged_config


def test_apply_choice_to_boundaries_delete_segment() -> None:
    doc = {
        "boundaries": [
            {"segment_id": "seg_001", "start_ms": 0, "end_ms": 1000, "type": "interview"},
            {"segment_id": "seg_002", "start_ms": 1000, "end_ms": 2000, "type": "interview"},
        ]
    }
    issue = {"segment_id": "seg_001", "repair_strategy": "merge_overlap"}
    out = apply_choice_to_boundaries(doc, issue, "delete_segment")
    assert len(out["boundaries"]) == 1
    assert out["boundaries"][0]["segment_id"] == "seg_002"


def test_repair_boundaries_dedupes_segment_id(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"artifact_issue_triage": {"segment_overlap_policy": "drop_duplicate_then_llm_pick"}}},
    )
    ctx = isolated_run_ctx(tmp_path, "boundary_dedupe")
    rows = [
        {"segment_id": "seg_001", "start_ms": 0, "end_ms": 1000, "type": "interview"},
        {"segment_id": "seg_001", "start_ms": 500, "end_ms": 1500, "type": "interview"},
        {"segment_id": "seg_002", "start_ms": 1500, "end_ms": 2500, "type": "interview"},
    ]
    out, applied = repair_boundaries(ctx, {"boundaries": rows})
    ids = [r["segment_id"] for r in out["boundaries"]]
    assert ids == ["seg_001", "seg_002"]
    assert any(a.get("reason") == "duplicate_segment_id" for a in applied)
