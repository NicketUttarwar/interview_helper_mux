from __future__ import annotations

import pytest

from interview_mux.artifact_repairs import repair_manifest_segments
from interview_mux.segment_timeline import validate_timeline_monotonic
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment, patch_merged_config


def test_exec_1160_overlap_drop_duplicate_text(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """seg_008/seg_009 share span with identical text → drop duplicate."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"artifact_issue_triage": {"enabled": True}}},
    )
    ctx = isolated_run_ctx(tmp_path, "overlap_exec1160")
    shared_text = "So we started the company in 2019 and grew quickly from there."
    manifest = minimal_manifest(
        minimal_manifest_segment(
            "seg_008",
            start_ms=690_000,
            end_ms=810_000,
            text=shared_text,
            type="interviewee_answer",
        ),
        minimal_manifest_segment(
            "seg_009",
            start_ms=690_000,
            end_ms=810_000,
            text=shared_text,
            type="interviewee_answer",
        ),
    )
    patched, applied = repair_manifest_segments(ctx, manifest)
    seg_ids = [s["segment_id"] for s in patched["segments"]]
    assert len(seg_ids) == 1
    assert any(a.get("reason") == "duplicate_span_same_text" for a in applied)
    assert validate_timeline_monotonic(patched["segments"]) == []


def test_overlap_trim_non_identical(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "overlap_trim")
    manifest = minimal_manifest(
        minimal_manifest_segment("seg_001", start_ms=0, end_ms=5000, text="First segment."),
        minimal_manifest_segment("seg_002", start_ms=4000, end_ms=8000, text="Second segment differs."),
    )
    patched, applied = repair_manifest_segments(ctx, manifest)
    assert any(a.get("action") == "trim_overlap" for a in applied)
    assert validate_timeline_monotonic(patched["segments"]) == []
