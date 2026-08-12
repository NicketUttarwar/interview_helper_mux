"""Listen delight is an authoritative ship gate by default (mastering.listen_delight)."""

from __future__ import annotations

import json

import pytest

from interview_mux.loud_fail import LoudStageFailure
from interview_mux.listen_delight import AUDIT_REL, run_listen_delight_audit
from run_fixtures import isolated_run_ctx


def _write_raw(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_authoritative_mode_is_default(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_delight_default_mode")
    from interview_mux.listen_delight import listen_delight_cfg

    cfg = listen_delight_cfg()
    assert cfg.get("mode") == "authoritative"
    assert cfg.get("overall_min") == 0.90


def test_authoritative_fails_below_floors_and_hard_stops(tmp_path):
    """Forbidden-for-mode glue (not system layups) still hard-stops ship."""
    ctx = isolated_run_ctx(tmp_path, "exec_delight_fail")
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_summary_x",
                    "line_category": "segment_summary",
                    "text": "In this chapter we recap the deal.",
                }
            ]
        },
    )
    _write_raw(
        ctx,
        "mastering/mastering_plan.json",
        {"narrative_mode": "sparse_source", "plan_status": "complete"},
    )

    with pytest.raises(LoudStageFailure, match="Listen delight floors failed"):
        run_listen_delight_audit(ctx)

    # The audit artifact is still written (observability) even though the stage hard-stops.
    audit = ctx.read_json("mastering/listen_delight_audit.json")
    assert audit["mode"] == "authoritative"
    assert audit["blocking"] is True
    assert audit["advisory"] is False
    assert audit["passed"] is False
    assert audit["overall"] < audit["overall_min"]
    assert audit["failed_dimensions"]


def test_authoritative_passes_when_floors_are_cleared(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_delight_pass")

    _write_raw(
        ctx,
        "understanding/delivery_brief.json",
        {
            "version": 1,
            "target_duration_sec": {"min": 60, "ideal": 100, "max": 150},
            "question_budget": {"min": 0, "ideal": 1, "max": 2},
        },
    )
    _write_raw(
        ctx,
        "segments/manifest.json",
        {"segments": [{"segment_id": "seg_001", "start_ms": 0, "end_ms": 100000}]},
    )
    _write_raw(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_001"]})
    _write_raw(ctx, "master/bridge_completeness.json", {"missing_count": 0, "stub_count": 0})
    _write_raw(
        ctx,
        "master/seam_autopsy.json",
        {"scores": {"music_completeness": 1.0}, "seams": []},
    )
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "line_001",
                    "line_category": "story_bridge",
                    "delivery": "record",
                }
            ]
        },
    )

    audit = run_listen_delight_audit(ctx)

    assert audit["mode"] == "authoritative"
    assert audit["blocking"] is True
    assert audit["passed"] is True
    assert audit["overall"] >= audit["overall_min"]
    assert not audit["failed_dimensions"]
    assert audit["dimensions"]["nugget_retention"] == 1.0
    assert audit["dimensions"]["cut_integrity"] == 1.0
    assert audit["dimensions"]["conversation_fit"] == 1.0
    assert audit["dimensions"]["sonic_weave"] == 1.0


def test_advisory_mode_never_blocks(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_delight_advisory")
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        lambda: {"mode": "advisory"},
    )
    audit = run_listen_delight_audit(ctx)
    assert audit["mode"] == "advisory"
    assert audit["advisory"] is True
    assert audit["blocking"] is False
    # Still scored — advisory only changes whether it blocks, not whether it's real.
    assert "dimensions" in audit
    assert isinstance(audit["overall"], float)


def test_gui_stage_info_artifact_path_matches_writer():
    """Regression: web/stages.py StageInfo must point at the real writer path
    (`mastering/…`, not `master/…`) or the GUI stage-outputs panel and
    write-staging allow-list silently disagree with what the stage writes."""
    from interview_mux.web.stages import STAGE_BY_ID

    info = STAGE_BY_ID["listen_delight_audit"]
    assert AUDIT_REL in info.artifacts
    assert all("master/listen_delight_audit.json" != a for a in info.artifacts)


def test_cut_integrity_degrades_with_critical_junction_residuals(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_delight_cut_integrity")
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        lambda: {"mode": "advisory"},
    )
    _write_raw(
        ctx,
        "master/junction_snip_qa.json",
        {
            "residual_findings": [
                {"severity": "critical", "kind": "unresolved_clause"},
                {"severity": "warn", "kind": "minor"},
            ]
        },
    )
    audit = run_listen_delight_audit(ctx)
    assert audit["dimensions"]["cut_integrity"] < 1.0


def test_cut_integrity_uses_hang_ratio_not_per_hit_zero(tmp_path, monkeypatch):
    """Five hanging ends on a long EDL must not collapse cut_integrity to 0."""
    from interview_mux.listen_delight import evaluate_listen_delight

    ctx = isolated_run_ctx(tmp_path, "exec_delight_hang_ratio")
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        lambda: {"mode": "advisory"},
    )

    def fake_continues(words, end_ms):
        return int(end_ms) < 5000  # first 5 clips only

    monkeypatch.setattr(
        "interview_mux.gap_vo_prior_context.clause_continues_after", fake_continues
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_prior_context.is_legal_conceptual_hinge",
        lambda *a, **k: True,
    )
    clips = [
        {"type": "speech", "source_start_ms": i * 1000, "source_end_ms": i * 1000 + 800}
        for i in range(50)
    ]
    words = [
        {"text": "hello.", "start_ms": c["source_end_ms"] - 50, "end_ms": c["source_end_ms"]}
        for c in clips
    ]
    _write_raw(ctx, "master/edl.json", {"clips": clips})
    _write_raw(ctx, "transcript/full.json", {"words": words})
    result = evaluate_listen_delight(ctx)
    assert result["dimensions"]["cut_integrity"] > 0.5
    assert result["dimensions"]["cut_integrity"] < 1.0


def test_authoritative_fail_writes_remutate_plan(tmp_path):
    from interview_mux.listen_delight_remutate import REMUTATE_REL

    ctx = isolated_run_ctx(tmp_path, "exec_delight_remutate")
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_summary_x",
                    "line_category": "segment_summary",
                    "text": "In this chapter we recap the deal.",
                }
            ]
        },
    )
    _write_raw(
        ctx,
        "mastering/mastering_plan.json",
        {"narrative_mode": "sparse_source", "plan_status": "complete"},
    )
    with pytest.raises(LoudStageFailure, match="Listen delight floors failed"):
        run_listen_delight_audit(ctx)
    assert ctx.artifact_exists(REMUTATE_REL)
    plan = ctx.read_json(REMUTATE_REL)
    assert plan["attempt"] == 1
    assert plan.get("failed_dimensions")
    assert plan.get("passed") is not True
