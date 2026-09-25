"""Post-master quality floors + feel-unavailable publish gate."""

from __future__ import annotations

import json

from interview_mux.post_master_quality import (
    build_listener_scorecard,
    evaluate_post_master_quality,
)
from run_fixtures import isolated_run_ctx


def _write_raw(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_feel_unavailable_omitted_when_aspirational_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "interview_mux.aspirational_quality.is_aspirational_enabled",
        lambda ctx=None: False,
    )
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        lambda: {"mode": "advisory", "overall_min": 0.90},
    )
    ctx = isolated_run_ctx(tmp_path, "exec_pmq_feel")
    master = ctx.path("master", "master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF....")
    _write_raw(
        ctx,
        "master/seam_autopsy.json",
        {
            "version": 1,
            "generated_at": "2026-01-01T00:00:00Z",
            "phase": "post_master",
            "commitment": {"status": "committed", "reasons": []},
            "scores": {
                "continuity": 0.95,
                "finishability": 0.95,
                "information_clarity": 0.95,
                "music_completeness": 0.95,
                "sonic_density_fit": 0.9,
            },
            "seams": [],
            "blocking_reasons": [],
        },
    )
    _write_raw(ctx, "master/render_ledger.json", {"version": 1})
    _write_raw(
        ctx,
        "master/junction_snip_qa.json",
        {
            "residual_findings": [],
            "feel_audit_unavailable": True,
            "blocking_reasons": ["junction_feel_audit_unavailable"],
        },
    )
    monkeypatch.setattr(
        "interview_mux.post_master_quality.post_master_quality_cfg",
        lambda: {
            "block_on_feel_unavailable": True,
            "overall_min": 0.90,
            "dimension_floors": {
                "flow": 0.90,
                "clarity": 0.90,
                "music_completeness": 0.90,
                "synthetic_fit": 0.85,
                "native_respect": 0.90,
            },
        },
    )
    quality = evaluate_post_master_quality(ctx)
    # F6 3C: aspirational off omits rubric misses (feel is rubric, not structural).
    assert quality["status"] == "pass"
    assert quality["publish_allowed"] is True
    assert "feel_audit_available" not in quality["failed_checks"]


