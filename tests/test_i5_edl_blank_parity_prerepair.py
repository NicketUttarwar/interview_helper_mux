"""i5: EDL narrative QC must pre-repair blank selection before parity fail."""

from __future__ import annotations

import json

from interview_mux.edl_narrative_qc import validate_flow1_edl_narrative
from interview_mux.gates import check_edl_narrative_qc
from run_fixtures import isolated_run_ctx, init_run_meta_for_test


def _write(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_i5_edl_narrative_qc_prerepairs_blank_before_parity(
    tmp_path, monkeypatch
) -> None:
    """Blank on-air id omitted from speech must not SystemExit after pre-repair."""
    ctx = isolated_run_ctx(tmp_path, "exec_i5_blank_parity")
    init_run_meta_for_test(ctx)
    monkeypatch.setattr(
        "interview_mux.artifact_repairs._segment_is_blank_or_unusable",
        lambda _ctx, sid: str(sid) == "seg_blank",
    )
    _write(
        ctx,
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_a", "seg_blank", "seg_b"],
            "excluded_segment_ids": [],
            "chapters": [],
        },
    )
    _write(
        ctx,
        "master/coverage_audit.json",
        {
            "coverage_score": 1.0,
            "topic_mappings": [],
            "claim_mappings": [],
            "missing_coverage": [],
        },
    )
    _write(ctx, "master/narrative_plan.json", {"beats": []})
    # In-memory EDL already omitted the blank (as build_flow1_edl does).
    edl = {
        "clips": [
            {"type": "speech", "segment_id": "seg_a"},
            {"type": "speech", "segment_id": "seg_b"},
        ]
    }
    # Pre-repair + validate should clear the parity miss.
    check_edl_narrative_qc(ctx, stage="edl", edl=edl, strict=True)
    sel = ctx.read_json("master/selection.json")
    assert "seg_blank" not in (sel.get("ordered_segment_ids") or [])
    assert validate_flow1_edl_narrative(ctx, edl) == []
