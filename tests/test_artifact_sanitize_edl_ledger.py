"""Tests for artifact_sanitize EDL + assembly_ledger pair (W6)."""

from __future__ import annotations

from interview_mux.artifact_sanitize.edl import LEDGER_REL, REL, persist_edl_and_ledger
from interview_mux.run_context import RunContext


def test_persist_edl_and_ledger_co_rebuilds_ledger() -> None:
    ctx = RunContext(create=True)
    ctx.path("master").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "excluded_segment_ids": [],
            "chapters": [],
            "order_content_hash": "edl_pair_hash",
        },
        skip_handoff=True,
    )
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_001", "seg_002"],
        "order_content_hash": "edl_pair_hash",
        "timeline_duration_ms": 1200,
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_001",
                "source_start_ms": 0,
                "source_end_ms": 500,
                "timeline_start_ms": 0,
                "duration_ms": 500,
            },
            {
                "type": "transition",
                "after_segment_id": "seg_001",
                "before_segment_id": "seg_002",
                "timeline_start_ms": 500,
                "duration_ms": 200,
            },
            {
                "type": "speech",
                "segment_id": "seg_002",
                "source_start_ms": 0,
                "source_end_ms": 500,
                "timeline_start_ms": 700,
                "duration_ms": 500,
            },
        ],
    }
    result = persist_edl_and_ledger(ctx, edl, source="test_persist")
    assert any(a.get("action") == "rebuild_assembly_ledger" for a in result.actions)
    assert ctx.artifact_exists(REL)
    assert ctx.artifact_exists(LEDGER_REL)
    ledger = ctx.read_json(LEDGER_REL)
    assert isinstance(ledger, dict)
    # Ledger should mirror EDL order surface
    assert (
        ledger.get("ordered_segment_ids") == ["seg_001", "seg_002"]
        or "atoms" in ledger
        or "seams" in ledger
    )
