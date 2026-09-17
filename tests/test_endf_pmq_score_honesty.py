"""End-F: PMQ ship score honesty — live clarity + omit (MUX_FORENSICS=0)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.omit_ledger import (
    OMIT_LEDGER_REL,
    air_contract_errors,
    heal_omit_ledger_air_contract,
)
from interview_mux.order_hash import bump_order_lock
from interview_mux.post_master_quality import (
    QUALITY_REL,
    build_listener_scorecard,
    evaluate_post_master_quality,
    require_publishable,
)
from interview_mux.quality_status import STATUS_PASS
from interview_mux.run_context import RunContext
from interview_mux.seam_autopsy import _pack_conflicts
from run_fixtures import isolated_run_ctx

_GOOD_FLOORS = {
    "block_on_feel_unavailable": False,
    "overall_min": 0.50,
    "dimension_floors": {
        "flow": 0.50,
        "clarity": 0.80,
        "music_completeness": 0.50,
        "synthetic_fit": 0.50,
        "native_respect": 0.50,
    },
}


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    # Production honesty: no e2e soft scorecard waiver.
    monkeypatch.setattr(
        "interview_mux.e2e_soft.e2e_quality_waivers_enabled",
        lambda meta=None: False,
    )
    monkeypatch.setattr(
        "interview_mux.aspirational_quality.is_aspirational_enabled",
        lambda _ctx=None: False,
    )
    run = isolated_run_ctx(tmp_path, "endf_pmq_honesty")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _write_raw(ctx: RunContext, rel: str, doc: dict) -> None:
    path = ctx.final_path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _plant_master_base(ctx: RunContext, *, clarity: float = 0.95) -> None:
    master = ctx.final_path("master", "master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF" + b"\x00" * 2048)
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
                "information_clarity": clarity,
                "music_completeness": 0.95,
                "sonic_density_fit": 0.9,
            },
            "guides": {"synthetic_input_share": 0.35},
            "seams": [],
            "blocking_reasons": [],
            "pack_conflicts": [],
        },
    )
    _write_raw(ctx, "master/render_ledger.json", {"version": 1})
    _write_raw(
        ctx,
        "master/junction_snip_qa.json",
        {"residual_findings": [], "blocking_reasons": []},
    )


def test_endf_applied_leftovers_do_not_tank_clarity_scorecard(ctx: RunContext) -> None:
    """Applied leftover inserts must not lower scorecard clarity (unresolved-only)."""
    _plant_master_base(ctx, clarity=0.95)
    sel = {
        "ordered_segment_ids": ["seg_010", "seg_012", "seg_014"],
        "_meta": {
            "repairs": [
                {
                    "action": "insert_leftovers_before_finale_span",
                    "count": 3,
                    "ids": ["seg_010", "seg_012", "seg_014"],
                }
            ]
        },
    }
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    assert _pack_conflicts(sel) == []
    card = build_listener_scorecard(
        ctx, {"status": STATUS_PASS, "publish_allowed": True}
    )
    assert float(card["dimensions"]["clarity"]) >= 0.90


def test_endf_unresolved_pack_conflicts_lower_live_clarity(ctx: RunContext) -> None:
    """Stale high autopsy clarity must not hide live unresolved leftovers."""
    _plant_master_base(ctx, clarity=0.95)
    sel = {
        "ordered_segment_ids": ["seg_010"],
        "_meta": {
            "repairs": [
                {
                    "action": "insert_leftovers_before_finale_span",
                    "count": 5,
                    "ids": ["seg_a", "seg_b", "seg_c", "seg_d", "seg_e"],
                }
            ]
        },
    }
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    assert len(_pack_conflicts(sel)) == 1
    assert _pack_conflicts(sel)[0]["count"] == 5
    card = build_listener_scorecard(
        ctx, {"status": STATUS_PASS, "publish_allowed": True}
    )
    # 0.95 flow - 0.04*1 pack row = ~0.91 still high; use many rows via count in formula
    # build_autopsy uses pack_n = len(conflicts) = 1 row → clarity ~0.91.
    # Force more rows by multiple repair actions.
    sel["_meta"]["repairs"] = [
        {
            "action": "insert_leftovers_before_finale_span",
            "count": 1,
            "ids": [f"seg_x{i}"],
        }
        for i in range(8)
    ]
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    assert len(_pack_conflicts(sel)) == 8
    card = build_listener_scorecard(
        ctx, {"status": STATUS_PASS, "publish_allowed": True}
    )
    assert float(card["dimensions"]["clarity"]) < 0.80


def test_endf_scorecard_floors_reflect_live_clarity(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live unresolved pack conflicts must surface on scorecard floors (no soft)."""
    monkeypatch.setattr(
        "interview_mux.aspirational_quality.is_aspirational_enabled",
        lambda _ctx=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.post_master_quality.post_master_quality_cfg",
        lambda: dict(_GOOD_FLOORS),
    )
    # Soften delight so it does not dominate failed_checks noise.
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        lambda: {"mode": "off", "overall_min": 0.0, "dimension_floors": {}},
    )
    _plant_master_base(ctx, clarity=0.95)
    sel = {
        "ordered_segment_ids": ["seg_010"],
        "_meta": {
            "repairs": [
                {
                    "action": "insert_leftovers_before_finale_span",
                    "count": 1,
                    "ids": [f"seg_x{i}"],
                }
                for i in range(8)
            ]
        },
    }
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    dest = ctx.final_path(*OMIT_LEDGER_REL.split("/", 1))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [],
                "summary": {
                    "active_count": 0,
                    "by_kind": {},
                    "unresolved_high_salience": 0,
                    "compensated_count": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    card = build_listener_scorecard(
        ctx, {"status": STATUS_PASS, "publish_allowed": True}
    )
    assert float(card["dimensions"]["clarity"]) < 0.80
    quality = evaluate_post_master_quality(ctx)
    assert "scorecard_dimension_floors" in quality["failed_checks"]
    assert "scorecard_dimension_floors" in (quality.get("rubric_failed_checks") or [])
    # Rubric under aspirational may still allow publish — honesty is the floor fail.
    assert quality.get("publish_allowed") is True



def test_endf_omit_heal_then_pmq_omit_contract_passes(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.seat_authority.soft_freeze_active",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.gate_seat_mutation",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "interview_mux.post_master_quality.post_master_quality_cfg",
        lambda: {
            "block_on_feel_unavailable": False,
            "overall_min": 0.50,
            "dimension_floors": {},
        },
    )
    _plant_master_base(ctx, clarity=0.95)
    sel = bump_order_lock(
        {"ordered_segment_ids": ["seg_002", "seg_005"], "version": 1},
        source="endf",
    )
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    stale = {
        "version": 1,
        "order_content_hash": "deadbeefdeadbeef",
        "order_lock": {
            "version": 1,
            "revision": 1,
            "authority": "master/selection.json",
            "ordered_segment_ids": ["seg_002"],
            "order_content_hash": "deadbeefdeadbeef",
            "created_by": "test",
        },
        "entries": [],
        "summary": {
            "active_count": 0,
            "by_kind": {},
            "unresolved_high_salience": 0,
            "compensated_count": 0,
        },
    }
    dest = ctx.final_path(*OMIT_LEDGER_REL.split("/", 1))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(stale), encoding="utf-8")
    assert "omit_ledger_order_lock_stale" in air_contract_errors(ctx)
    assert heal_omit_ledger_air_contract(ctx).get("healed") is True
    quality = evaluate_post_master_quality(ctx)
    omit_check = next(
        c for c in quality["checks"] if c.get("check_id") == "omit_ledger_air_contract"
    )
    assert omit_check.get("passed") is True


def test_endf_require_publishable_refreshes_before_reeval(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    refreshes: list[str] = []

    def _refresh(_ctx):
        refreshes.append("refreshed")
        return {"version": 1}

    monkeypatch.setattr(
        "interview_mux.post_master_quality.refresh_live_post_master_autopsy",
        _refresh,
    )
    monkeypatch.setattr(
        "interview_mux.post_master_quality.evaluate_post_master_quality",
        lambda _ctx: {
            "version": 1,
            "publish_allowed": True,
            "status": STATUS_PASS,
            "failed_checks": [],
            "structural_failed_checks": [],
            "checks": [],
        },
    )
    monkeypatch.setattr(
        "interview_mux.post_master_quality.persist_post_master_quality",
        lambda *_a, **_k: None,
    )
    _write_raw(
        ctx,
        QUALITY_REL,
        {"version": 1, "publish_allowed": False, "status": "fail", "failed_checks": ["x"]},
    )
    require_publishable(ctx, stage="podcast_publish")
    assert refreshes == ["refreshed"]
