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


def test_repair_narrative_plan_infers_segment_ids_from_topic_tags(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_narr_infer")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_001"),
            minimal_manifest_segment("seg_012"),
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "Test thesis",
            "topics": [
                {
                    "name": "Early product missteps and pivots",
                    "summary": "Regulatory setbacks and failed products.",
                    "segment_ids": ["seg_012"],
                }
            ],
        },
        skip_handoff=True,
    )
    doc = {
        "arc_summary": "Test arc",
        "chapters": [
            {
                "chapter_id": "ch_01",
                "title": "False Starts",
                "topic_tags": ["early_product_missteps_and_pivots"],
                "suggested_open_segment_id": "seg_012",
            }
        ],
        "ordering_constraints": [],
    }
    patched, applied = repair_narrative_plan(ctx, doc)
    assert len(patched["chapters"]) == 1
    assert patched["chapters"][0]["segment_ids"] == ["seg_012"]
    assert any(row.get("action") == "infer_segment_ids" for row in applied)


def test_repair_edl_audit_normalizes_verdict(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_edl")
    patched, applied = repair_edl_audit(ctx, {"verdict": "unknown_status", "issues": []})
    assert patched["verdict"] == "warn"
    assert applied


def test_repair_edl_audit_demotes_premature_vo_nle_placement(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_edl_vo")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_005")),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_005",
                    "targets_segment_id": "seg_005",
                    "severity": "high",
                    "required": True,
                    "delivery": "synthesize",
                    "gap_type": "nugget_layup",
                    "placement": "before",
                    "text": "Stevia roadblock?",
                }
            ]
        },
        skip_handoff=True,
    )
    vo = ctx.final_path("vo_pickup")
    vo.mkdir(parents=True, exist_ok=True)
    (vo / "vo_layup_seg_005.wav").write_bytes(b"RIFF....")
    doc = {
        "verdict": "fail",
        "blocking_issues": [
            {
                "issue": (
                    "Required high-severity setup and continuity lines have no "
                    "evidenced VO-ingest or NLE placement."
                ),
                "evidence": [
                    "gap_report.interviewer_lines[0].line_id=vo_layup_seg_005",
                    "nle_edits={}",
                ],
                "recommended_action": "rerun vo_ingest, then rerun edl",
            }
        ],
        "warnings": [],
    }
    patched, applied = repair_edl_audit(ctx, doc)
    assert patched["verdict"] in ("pass", "warn")
    assert not patched.get("blocking_issues")
    assert any(
        row.get("action") == "demote_premature_vo_nle_placement" for row in applied
    )


def test_repair_edl_audit_demotes_stale_meta_question(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_edl_stale")
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_episode_orientation",
                    "episode_orientation": True,
                    "line_category": "episode_preface",
                    "text": (
                        "In this conversation, an entrepreneur traces how rural "
                        "farming roots led to a healthy-snack business. Let's hear "
                        "how that opening beat lands."
                    ),
                    "delivery": "synthesize",
                    "gap_type": "missing_setup",
                    "placement": "before",
                    "targets_segment_id": "seg_001",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "type": "transition",
                    "after_segment_id": "seg_001",
                    "before_segment_id": "seg_002",
                    "text": "At university, an unexpected encounter changed that direction.",
                }
            ]
        },
        skip_handoff=True,
    )
    doc = {
        "verdict": "fail",
        "blocking_issues": [
            {
                "issue": (
                    "The required opening-orientation line does not supply the guest "
                    "identity; it is only a meta-question."
                ),
                "evidence": ["gap_report.interviewer_lines[line_id=vo_preface_episode_orientation].text"],
            },
            {
                "issue": "Two different transition lines occupy identical selected-order adjacencies.",
                "evidence": ["transitions.transitions[0] and transitions.transitions[2]"],
            },
        ],
        "warnings": [],
    }
    patched, applied = repair_edl_audit(ctx, doc)
    assert patched["verdict"] in ("pass", "warn")
    assert not patched.get("blocking_issues")
    assert any(row.get("action") == "demote_stale_audit_vs_disk" for row in applied)


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
    # Unknown topics dropped; brief topics may be auto-documented as uncovered.
    assert not any(
        str(row.get("topic") or "") == "Unknown Topic"
        for row in (patched.get("missing_coverage") or [])
        if isinstance(row, dict)
    )
    assert applied
    assert any(
        str(row.get("topic") or "") == "Origin Story"
        for row in (patched.get("missing_coverage") or [])
        if isinstance(row, dict)
    )