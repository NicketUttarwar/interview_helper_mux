from __future__ import annotations

import pytest

from interview_mux.edl_qc import validate_flow1_edl
from interview_mux.gates import check_edl_qc
from interview_mux.operator_quality import qc_summary
from interview_mux.run_context import RunContext
from interview_mux.stages.assembly import build_flow1_edl
from run_fixtures import (
    isolated_run_ctx,
    minimal_gap_line,
    minimal_gap_report,
    minimal_manifest,
    minimal_manifest_segment,
    write_fixture_json,
)


def _remap_nle_writes(ctx: RunContext) -> None:
    """Overlap repair persists nle_edits only with mutation_class=segment_id_remap."""
    orig = ctx.write_json

    def _wrapped(rel, data, **kwargs):
        if rel == "segments/nle_edits.json":
            kwargs.setdefault("mutation_class", "segment_id_remap")
        return orig(rel, data, **kwargs)

    ctx.write_json = _wrapped  # type: ignore[method-assign]


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
    write_fixture_json(
        ctx,
        "understanding/gap_report.json",
        minimal_gap_report(*(lines or [])),
        stage_key="gap_framing_compose",
    )


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


def test_validate_flow1_edl_accepts_nle_split_children_missing_from_manifest() -> None:
    """CTA/NLE recuts live as overrides; QC must not treat those ids as unknown."""
    ctx = RunContext("run_edl_qc_nle_child", create=True)
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_003", start_ms=0, end_ms=30_000),
        ),
    )
    ctx.write_json(
        "segments/nle_edits.json",
        {
            "playhead_ms": 0,
            "sequence_order": [],
            "segment_overrides": {
                "seg_003a": {
                    "parent_id": "seg_003",
                    "start_ms": 0,
                    "end_ms": 4000,
                    "label": "intro a",
                },
                "seg_003b": {
                    "parent_id": "seg_003",
                    "start_ms": 4000,
                    "end_ms": 8000,
                    "label": "intro b",
                },
            },
        },
    )
    _write_gap_report(ctx)
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_003a", "seg_003b"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_003a",
                "source_start_ms": 0,
                "source_end_ms": 4000,
                "timeline_start_ms": 0,
                "duration_ms": 4000,
            },
            {
                "type": "speech",
                "segment_id": "seg_003b",
                "source_start_ms": 4000,
                "source_end_ms": 8000,
                "timeline_start_ms": 4000,
                "duration_ms": 4000,
            },
        ],
        "timeline_duration_ms": 8000,
    }
    errors = validate_flow1_edl(ctx, edl)
    assert not any("unknown segment_id" in e for e in errors), errors


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


def test_validate_flow1_edl_speech_clip_order_mismatch() -> None:
    ctx = RunContext("run_edl_qc_clip_order", create=True)
    _write_manifest(ctx)
    _write_gap_report(ctx)
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_a", "seg_b"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_b",
                "source_start_ms": 10_000,
                "source_end_ms": 25_000,
                "timeline_start_ms": 0,
                "duration_ms": 15_000,
            },
            {
                "type": "speech",
                "segment_id": "seg_a",
                "source_start_ms": 0,
                "source_end_ms": 10_000,
                "timeline_start_ms": 15_000,
                "duration_ms": 10_000,
            },
        ],
        "timeline_duration_ms": 25_000,
    }
    errors = validate_flow1_edl(ctx, edl)
    assert any("speech clip order" in e and "ordered_segment_ids" in e for e in errors)


def _overlapping_child_edl() -> dict:
    return {
        "version": 1,
        "ordered_segment_ids": ["seg_003c", "seg_003d", "seg_004"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_003c",
                "source_start_ms": 62_900,
                "source_end_ms": 74_760,
                "timeline_start_ms": 0,
                "duration_ms": 11_860,
            },
            {
                "type": "transition",
                "after_segment_id": "seg_003c",
                "before_segment_id": "seg_003d",
                "timeline_start_ms": 11_860,
                "duration_ms": 0,
            },
            {
                "type": "speech",
                "segment_id": "seg_003d",
                "source_start_ms": 71_000,
                "source_end_ms": 74_810,
                "timeline_start_ms": 11_860,
                "duration_ms": 3_810,
            },
            {
                "type": "speech",
                "segment_id": "seg_004",
                "source_start_ms": 80_000,
                "source_end_ms": 90_000,
                "timeline_start_ms": 15_670,
                "duration_ms": 10_000,
            },
        ],
        "timeline_duration_ms": 25_670,
    }


