"""End-D: claim-inventory paperwork vs live incomplete-cut (exec_023 deadlock).

Stale junction ``applied`` stamps must not map to incomplete_cut_unresolved /
junction ladder while speech-first remaster is owed to mix.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.heal_routing import classify_heal_error
from interview_mux.junction_snip_qa import reconcile_junction_claim_inventory
from interview_mux.nle_state import load_nle, save_nle
from interview_mux.order_hash import stamp_order_hash
from interview_mux.publishability_boundary import validate_publishability
from interview_mux.delivery_guardrails import CriticalResidualView
from interview_mux.recovery_controller import (
    classify_error_class,
    playbook_junction_claim_inventory_stale,
)
from interview_mux.run_context import RunContext
from interview_mux.seam_autopsy import verify_commitment
from interview_mux.thought_complete_recut import apply_thought_complete_to_clips
from interview_mux.write_staging import enter_stage_staging, exit_stage_staging
from run_fixtures import isolated_run_ctx


def _plant_claim_diverge(ctx: RunContext, *, edl_end: int = 896370) -> None:
    master = ctx.run_dir / "master"
    master.mkdir(parents=True, exist_ok=True)
    selection = stamp_order_hash(
        {
            "version": 1,
            "ordered_segment_ids": ["seg_023", "seg_024"],
            "excluded_segment_ids": ["seg_025"],
        }
    )
    edl = stamp_order_hash(
        {
            "version": 1,
            "ordered_segment_ids": ["seg_023", "seg_024"],
            "timeline_duration_ms": 40000,
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_023",
                    "source_start_ms": 870980,
                    "source_end_ms": edl_end,
                    "timeline_start_ms": 0,
                    "duration_ms": edl_end - 870980,
                },
                {
                    "type": "speech",
                    "segment_id": "seg_024",
                    "source_start_ms": 896420,
                    "source_end_ms": 904970,
                    "timeline_start_ms": edl_end - 870980,
                    "duration_ms": 8550,
                },
            ],
        }
    )
    # Raw fixture writes (skip schema) — same pattern as test_i11_premix_*.
    (master / "selection.json").write_text(json.dumps(selection), encoding="utf-8")
    (master / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    (master / "junction_snip_qa.json").write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-10-06T00:00:00Z",
                "critical_residuals": 0,
                "critical_residual_count": 0,
                "blocking_reasons": [],
                "applied": [
                    {
                        "kind": "on_a_roll",
                        "severity": "critical",
                        "segment_id": "seg_023",
                        "clip_index": 0,
                        "action": "thought_complete_recut",
                        "status": "applied",
                        "keep_end_ms": 909500,
                        "detail": {
                            "keep_end_ms": 909500,
                            "consumed_segment_ids": ["seg_025"],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (master / "seam_autopsy.json").write_text(
        json.dumps(
            {
                "version": 1,
                "blocking_reasons": ["claimed_repairs_missing_from_edl"],
                "commitment": {
                    "status": "diverged",
                    "reasons": ["claimed_repairs_missing_from_edl"],
                    "unresolved_repair_keys": ["0:thought_complete_recut:seg_023"],
                    "repairs_claimed": 1,
                    "repairs_committed": 0,
                },
                "seams": [],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "claim_inventory_stale")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.has_critical_residuals",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [],
    )
    _plant_claim_diverge(run)
    return run


def test_reconcile_supersedes_stale_applied_when_live_clean(ctx: RunContext) -> None:
    ok = reconcile_junction_claim_inventory(ctx)
    assert ok is True
    report = ctx.read_json("master/junction_snip_qa.json")
    applied = report["applied"][0]
    assert applied["status"] == "superseded"
    assert applied["supersede_reason"] == "claim_inventory_reconcile_edl_mismatch"
    commitment = verify_commitment(ctx, report)
    assert "claimed_repairs_missing_from_edl" not in (commitment.get("reasons") or [])


def test_reconcile_refuses_supersede_when_live_critical(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [
            {
                "kind": "on_a_roll",
                "severity": "critical",
                "segment_id": "seg_023",
                "action": "thought_complete_recut",
            }
        ],
    )
    ok = reconcile_junction_claim_inventory(ctx)
    assert ok is False
    report = ctx.read_json("master/junction_snip_qa.json")
    assert report["applied"][0]["status"] == "applied"


def test_premix_classifies_claim_inventory_not_incomplete_cut(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.publishability_boundary import _check_critical_junction

    # Force classify path without auto-heal clearing the violation first.
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.reconcile_junction_claim_inventory",
        lambda _ctx: False,
    )
    enter_stage_staging("mix")
    try:
        junction_violations = _check_critical_junction(ctx)
        report = validate_publishability(ctx, checkpoint="pre_mix")
    finally:
        exit_stage_staging()
    j_classes = [v.error_class for v in junction_violations]
    assert "incomplete_cut_unresolved" not in j_classes
    assert "junction_claim_inventory_stale" in j_classes
    assert "incomplete_cut_unresolved" not in [v.error_class for v in report.violations]


def test_premix_auto_reconcile_clears_claim_inventory(ctx: RunContext) -> None:
    enter_stage_staging("mix")
    try:
        report = validate_publishability(ctx, checkpoint="pre_mix")
    finally:
        exit_stage_staging()
    assert not any(
        v.error_class
        in {"junction_claim_inventory_stale", "incomplete_cut_unresolved"}
        for v in report.violations
    ), [f"{v.error_class}:{v.detail}" for v in report.violations]


def test_heal_routes_claim_inventory_to_mix_not_junction(ctx: RunContext) -> None:
    err = (
        "publishability blocked at pre_mix: junction_claim_inventory_stale — "
        "claimed_repairs_missing_from_edl"
    )
    route = classify_heal_error(err, ctx, stage="mix")
    assert route is not None
    assert route.from_stage == "mix"
    assert route.action == "claim_reconcile"
    assert route.from_stage != "junction_snip_qa"


def test_recovery_classifies_claimed_repairs_as_claim_inventory() -> None:
    exc = RuntimeError(
        "publishability blocked at pre_mix: incomplete_cut_unresolved — "
        "claimed_repairs_missing_from_edl"
    )
    assert classify_error_class("mix", exc) == "junction_claim_inventory_stale"


def test_playbook_claim_inventory_resumes_mix(ctx: RunContext) -> None:
    artifacts = playbook_junction_claim_inventory_stale(ctx)
    assert not any("unresolved" in str(a) for a in artifacts)
    assert any("mix" in str(a) for a in artifacts)


def test_reconcile_aligns_nle_override_to_edl(ctx: RunContext) -> None:
    save_nle(
        ctx,
        {
            "segment_overrides": {
                "seg_023": {"start_ms": 870980, "end_ms": 957750},
            },
            "junction_nudge_history": {},
        },
    )
    assert reconcile_junction_claim_inventory(ctx) is True
    nle = load_nle(ctx)
    ov = nle["segment_overrides"]["seg_023"]
    assert int(ov["end_ms"]) == 896370
    assert ov.get("align_reason") == "claim_inventory_reconcile"


def test_apply_consumes_air_order_neighbor_not_ghost() -> None:
    clips = [
        {
            "type": "speech",
            "segment_id": "seg_023",
            "source_start_ms": 870980,
            "source_end_ms": 894080,
            "duration_ms": 23100,
        },
        {
            "type": "speech",
            "segment_id": "seg_024",
            "source_start_ms": 896420,
            "source_end_ms": 904970,
            "duration_ms": 8550,
        },
    ]
    finding = {
        "segment_id": "seg_023",
        "kind": "on_a_roll",
        "action": "thought_complete_recut",
        "detail": {
            "keep_end_ms": 909500,
            "remainder_start_ms": 910060,
            # Ghost / off-air consume target (exec_023).
            "consumed_segment_ids": ["seg_025"],
        },
    }
    out, overrides, changed = apply_thought_complete_to_clips(
        clips, finding, overrides={}, excluded=set(), exclude_reasons={}
    )
    assert changed is True
    by_id = {c["segment_id"]: c for c in out}
    assert by_id["seg_023"]["source_end_ms"] == 909500
    assert "seg_024" not in by_id  # swallowed as continuum neighbor
    assert overrides.get("seg_024", {}).get("excluded") is True
    assert finding["detail"]["consumed_segment_ids"] == ["seg_024"]
    assert "seg_025" not in finding["detail"]["consumed_segment_ids"]


def test_live_critical_still_incomplete_cut(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [
            {
                "kind": "on_a_roll",
                "severity": "critical",
                "segment_id": "seg_023",
            }
        ],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.has_critical_residuals",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.critical_residual_view",
        lambda _ctx: CriticalResidualView(
            count=1, kinds=("on_a_roll",), sources=("live",)
        ),
    )
    enter_stage_staging("mix")
    try:
        report = validate_publishability(ctx, checkpoint="pre_mix")
    finally:
        exit_stage_staging()
    assert any(v.error_class == "incomplete_cut_unresolved" for v in report.violations)
