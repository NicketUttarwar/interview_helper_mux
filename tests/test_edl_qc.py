from __future__ import annotations

import pytest

from interview_mux.edl_qc import validate_flow1_edl
from interview_mux.gates import check_edl_qc
from interview_mux.operator_quality import qc_summary
from interview_mux.run_context import RunContext
from interview_mux.stages.assembly import build_flow1_edl
from run_fixtures import minimal_gap_line, minimal_gap_report, minimal_manifest, minimal_manifest_segment


def _segments() -> dict[str, dict]:
    return {
        "seg_a": minimal_manifest_segment("seg_a", start_ms=0, end_ms=10_000),
        "seg_b": minimal_manifest_segment("seg_b", start_ms=10_000, end_ms=25_000),
    }


def _write_manifest(ctx: RunContext) -> None:
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_a", start_ms=0, end_ms=10_000),
            minimal_manifest_segment("seg_b", start_ms=10_000, end_ms=25_000),
        ),
    )


def _write_gap_report(ctx: RunContext, *, lines: list[dict] | None = None) -> None:
    ctx.write_json("understanding/gap_report.json", minimal_gap_report(*(lines or [])))


def test_validate_flow1_edl_passes_built_edl(tmp_path) -> None:
    ctx = RunContext("run_edl_qc_ok", create=True)
    _write_manifest(ctx)
    _write_gap_report(
        ctx,
        lines=[
            minimal_gap_line(
                line_id="line_001",
                targets_segment_id="seg_b",
                placement="before",
                delivery="record",
            )
        ],
    )
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a", "seg_b"]},
        segments_by_id=_segments(),
        gap_report=ctx.read_json("understanding/gap_report.json"),
        resolve_vo_path=lambda _line: None,
        vo_duration_ms=lambda _p: 2_000,
    )
    assert validate_flow1_edl(ctx, edl) == []


def test_validate_flow1_edl_unknown_vo_line_id(tmp_path) -> None:
    ctx = RunContext("run_edl_qc_bad_line", create=True)
    _write_manifest(ctx)
    _write_gap_report(ctx)
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_a"],
        "clips": [
            {
                "type": "vo_pickup",
                "line_id": "line_missing",
                "targets_segment_id": "seg_a",
                "placement": "before",
                "timeline_start_ms": 0,
                "duration_ms": 1000,
            },
            {
                "type": "speech",
                "segment_id": "seg_a",
                "source_start_ms": 0,
                "source_end_ms": 5000,
                "timeline_start_ms": 1000,
                "duration_ms": 5000,
            },
        ],
        "timeline_duration_ms": 6000,
    }
    errors = validate_flow1_edl(ctx, edl)
    assert any("line_missing" in e for e in errors)


def test_validate_flow1_edl_overlapping_speech() -> None:
    ctx = RunContext("run_edl_qc_overlap", create=True)
    _write_manifest(ctx)
    _write_gap_report(ctx)
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_a", "seg_b"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_a",
                "source_start_ms": 0,
                "source_end_ms": 5000,
                "timeline_start_ms": 0,
                "duration_ms": 5000,
            },
            {
                "type": "speech",
                "segment_id": "seg_b",
                "source_start_ms": 0,
                "source_end_ms": 5000,
                "timeline_start_ms": 3000,
                "duration_ms": 5000,
            },
        ],
        "timeline_duration_ms": 8000,
    }
    errors = validate_flow1_edl(ctx, edl)
    assert any("Overlapping speech" in e for e in errors)


def test_validate_flow1_edl_allows_mix_overlap() -> None:
    ctx = RunContext("run_edl_qc_mix_overlap", create=True)
    _write_manifest(ctx)
    _write_gap_report(
        ctx,
        lines=[
            minimal_gap_line(
                line_id="line_001",
                targets_segment_id="seg_a",
                placement="after",
                delivery="record",
            )
        ],
    )
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_a"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_a",
                "source_start_ms": 0,
                "source_end_ms": 5000,
                "timeline_start_ms": 0,
                "duration_ms": 5000,
                "mix_overlap_ms": 0,
            },
            {
                "type": "vo_pickup",
                "line_id": "line_001",
                "targets_segment_id": "seg_a",
                "placement": "after",
                "timeline_start_ms": 4900,
                "duration_ms": 2000,
                "mix_overlap_ms": 100,
            },
        ],
        "timeline_duration_ms": 6900,
    }
    assert validate_flow1_edl(ctx, edl) == []