def test_feel_unavailable_allows_publish_when_junction_committed(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_pmq_feel_ok")
    master = ctx.path("master", "master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF....")
    _write_raw(
        ctx,
        "master/seam_autopsy.json",
        {
            "version": 1,
            "generated_at": "2026-01-01T00:00:00Z",
            "phase": "post_master",
            "commitment": {"status": "committed", "reasons": []},
            "scores": {
                "continuity": 0.95,
                "finishability": 0.95,
                "information_clarity": 0.95,
                "music_completeness": 0.95,
                "sonic_density_fit": 0.9,
            },
            "seams": [],
            "blocking_reasons": [],
        },
    )
    _write_raw(ctx, "master/render_ledger.json", {"version": 1})
    _write_raw(
        ctx,
        "master/junction_snip_qa.json",
        {
            "residual_findings": [],
            "feel_audit_unavailable": True,
            "blocking_reasons": [],
        },
    )
    monkeypatch.setattr(
        "interview_mux.post_master_quality.post_master_quality_cfg",
        lambda: {
            "block_on_feel_unavailable": True,
            "overall_min": 0.0,
            "dimension_floors": {},
        },
    )
    quality = evaluate_post_master_quality(ctx)
    assert "feel_audit_available" not in quality["failed_checks"]


def test_scorecard_dimension_floors_block_publish(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_pmq_floors")
    master = ctx.path("master", "master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF....")
    _write_raw(
        ctx,
        "master/seam_autopsy.json",
        {
            "version": 1,
            "generated_at": "2026-01-01T00:00:00Z",
            "phase": "post_master",
            "commitment": {"status": "committed", "reasons": []},
            "scores": {
                "continuity": 0.95,
                "finishability": 0.95,
                "information_clarity": 0.95,
                "music_completeness": 0.95,
                "sonic_density_fit": 0.2,
            },
            "seams": [],
            "blocking_reasons": [],
        },
    )
    _write_raw(ctx, "master/render_ledger.json", {"version": 1})
    _write_raw(
        ctx,
        "master/junction_snip_qa.json",
        {"residual_findings": [], "blocking_reasons": []},
    )
    monkeypatch.setattr(
        "interview_mux.post_master_quality.post_master_quality_cfg",
        lambda: {
            "block_on_feel_unavailable": True,
            "overall_min": 0.90,
            "dimension_floors": {
                "flow": 0.90,
                "clarity": 0.90,
                "music_completeness": 0.90,
                "synthetic_fit": 0.85,
                "native_respect": 0.90,
            },
        },
    )
    quality = evaluate_post_master_quality(ctx)
    assert "scorecard_dimension_floors" in quality["failed_checks"] or (
        "scorecard_overall_floor" in quality["failed_checks"]
    )


def test_omit_ledger_contract_is_a_publish_check(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_pmq_omit_contract")
    master = ctx.path("master", "master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF....")
    _write_raw(ctx, "understanding/omit_ledger.json", {"version": 1, "entries": [], "summary": {}})
    monkeypatch.setattr(
        "interview_mux.omit_ledger.air_contract_errors",
        lambda *_args, **_kwargs: ["omit_ledger_gap_line_still_in_edl:vo_001"],
    )

    quality = evaluate_post_master_quality(ctx)
    check = next(
        row for row in quality["checks"] if row["check_id"] == "omit_ledger_air_contract"
    )
    assert check["passed"] is False
    assert check["detail"]["errors"] == ["omit_ledger_gap_line_still_in_edl:vo_001"]
    card = build_listener_scorecard(ctx, {"status": "pass", "publish_allowed": True})
    assert "synthetic_fit" in card["dimensions"]


def _write_good_pmq_fixture(ctx) -> None:
    master = ctx.path("master", "master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF....")
    _write_raw(
        ctx,
        "master/seam_autopsy.json",
        {
            "version": 1,
            "generated_at": "2026-01-01T00:00:00Z",
            "phase": "post_master",
            "commitment": {"status": "committed", "reasons": []},
            "scores": {
                "continuity": 0.95,
                "finishability": 0.95,
                "information_clarity": 0.95,
                "music_completeness": 0.95,
                "sonic_density_fit": 0.9,
            },
            "seams": [],
            "blocking_reasons": [],
        },
    )
    _write_raw(ctx, "master/render_ledger.json", {"version": 1})
    _write_raw(
        ctx,
        "master/junction_snip_qa.json",
        {"residual_findings": [], "blocking_reasons": []},
    )


_GOOD_PMQ_CFG = {
    "block_on_feel_unavailable": True,
    "overall_min": 0.90,
    "dimension_floors": {
        "flow": 0.90,
        "clarity": 0.90,
        "music_completeness": 0.90,
        "synthetic_fit": 0.85,
        "native_respect": 0.90,
    },
}


def test_listen_delight_floors_not_in_pmq_ship_bar(tmp_path, monkeypatch):
    """S2: delight floors are judged only by listen_delight at ship — not PMQ."""
    monkeypatch.setattr(
        "interview_mux.aspirational_quality.is_aspirational_enabled",
        lambda ctx=None: False,
    )
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        lambda: {"mode": "authoritative", "overall_min": 0.90},
    )
    ctx = isolated_run_ctx(tmp_path, "exec_pmq_delight_missing")
    _write_good_pmq_fixture(ctx)
    monkeypatch.setattr(
        "interview_mux.post_master_quality.post_master_quality_cfg",
        lambda: _GOOD_PMQ_CFG,
    )
    quality = evaluate_post_master_quality(ctx)
    assert "listen_delight_floors" not in [c["check_id"] for c in quality["checks"]]
    assert "listen_delight_floors" not in quality["failed_checks"]


def test_listen_delight_floors_pass_when_audit_clears_floors(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_pmq_delight_pass")
    _write_good_pmq_fixture(ctx)
    monkeypatch.setattr(
        "interview_mux.post_master_quality.post_master_quality_cfg",
        lambda: _GOOD_PMQ_CFG,
    )
    _write_raw(
        ctx,
        "mastering/listen_delight_audit.json",
        {
            "version": 1,
            "mode": "authoritative",
            "advisory": False,
            "blocking": True,
            "overall": 0.95,
            "overall_min": 0.90,
            "dimensions": {
                "nugget_retention": 0.95,
                "cut_integrity": 1.0,
                "conversation_fit": 0.95,
                "sonic_weave": 0.95,
                "mode_coherence": 1.0,
                "finishability": 0.9,
                "recommendability": 0.9,
                "story_followability": 0.88,
            },
            "failed_dimensions": [],
            "passed": True,
            "dimension_floors": {
                "nugget_retention": 0.80,
                "cut_integrity": 0.85,
                "conversation_fit": 0.85,
                "sonic_weave": 0.85,
                "mode_coherence": 0.80,
                "finishability": 0.80,
                "recommendability": 0.75,
            },
            "generated_at": "2026-01-01T00:00:00Z",
        },
    )
    quality = evaluate_post_master_quality(ctx)
    assert "listen_delight_floors" not in quality["failed_checks"]
    assert quality["status"] == "pass"


def test_advisory_rubric_fail_allows_publish_with_advisories(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_pmq_advisory_fail")
    _write_good_pmq_fixture(ctx)
    monkeypatch.setattr(
        "interview_mux.post_master_quality.post_master_quality_cfg",
        lambda: _GOOD_PMQ_CFG,
    )
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        lambda: {
            "mode": "advisory",
            "overall_min": 0.99,
            "dimension_floors": {"finishability": 0.99},
        },
    )
    quality = evaluate_post_master_quality(ctx)
    from interview_mux.quality_status import STATUS_PASS

    assert quality["status"] == STATUS_PASS
    assert quality["publish_allowed"] is True
    assert "listen_delight_floors" not in quality["rubric_failed_checks"]
    from interview_mux.post_master_quality import build_listener_scorecard
    from interview_mux.prompt_validation import validate_listener_scorecard

    scorecard = build_listener_scorecard(ctx, quality)
    assert scorecard["quality_status"] == STATUS_PASS
    assert scorecard["publish_allowed"] is True
    assert validate_listener_scorecard(scorecard) == []


def test_listen_delight_advisory_mode_not_rescored_in_pmq(tmp_path, monkeypatch):
    """S2: advisory delight floors are not a PMQ check (ship judge is listen_delight)."""
    ctx = isolated_run_ctx(tmp_path, "exec_pmq_delight_advisory")
    _write_good_pmq_fixture(ctx)
    monkeypatch.setattr(
        "interview_mux.post_master_quality.post_master_quality_cfg",
        lambda: _GOOD_PMQ_CFG,
    )
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        lambda: {
            "mode": "advisory",
            "overall_min": 0.99,
            "dimension_floors": {"finishability": 0.99},
        },
    )
    quality = evaluate_post_master_quality(ctx)
    assert "listen_delight_floors" not in [c["check_id"] for c in quality["checks"]]
    assert quality["publish_allowed"] is True
    from interview_mux.quality_status import STATUS_PASS

    assert quality["status"] == STATUS_PASS
