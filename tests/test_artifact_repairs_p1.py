from __future__ import annotations

import pytest

from interview_mux.artifact_repairs import (
    repair_coverage_audit,
    repair_edl_audit,
    repair_gap_report,
    repair_narrative_plan,
)
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment


def test_repair_gap_report_drops_orphan_targets(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_gap")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_001")),
        skip_handoff=True,
    )
    doc = {
        "interviewer_lines": [
            {"line_id": "line_1", "targets_segment_id": "seg_missing", "text": "Why?"},
            {"targets_segment_id": "seg_001", "text": "Follow up"},
        ]
    }
    patched, applied = repair_gap_report(ctx, doc)
    assert len(patched["interviewer_lines"]) == 1
    assert patched["interviewer_lines"][0]["targets_segment_id"] == "seg_001"
    assert applied


def test_repair_narrative_plan_drops_orphan_chapters(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_narr")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_001")),
        skip_handoff=True,
    )
    doc = {
        "arc_summary": "Test",
        "chapters": [
            {"chapter_id": "ch_1", "title": "A", "segment_ids": ["seg_missing"]},
            {"chapter_id": "ch_2", "title": "B", "segment_ids": ["seg_001"]},
        ],
    }
    patched, applied = repair_narrative_plan(ctx, doc)
    assert len(patched["chapters"]) == 1
    assert patched["chapters"][0]["chapter_id"] == "ch_2"


def test_repair_edl_audit_normalizes_verdict(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_edl")
    patched, applied = repair_edl_audit(ctx, {"verdict": "unknown_status", "issues": []})
    assert patched["verdict"] == "warn"
    assert applied


def test_repair_coverage_audit_drops_unknown_topics(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_cov")
    ctx.write_json(
        "understanding/content_brief.json",
        {"thesis": "Test thesis", "topics": [{"name": "Origin Story", "summary": "x"}]},
        skip_handoff=True,
    )
    doc = {"missing_coverage": [{"topic": "Unknown Topic", "reason": "gap"}]}
    patched, applied = repair_coverage_audit(ctx, doc)
    assert patched["missing_coverage"] == []
    assert applied
