"""R7 (#27): PMQ honesty — live pack clarity, omit structural, floor lock.

Wraps End-F helpers; adds genuine ``gap_line_still_in_edl`` structural fail and
document-locks against lowering clarity / host_vo floors.

Also thin-asserts intentional gates:
- #29 ``host_vo_duration`` advisory (listenability floors stay honest)
- #30 no auto-S3 on advisories (anti_footgun cousin)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.aspirational_quality import (
    STRUCTURAL_PMQ_CHECKS,
    has_quality_advisories,
    publish_blocked_by_advisories,
)
from interview_mux.config import merged_config
from interview_mux.listenability_guards import listenability_guards_cfg
from interview_mux.omit_ledger import (
    OMIT_LEDGER_REL,
    air_contract_errors,
    empty_omit_ledger,
    heal_omit_ledger_air_contract,
    mint_entry,
)
from interview_mux.order_hash import bump_order_lock
from interview_mux.post_master_quality import (
    build_listener_scorecard,
    evaluate_post_master_quality,
)
from interview_mux.quality_status import STATUS_PASS
from interview_mux.run_context import RunContext
from interview_mux.seam_autopsy import _pack_conflicts
from run_fixtures import isolated_run_ctx

# Floor lock (document): do not lower these to silence Mohan / exec_11630 #27.
_LOCKED_CLARITY_FLOOR = 0.8
_LOCKED_HOST_VO_MIN = 0.04

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
    monkeypatch.setattr(
        "interview_mux.e2e_soft.e2e_quality_waivers_enabled",
        lambda meta=None: False,
    )
    monkeypatch.setattr(
        "interview_mux.aspirational_quality.is_aspirational_enabled",
        lambda _ctx=None: False,
    )
    run = isolated_run_ctx(tmp_path, "r7_pmq_honesty")
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


def test_r7_config_floors_not_lowered() -> None:
    """Document lock: PMQ clarity + host_vo floors must not be lowered to greenwash."""
    root = merged_config()
    mastering = root.get("mastering") if isinstance(root, dict) else {}
    pmq = (mastering or {}).get("post_master_quality") if isinstance(mastering, dict) else {}
    floors = (pmq or {}).get("dimension_floors") if isinstance(pmq, dict) else {}
    assert float((floors or {}).get("clarity") or 0.0) >= _LOCKED_CLARITY_FLOOR
    guards = listenability_guards_cfg()
    assert float(guards.get("host_vo_duration_min_ratio") or 0.0) >= _LOCKED_HOST_VO_MIN
    # Paperwork check is advisory since ISSUES 185; floors above stay locked.
    assert "omit_ledger_air_contract" not in STRUCTURAL_PMQ_CHECKS


def test_r7_unresolved_pack_lowers_clarity_and_floors_fail(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-F cousin: live unresolved leftovers tank clarity → scorecard floor fail."""
    monkeypatch.setattr(
        "interview_mux.aspirational_quality.is_aspirational_enabled",
        lambda _ctx=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.post_master_quality.post_master_quality_cfg",
        lambda: dict(_GOOD_FLOORS),
    )
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
    assert len(_pack_conflicts(sel)) == 8
    card = build_listener_scorecard(
        ctx, {"status": STATUS_PASS, "publish_allowed": True}
    )
    assert float(card["dimensions"]["clarity"]) < 0.80
    quality = evaluate_post_master_quality(ctx)
    assert "scorecard_dimension_floors" in quality["failed_checks"]


def test_r7_applied_leftovers_alone_do_not_tank_clarity(ctx: RunContext) -> None:
    """End-F cousin: applied leftovers (already in order) are not unresolved packs."""
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