def test_validate_flow1_edl_skips_zero_duration_for_monotonic() -> None:
    ctx = RunContext("run_edl_qc_zero_skip", create=True)
    _write_manifest(ctx)
    _write_gap_report(ctx)
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_a"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_a",
                "source_start_ms": 0,
                "source_end_ms": 5000,
                "timeline_start_ms": 0,
                "duration_ms": 5000,
            },
            {
                "type": "transition",
                "after_segment_id": "seg_a",
                "before_segment_id": "seg_b",
                "timeline_start_ms": 5000,
                "duration_ms": 0,
                "mix_overlap_ms": 0,
            },
            {
                "type": "vo_pickup",
                "line_id": "line_001",
                "targets_segment_id": "seg_a",
                "placement": "after",
                "timeline_start_ms": 4900,
                "duration_ms": 2000,
                "mix_overlap_ms": 100,
            },
        ],
        "timeline_duration_ms": 6900,
    }
    _write_gap_report(
        ctx,
        lines=[
            minimal_gap_line(
                line_id="line_001",
                targets_segment_id="seg_a",
                placement="after",
                delivery="record",
            )
        ],
    )
    assert validate_flow1_edl(ctx, edl) == []


def test_validate_flow1_edl_non_monotonic_timeline() -> None:
    ctx = RunContext("run_edl_qc_mono", create=True)
    _write_manifest(ctx)
    _write_gap_report(ctx)
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_a", "seg_b"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_a",
                "source_start_ms": 0,
                "source_end_ms": 5000,
                "timeline_start_ms": 5000,
                "duration_ms": 5000,
            },
            {
                "type": "speech",
                "segment_id": "seg_b",
                "source_start_ms": 0,
                "source_end_ms": 5000,
                "timeline_start_ms": 0,
                "duration_ms": 5000,
            },
        ],
        "timeline_duration_ms": 10_000,
    }
    errors = validate_flow1_edl(ctx, edl)
    assert any("timeline_start_ms" in e and "before previous" in e for e in errors)


def test_validate_flow1_edl_timeline_duration_mismatch() -> None:
    ctx = RunContext("run_edl_qc_duration", create=True)
    _write_manifest(ctx)
    _write_gap_report(ctx)
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_a"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_a",
                "source_start_ms": 0,
                "source_end_ms": 5000,
                "timeline_start_ms": 0,
                "duration_ms": 5000,
            }
        ],
        "timeline_duration_ms": 9999,
    }
    errors = validate_flow1_edl(ctx, edl)
    assert any("timeline_duration_ms" in e for e in errors)


def test_check_edl_qc_records_summary_on_pass(tmp_path) -> None:
    ctx = RunContext("run_edl_qc_summary", create=True)
    _write_manifest(ctx)
    _write_gap_report(ctx)
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_a"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_a",
                "source_start_ms": 0,
                "source_end_ms": 5000,
                "timeline_start_ms": 0,
                "duration_ms": 5000,
            }
        ],
        "timeline_duration_ms": 5000,
    }
    check_edl_qc(ctx, stage="edl", edl=edl, strict=True)
    meta = ctx.read_json("run_meta.json")
    summary = qc_summary(meta, "edl_qc")
    assert summary is not None
    assert summary["passed"] is True
    assert summary["at_stage"] == "edl"


def test_check_edl_qc_strict_raises() -> None:
    ctx = RunContext("run_edl_qc_strict", create=True)
    _write_manifest(ctx)
    _write_gap_report(ctx)
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_a"],
        "clips": [],
        "timeline_duration_ms": 100,
    }
    with pytest.raises(SystemExit, match="edl_qc strict"):
        check_edl_qc(ctx, stage="edl", edl=edl, strict=True)


def test_check_edl_qc_warn_does_not_raise() -> None:
    ctx = RunContext("run_edl_qc_warn", create=True)
    _write_manifest(ctx)
    _write_gap_report(ctx)
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_a"],
        "clips": [],
        "timeline_duration_ms": 100,
    }
    check_edl_qc(ctx, stage="mix", edl=edl, strict=False)
    meta = ctx.read_json("run_meta.json")
    assert qc_summary(meta, "edl_qc")["passed"] is False