def test_repair_overlapping_source_merges_into_survivor(tmp_path) -> None:
    from interview_mux.edl_overlap_repair import repair_overlapping_source_ranges

    ctx = isolated_run_ctx(tmp_path, "run_edl_overlap_merge")
    _remap_nle_writes(ctx)
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment(
                "seg_003c",
                start_ms=62_900,
                end_ms=74_760,
                text="First child continues.",
                topic_tags=["origin_story"],
                speaker_id="spk_0",
                parent_id="seg_003",
            ),
            minimal_manifest_segment(
                "seg_003d",
                start_ms=71_000,
                end_ms=74_810,
                text="Nested tail.",
                topic_tags=["origin_story", "turning_point"],
                speaker_id="spk_0",
                parent_id="seg_003",
            ),
            minimal_manifest_segment(
                "seg_004",
                start_ms=80_000,
                end_ms=90_000,
                text="Next keep.",
                speaker_id="spk_0",
            ),
        ),
    )
    ctx.write_json(
        "segments/nle_edits.json",
        {
            "playhead_ms": 0,
            "sequence_order": ["seg_003c", "seg_003d", "seg_004"],
            "segment_overrides": {
                "seg_003": {"excluded": True, "split_into": ["seg_003c", "seg_003d"]},
                "seg_003c": {"parent_id": "seg_003", "start_ms": 62_900, "end_ms": 74_760},
                "seg_003d": {"parent_id": "seg_003", "start_ms": 71_000, "end_ms": 74_810},
            },
        },
        mutation_class="segment_id_remap",
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_003c", "seg_003d", "seg_004"]},
        stage_key="selection_order_sanitize",
    )
    write_fixture_json(
        ctx,
        "understanding/gap_report.json",
        minimal_gap_report(),
        stage_key="gap_framing_compose",
    )
    edl = _overlapping_child_edl()
    assert any("Overlapping source range" in e for e in validate_flow1_edl(ctx, edl))
    result = repair_overlapping_source_ranges(ctx, edl)
    assert result["repaired"] is True
    assert result["remap"] == {"seg_003d": "seg_003c"}
    speech = [c for c in edl["clips"] if c.get("type") == "speech"]
    assert [c["segment_id"] for c in speech] == ["seg_003c", "seg_004"]
    mega = speech[0]
    assert mega["source_start_ms"] == 62_900
    assert mega["source_end_ms"] == 74_810
    assert mega["duration_ms"] == 11_910
    assert edl["ordered_segment_ids"] == ["seg_003c", "seg_004"]
    assert not any(c.get("type") == "transition" for c in edl["clips"])
    assert validate_flow1_edl(ctx, edl) == []
    man = ctx.read_json("segments/manifest.json")
    ids = [s["segment_id"] for s in man["segments"]]
    assert "seg_003d" not in ids
    survivor = next(s for s in man["segments"] if s["segment_id"] == "seg_003c")
    assert survivor["start_ms"] == 62_900
    assert survivor["end_ms"] == 74_810
    assert "turning_point" in survivor["topic_tags"]
    assert "seg_003d" in survivor["fused_from"]
    sel = ctx.read_json("master/selection.json")
    assert sel["ordered_segment_ids"] == ["seg_003c", "seg_004"]
    nle = ctx.read_json("segments/nle_edits.json")
    assert nle["segment_overrides"]["seg_003d"]["excluded"] is True
    assert nle["segment_overrides"]["seg_003"]["split_into"] == ["seg_003c"]


def test_check_edl_qc_repairs_overlapping_source_instead_of_raising(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_edl_qc_overlap_gate")
    _remap_nle_writes(ctx)
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment(
                "seg_003c",
                start_ms=62_900,
                end_ms=74_760,
                speaker_id="spk_0",
                parent_id="seg_003",
            ),
            minimal_manifest_segment(
                "seg_003d",
                start_ms=71_000,
                end_ms=74_810,
                speaker_id="spk_0",
                parent_id="seg_003",
            ),
            minimal_manifest_segment("seg_004", start_ms=80_000, end_ms=90_000, speaker_id="spk_0"),
        ),
    )
    write_fixture_json(
        ctx,
        "understanding/gap_report.json",
        minimal_gap_report(),
        stage_key="gap_framing_compose",
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_003c", "seg_003d", "seg_004"]},
        stage_key="selection_order_sanitize",
    )
    edl = _overlapping_child_edl()
    check_edl_qc(ctx, stage="edl", edl=edl, strict=True)
    assert [c["segment_id"] for c in edl["clips"] if c.get("type") == "speech"] == [
        "seg_003c",
        "seg_004",
    ]
    meta = ctx.read_json("run_meta.json")
    assert qc_summary(meta, "edl_qc")["passed"] is True


def test_overlapping_source_does_not_merge_cross_speaker(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_edl_qc_overlap_xspk")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment(
                "seg_a", start_ms=0, end_ms=5000, speaker_id="spk_0"
            ),
            minimal_manifest_segment(
                "seg_b", start_ms=3000, end_ms=8000, speaker_id="spk_1"
            ),
        ),
    )
    ctx.write_json("understanding/gap_report.json", minimal_gap_report())
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
                "source_start_ms": 3000,
                "source_end_ms": 8000,
                "timeline_start_ms": 5000,
                "duration_ms": 5000,
            },
        ],
        "timeline_duration_ms": 10_000,
    }
    with pytest.raises(SystemExit, match="Overlapping source range"):
        check_edl_qc(ctx, stage="edl", edl=edl, strict=True)
