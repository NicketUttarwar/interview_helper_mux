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


def test_feel_unavailable_blocks_when_configured(tmp_path, monkeypatch):
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
    assert quality["status"] == "fail"
    assert "feel_audit_available" in quality["failed_checks"]


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
    card = build_listener_scorecard(ctx, {"status": "pass", "publish_allowed": True})
    assert "synthetic_fit" in card["dimensions"]
