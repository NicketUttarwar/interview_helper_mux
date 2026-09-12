"""F6 ship schema / PMQ: allowed ships write pass; finalize does not crash.

Fixture intent from exec_11160 (advisory_fail rejected by pass/fail-only schema).
Does not resume that run. Disk status is pass when publish is allowed (1B/2A);
non-aspirational rubric misses are omitted (3C).
"""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.post_master_quality import (
    evaluate_post_master_quality,
    persist_post_master_quality,
    run_post_master_quality,
)
from interview_mux.prompt_validation import (
    validate_listener_scorecard,
    validate_post_master_quality,
)
from interview_mux.quality_status import STATUS_ADVISORY_FAIL, STATUS_PASS
from run_fixtures import isolated_run_ctx

_FIX = Path(__file__).resolve().parent / "fixtures" / "f6_pmq_ship_schema"
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


def _write_raw(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _plant_good_master(ctx) -> None:
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


def _delight_miss_cfg():
    return {
        "mode": "advisory",
        "overall_min": 0.99,
        "dimension_floors": {"finishability": 0.99},
    }


def test_allowed_ship_writes_pass_not_advisory_fail(tmp_path, monkeypatch) -> None:
    json.loads((_FIX / "advisory_envelope.json").read_text(encoding="utf-8"))
    ctx = isolated_run_ctx(tmp_path, "f6_pass_on_disk")
    _plant_good_master(ctx)
    monkeypatch.setattr(
        "interview_mux.post_master_quality.post_master_quality_cfg",
        lambda: _GOOD_PMQ_CFG,
    )
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        _delight_miss_cfg,
    )
    quality = evaluate_post_master_quality(ctx)
    assert quality["publish_allowed"] is True
    assert quality["status"] == STATUS_PASS
    assert quality["status"] != STATUS_ADVISORY_FAIL
    persist_post_master_quality(ctx, quality)
    disk = ctx.read_json("master/post_master_quality.json")
    assert disk["status"] == STATUS_PASS
    assert disk["status"] != STATUS_ADVISORY_FAIL
    assert validate_post_master_quality(disk) == []
    card = ctx.read_json("master/listener_scorecard.json")
    assert card["quality_status"] == STATUS_PASS
    assert card["quality_status"] != STATUS_ADVISORY_FAIL
    assert validate_listener_scorecard(card) == []


def test_run_pmq_block_true_does_not_loud_fail_on_allowed_rubric(
    tmp_path, monkeypatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "f6_finalize_no_crash")
    _plant_good_master(ctx)
    _write_raw(ctx, "run_meta.json", {"homunculus_version": "0.1.0"})
    monkeypatch.setattr(
        "interview_mux.post_master_quality.post_master_quality_cfg",
        lambda: _GOOD_PMQ_CFG,
    )
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        _delight_miss_cfg,
    )
    monkeypatch.setattr(
        "interview_mux.listen_delight.run_authoritative_listen_delight_at_ship",
        lambda _ctx: None,
    )
    monkeypatch.setattr(
        "interview_mux.seam_autopsy.build_autopsy",
        lambda _ctx, **_k: ctx.read_json("master/seam_autopsy.json"),
    )
    monkeypatch.setattr("interview_mux.seam_autopsy.write_autopsy", lambda *_a, **_k: None)
    monkeypatch.setattr("interview_mux.seam_autopsy.enrich_ledger", lambda *_a, **_k: None)
    out = run_post_master_quality(ctx, block=True)
    assert out["publish_allowed"] is True
    assert out["status"] == STATUS_PASS
    assert ctx.artifact_exists("master/post_master_quality.json")


def test_non_aspirational_omits_rubric_miss_from_pmq(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.aspirational_quality.is_aspirational_enabled",
        lambda ctx=None: False,
    )
    ctx = isolated_run_ctx(tmp_path, "f6_omit_rubric")
    _plant_good_master(ctx)
    monkeypatch.setattr(
        "interview_mux.post_master_quality.post_master_quality_cfg",
        lambda: _GOOD_PMQ_CFG,
    )
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        _delight_miss_cfg,
    )
    quality = evaluate_post_master_quality(ctx)
    assert quality["status"] == STATUS_PASS
    assert quality["publish_allowed"] is True
    assert "listen_delight_floors" not in quality["failed_checks"]
    assert "listen_delight_floors" not in [
        str(c.get("check_id") or "") for c in (quality.get("checks") or [])
    ]
    assert not quality.get("rubric_failed_checks")
