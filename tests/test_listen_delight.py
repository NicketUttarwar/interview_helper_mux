"""Listen delight is an authoritative ship gate by default (mastering.listen_delight)."""

from __future__ import annotations

import json

import pytest

from interview_mux.loud_fail import LoudStageFailure
from interview_mux.listen_delight import (
    AUDIT_REL,
    evaluate_listen_delight,
    run_authoritative_listen_delight_at_ship,
    run_listen_delight_audit,
)
from run_fixtures import isolated_run_ctx


def _write_raw(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_advisory_mode_is_default(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_delight_default_mode")
    from interview_mux.listen_delight import listen_delight_cfg

    cfg = listen_delight_cfg()
    assert cfg.get("mode") == "advisory"
    assert cfg.get("overall_min") == 0.90


def test_aspirational_ship_does_not_hard_stop(tmp_path):
    """With aspirational policy, below-floor delight is advisory at ship."""
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

    audit = run_listen_delight_audit(ctx)
    assert audit["pass"] == "pre_mix"
    assert audit["blocking"] is False
    assert audit["passed"] is False

    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "master.wav").write_bytes(b"RIFF" + b"x" * 1100)

    ship_audit = run_authoritative_listen_delight_at_ship(ctx)
    assert ship_audit["pass"] == "post_master"
    assert ship_audit["blocking"] is False
    assert ship_audit.get("aspirational_fail") is True
    assert ship_audit["passed"] is False


def test_authoritative_fails_below_floors_when_aspirational_disabled(tmp_path, monkeypatch):
    """When aspirational is off and mode authoritative, ship still hard-stops."""
    monkeypatch.setattr(
        "interview_mux.aspirational_quality.is_aspirational_enabled",
        lambda ctx=None: False,
    )
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        lambda: {
            "mode": "authoritative",
            "overall_min": 0.90,
            "dimension_floors": {},
            "fail_early_at_audit_stage": False,
        },
    )
    ctx = isolated_run_ctx(tmp_path, "exec_delight_fail_hard")
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
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "master.wav").write_bytes(b"RIFF")

    with pytest.raises(LoudStageFailure, match="Listen delight floors failed at ship"):
        run_authoritative_listen_delight_at_ship(ctx)


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

    assert audit["mode"] == "advisory"
    assert audit["pass"] == "pre_mix"
    assert audit["blocking"] is False
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


def test_authoritative_fail_early_legacy_blocks_at_audit_stage(tmp_path, monkeypatch):
    from interview_mux.listen_delight_remutate import REMUTATE_REL

    ctx = isolated_run_ctx(tmp_path, "exec_delight_remutate")
    monkeypatch.setattr(
        "interview_mux.aspirational_quality.is_aspirational_enabled",
        lambda ctx=None: False,
    )
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        lambda: {
            "mode": "authoritative",
            "fail_early_at_audit_stage": True,
        },
    )
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


def test_recommendability_clears_floor_without_gap_vo(tmp_path, monkeypatch):
    """conversational_host + empty interviewer_lines must not fail recommendability.

    exec_1970 scored 0.65 vs a 0.75 floor while every other dim passed; ranking
    remutate cannot invent VO lines and looped 70+ times.
    """
    from interview_mux.listen_delight import evaluate_listen_delight

    ctx = isolated_run_ctx(tmp_path, "exec_delight_reco_no_vo")
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        lambda: {
            "mode": "authoritative",
            "overall_min": 0.90,
            "dimension_floors": {
                "nugget_retention": 0.80,
                "cut_integrity": 0.85,
                "conversation_fit": 0.85,
                "sonic_weave": 0.85,
                "mode_coherence": 0.80,
                "finishability": 0.80,
                "recommendability": 0.75,
                "story_followability": 0.85,
            },
        },
    )
    _write_raw(
        ctx,
        "understanding/delivery_brief.json",
        {
            "version": 1,
            "target_duration_sec": {"min": 60, "ideal": 100, "max": 150},
        },
    )
    _write_raw(
        ctx,
        "segments/manifest.json",
        {"segments": [{"segment_id": "seg_001", "start_ms": 0, "end_ms": 100000}]},
    )
    _write_raw(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_001"]})
    _write_raw(ctx, "master/bridge_completeness.json", {"missing_count": 0, "stub_count": 0, "complete": True})
    _write_raw(
        ctx,
        "master/seam_autopsy.json",
        {"scores": {"music_completeness": 1.0}, "seams": []},
    )
    _write_raw(ctx, "understanding/gap_report.json", {"interviewer_lines": []})
    _write_raw(
        ctx,
        "mastering/mastering_plan.json",
        {"narrative_mode": "conversational_host", "plan_status": "complete"},
    )
    result = evaluate_listen_delight(ctx)
    assert result["dimensions"]["recommendability"] >= 0.75
    assert "recommendability" not in result["failed_dimensions"]
    assert result["passed"] is True


def test_recommendability_only_does_not_schedule_ranking_remutate(tmp_path):
    from interview_mux.listen_delight_remutate import plan_listen_delight_remutate

    ctx = isolated_run_ctx(tmp_path, "exec_delight_reco_no_remutate")
    plan = plan_listen_delight_remutate(ctx, failed_dimensions=["recommendability"])
    assert plan["from_stages"] == []
    assert plan["from_stage"] is None
    assert plan["exhausted"] is True


def test_cut_integrity_penalizes_air_order_violations(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_delight_air_order")
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        lambda: {"mode": "advisory"},
    )
    _write_raw(
        ctx,
        "segments/boundaries.json",
        {
            "boundaries": [
                {"segment_id": "seg_003", "start_ms": 152_000},
                {"segment_id": "seg_050", "start_ms": 2_416_000},
                {"segment_id": "seg_001c", "start_ms": 0},
            ]
        },
    )
    _write_raw(
        ctx,
        "master/selection.json",
        {"ordered_segment_ids": ["seg_003", "seg_050", "seg_001c"]},
    )
    result = evaluate_listen_delight(ctx)
    assert result["dimensions"]["cut_integrity"] < 0.85
    """Slightly under brief.min but inside the ship 0.85×min envelope must pass."""
    from interview_mux.listen_delight import _nugget_retention

    ctx = isolated_run_ctx(tmp_path, "exec_delight_concise_band")
    _write_raw(
        ctx,
        "understanding/delivery_brief.json",
        {"version": 1, "target_duration_sec": {"min": 1622, "ideal": 2318, "max": 5349}},
    )
    _write_raw(
        ctx,
        "segments/manifest.json",
        {"segments": [{"segment_id": "seg_001", "start_ms": 0, "end_ms": 1_546_400}]},
    )
    _write_raw(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_001"]})
    score = _nugget_retention(ctx)
    assert score >= 0.80
    assert score < 1.0


def test_nugget_retention_after_assembly_resumes_mix_not_ranking(tmp_path):
    from interview_mux.listen_delight_remutate import plan_listen_delight_remutate

    ctx = isolated_run_ctx(tmp_path, "exec_delight_retention_after_edl")
    (ctx.run_dir / ".stage_done" / "edl").write_text("done\n", encoding="utf-8")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "assembly_preview.wav").write_bytes(b"RIFF")
    plan = plan_listen_delight_remutate(ctx, failed_dimensions=["nugget_retention"])
    assert "full_master_ranking" not in plan["from_stages"]
    assert plan["from_stage"] in {"mmaudio_sfx", "mix", "listen_delight_audit", "master_finalize"}
    assert plan["exhausted"] is False
