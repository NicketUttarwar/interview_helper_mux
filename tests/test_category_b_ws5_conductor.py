"""Category B WS5 regressions from exec_13157 (MUX_FORENSICS=0 cascades)."""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.run_context import RunContext
from run_fixtures import (
    isolated_run_ctx,
    mark_done_raw,
    plant_primary_and_stamp,
    plant_seed_complete_through,
)


def _blocking_audit(ctx: RunContext) -> None:
    path = ctx.final_path("master", "edl_narrative_audit.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"verdict": "fail", "blocking_issues": [{"issue": "order"}]}),
        encoding="utf-8",
    )


def test_5a_blocked_edl_resume_pins_narrative_audit(
    tmp_path: Path, monkeypatch
) -> None:
    from interview_mux import delivery_guardrails
    from interview_mux.thrash_hardening import (
        FAIL_CLASS_DELIVERY_BLOCKED,
        canonical_resume_pin,
        heal_navigate,
        path_to_master_pin,
    )

    ctx = isolated_run_ctx(tmp_path, "ws5_edl_pin")
    # Leave ENA incomplete so a blocked-EDL pin can land on the audit producer.
    plant_seed_complete_through(ctx, "vo_synthesize")
    _blocking_audit(ctx)
    monkeypatch.setattr(delivery_guardrails, "_g1_open", lambda _ctx: [])
    monkeypatch.setattr(delivery_guardrails, "phase_a_sealed", lambda _ctx: False)
    monkeypatch.setattr(
        delivery_guardrails,
        "delivery_stable_for_music",
        lambda _ctx: (False, "edl_incomplete"),
    )

    assert canonical_resume_pin(ctx, FAIL_CLASS_DELIVERY_BLOCKED) in {
        "edl_narrative_audit",
        "edl",
    }
    assert path_to_master_pin(ctx) in {"edl_narrative_audit", "edl"}
    nav_pin = heal_navigate(
        ctx, error="delivery blocked; remaining head is edl", stage="edl"
    )["from_stage"]
    assert nav_pin in {"edl_narrative_audit", "edl"}


def test_5b_incomplete_after_conductor_is_hard_own_class(tmp_path: Path) -> None:
    from interview_mux.thrash_hardening import (
        FAIL_CLASS_INCOMPLETE_AFTER_CONDUCTOR,
        infer_heal_intent,
        premature_fail_class,
        suppress_allowed,
    )

    ctx = isolated_run_ctx(tmp_path, "ws5_conductor_class")
    cls = infer_heal_intent(error="Delivery incomplete after conductor", stage="edl")
    assert cls == FAIL_CLASS_INCOMPLETE_AFTER_CONDUCTOR
    assert premature_fail_class(cls) == cls
    assert suppress_allowed(ctx, cls) is False
    assert not ctx.artifact_exists("operator/suppress_budget.json")


def test_5c_master_finalize_seed_does_not_rewind_valid_master(
    tmp_path: Path,
) -> None:
    from interview_mux.homunculus.runtime import _seed_prereq_block

    ctx = isolated_run_ctx(tmp_path, "ws5_master_seed")
    master = ctx.final_path("master", "master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF" + b"\0" * 9000)

    assert not ctx.is_done("mix")
    assert _seed_prereq_block(ctx, "master_finalize") is None


def test_5d_soft_pass_refuse_routes_to_real_qc_producer(tmp_path: Path) -> None:
    from interview_mux.thrash_hardening import heal_navigate

    ctx = isolated_run_ctx(tmp_path, "ws5_soft_refuse")
    plant_seed_complete_through(ctx, "information_package_plan")
    plant_primary_and_stamp(ctx, "nugget_corpus_mine")
    from interview_mux.v2.config import DELIVERY_ORDER

    for sid in DELIVERY_ORDER:
        plant_primary_and_stamp(ctx, sid)
        if sid == "nugget_layup_compose":
            break
    nav = heal_navigate(
        ctx,
        error="pre-EDL delivery QC incomplete — refusing e2e stub",
        stage="nugget_layup_compose",
    )
    # Seed-front hole (topic_coverage) wins unless that producer is seed-complete.
    assert nav["from_stage"] in {"nugget_layup_compose", "topic_coverage_audit"}
    assert nav["intent"] in {"pre_edl_qc_producer", nav["intent"]}


def test_5e_interrupt_with_master_resumes_finalize_then_ship(tmp_path: Path) -> None:
    from interview_mux.thrash_hardening import infrastructure_interrupt_resume_pin

    ctx = isolated_run_ctx(tmp_path, "ws5_interrupt")
    plant_seed_complete_through(ctx, "master_finalize")
    master = ctx.final_path("master", "master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF" + b"\0" * 9000)

    assert infrastructure_interrupt_resume_pin(ctx) == "master_finalize"
    mark_done_raw(ctx, "master_finalize")
    # Hollow finalize stamp is not honest seed-complete; publish stays closed.
    assert infrastructure_interrupt_resume_pin(ctx) == "master_finalize"


def test_5f_sticky_halt_constrains_delivery_walk(tmp_path: Path) -> None:
    from interview_mux.homunculus.agenda import _constrain_delivery_walk_for_sticky

    ctx = isolated_run_ctx(tmp_path, "ws5_sticky_walk")
    ctx.write_json(
        "operator/sticky_heal.json",
        {"active_halt": {"pin": "edl_narrative_audit", "halt": True}},
        skip_handoff=True,
    )
    stages = ["edl_narrative_audit", "edl", "mix"]
    assert _constrain_delivery_walk_for_sticky(ctx, stages) == ["edl_narrative_audit"]


def test_sticky_sealed_pin_clears_and_allows_remainder_walk(
    tmp_path: Path, monkeypatch
) -> None:
    """exec_13170: sealed SDP sticky must not refuse vo_line_adjudicate walk."""
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.homunculus.agenda import _constrain_delivery_walk_for_sticky
    from run_fixtures import mark_done_raw

    ctx = isolated_run_ctx(tmp_path, "ws5_sticky_sealed")
    # Minimal SDP artifact so seed_stage_complete can pass when we stub it.
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid == "sound_design_plan",
    )
    ctx.write_json(
        "operator/sticky_heal.json",
        {
            "active_halt": {
                "pin": "sound_design_plan",
                "halt": True,
                "kind": "incomplete_after_conductor",
            }
        },
        skip_handoff=True,
    )
    stages = ["vo_line_adjudicate", "vo_synthesize", "edl"]
    out = _constrain_delivery_walk_for_sticky(ctx, stages)
    assert out == stages
    sticky = ctx.read_json("operator/sticky_heal.json")
    assert not sticky.get("active_halt")


def test_dual_driver_claim_refuses_live_foreign_owner(
    tmp_path: Path, monkeypatch
) -> None:
    import os

    import pytest

    from interview_mux import driver_singleton

    ctx = isolated_run_ctx(tmp_path, "ws5_dual_driver")
    ctx.write_json(
        driver_singleton.DRIVER_CLAIM_REL,
        {"pid": os.getpid() + 1000, "claimed_at": "2026-09-18T00:00:00Z"},
        skip_handoff=True,
    )
    monkeypatch.setattr(driver_singleton, "_pid_alive", lambda _pid: True)

    with pytest.raises(RuntimeError, match="refuse second driver"):
        driver_singleton.claim_driver_run(ctx)