def test_r7_omit_heal_under_freeze_then_pmq_omit_passes(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-F cousin: stale omit lock rebuild under freeze → omit contract passes."""
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
        source="r7",
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


def test_r7_genuine_gap_line_still_in_edl_is_structural(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Omitted gap line still seated in EDL → structural omit contract fail."""
    monkeypatch.setattr(
        "interview_mux.aspirational_quality.is_aspirational_enabled",
        lambda _ctx=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.post_master_quality.post_master_quality_cfg",
        lambda: {
            "block_on_feel_unavailable": False,
            "overall_min": 0.50,
            "dimension_floors": {},
        },
    )
    monkeypatch.setattr(
        "interview_mux.listen_delight.listen_delight_cfg",
        lambda: {"mode": "off", "overall_min": 0.0, "dimension_floors": {}},
    )
    _plant_master_base(ctx, clarity=0.95)
    sel = bump_order_lock(
        {"ordered_segment_ids": ["seg_b"], "version": 1}, source="r7"
    )
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    ledger = empty_omit_ledger()
    ledger["entries"] = [
        mint_entry(
            kind="gap_line_skip",
            subject_id="vo_001",
            target_segment_id="seg_b",
            decision="omit",
            reason_code="operator_force_omit",
            owner_stage="g1_vo_pickup",
            compensating_path="operator_omit",
            seq=1,
        )
    ]
    ledger["summary"] = {
        "active_count": 1,
        "by_kind": {"gap_line_skip": 1},
        "compensated_count": 1,
        "unresolved_high_salience": 0,
    }
    ledger["order_content_hash"] = sel.get("order_content_hash")
    ledger["order_lock"] = sel.get("order_lock")
    dest = ctx.final_path(*OMIT_LEDGER_REL.split("/", 1))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(ledger), encoding="utf-8")
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_001",
                    "targets_segment_id": "seg_b",
                    "skip": True,
                    "skipped_optional": True,
                }
            ]
        },
        skip_handoff=True,
    )
    # Bypass schema admit — contract check only needs line_id on a clip.
    _write_raw(
        ctx,
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_b"],
            "clips": [
                {
                    "type": "vo_pickup",
                    "line_id": "vo_001",
                    "targets_segment_id": "seg_b",
                    "placement": "before",
                    "duration_ms": 500,
                    "timeline_start_ms": 0,
                }
            ],
            "timeline_duration_ms": 500,
            "order_content_hash": sel.get("order_content_hash"),
            "order_lock": sel.get("order_lock"),
        },
    )
    errors = air_contract_errors(ctx)
    assert any(e.startswith("omit_ledger_gap_line_still_in_edl:") for e in errors)
    quality = evaluate_post_master_quality(ctx)
    omit_check = next(
        c for c in quality["checks"] if c.get("check_id") == "omit_ledger_air_contract"
    )
    # Still detected and reported, but advisory (ISSUES 185).
    assert omit_check.get("passed") is False
    assert "omit_ledger_air_contract" not in (quality.get("structural_failed_checks") or [])


def test_r7_host_vo_duration_advisory_intentional() -> None:
    """#29 INTENTIONAL_GATE: host_vo_duration floor stays advisory — no auto-thicken.

    Softening ``host_vo_duration_min_ratio`` or auto-thickening under hard freeze
    recreates thrash vs narrative economy. Documented in residual-closure-constitution.
    """
    guards = listenability_guards_cfg()
    assert float(guards["host_vo_duration_min_ratio"]) >= _LOCKED_HOST_VO_MIN
    assert float(guards["host_vo_duration_max_ratio"]) > float(
        guards["host_vo_duration_min_ratio"]
    )
    # Floor is an aspirational listenability contract surface, not a hard PMQ structural.
    assert "host_vo_duration" not in STRUCTURAL_PMQ_CHECKS


def test_r7_no_auto_s3_on_advisories(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    """#30 INTENTIONAL_GATE cousin: advisories block remote publish (anti_footgun)."""
    monkeypatch.setenv("INTERVIEW_MUX_REQUIRE_OPERATOR_PUBLISH_ADVISORY", "1")

    def _patch(meta):
        meta["quality_advisories"] = [{"code": "rubric"}]
        meta["aspirational_proceeded"] = True

    ctx.mutate_run_meta(_patch)
    assert has_quality_advisories(ctx)
    assert publish_blocked_by_advisories(ctx) is True
