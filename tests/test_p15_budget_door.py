"""p15-budget-door (§5.3): the driver walk goes through the caps, exemptions are narrow.

Evidence from exec_11871: ``audio_probe_build`` halted correctly at 3/3 on the
conductor path (``mastering/homunculus/limit_exhausted.json``) while ``mix`` reached
28 dispatches against ``max_mix_cycles: 3`` on the driver path — because
``count_identity`` returns 0 while a stage is not done, and the junction remaster
unmarks ``.stage_done/mix`` between iterations.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.dispatch_door import evaluate_dispatch
from interview_mux.homunculus.budget import (
    AUDIO_MUTATING,
    CTA_COVER_EXEMPT_IDENTITIES,
    EXEMPTION_GRACE,
    LimitExhausted,
    attempt_cap,
    check_dispatch,
    count_attempts,
    dispatch_cap_refusal,
    exemption_for,
)
from interview_mux.homunculus.ledger import append_ledger, count_identity, read_ledger
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, mark_done_raw


def _driver_ctx(tmp_path: Path, name: str) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.2.0",
            "homunculus_kind": "homunculus",
            "homunculus_control_plane": "deterministic",
            "run_mode": "full-auto",
            "full_auto": True,
        },
        skip_handoff=True,
    )
    return ctx


def _dispatch_rows(ctx: RunContext, stage: str, n: int) -> None:
    for _ in range(n):
        append_ledger(ctx, {"kind": "stage", "identity": stage, "status": "started"})
        append_ledger(ctx, {"kind": "stage", "identity": stage, "status": "done"})


def test_count_attempts_sees_what_count_identity_hides(tmp_path: Path) -> None:
    ctx = _driver_ctx(tmp_path, "door_counts")
    _dispatch_rows(ctx, "mix", 4)
    # The measured bypass: no .stage_done/mix, so the cap counter reads zero.
    assert count_identity(ctx, "mix") == 0
    assert count_attempts(ctx, "mix") == 4


def test_walk_door_refuses_mix_at_max_mix_cycles(tmp_path: Path) -> None:
    ctx = _driver_ctx(tmp_path, "door_mix_cap")
    cap, reason = attempt_cap("mix")
    assert (cap, reason) == (3, "max_mix_cycles")
    _dispatch_rows(ctx, "mix", cap - 1)
    assert dispatch_cap_refusal(ctx, "mix") is None
    _dispatch_rows(ctx, "mix", 1)
    hit = dispatch_cap_refusal(ctx, "mix")
    assert hit is not None
    assert hit[0] == "max_mix_cycles"
    assert hit[1]["used"] == cap


def test_cap_hit_is_a_verdict_not_an_exception(tmp_path: Path) -> None:
    """D1: a spent cap must not strand the walk with a traceback."""
    ctx = _driver_ctx(tmp_path, "door_verdict")
    _dispatch_rows(ctx, "junction_snip_qa", 3)
    verdict = evaluate_dispatch(ctx, "junction_snip_qa", source="delivery_walk_to_master")
    assert verdict.refused
    assert verdict.reason == "max_invokes_per_identity"


def test_door_is_inert_for_a_manual_run(tmp_path: Path) -> None:
    """A human clicking Re-run is a decision; the door governs driver dispatches."""
    ctx = isolated_run_ctx(tmp_path, "door_manual")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "run_mode": "manual"},
        skip_handoff=True,
    )
    _dispatch_rows(ctx, "mix", 9)
    assert evaluate_dispatch(ctx, "mix", source="operator").allowed


def test_no_exemption_covers_an_audio_mutating_stage(tmp_path: Path, monkeypatch) -> None:
    ctx = _driver_ctx(tmp_path, "door_audio_exempt")
    # Both exemptions active at once: a remediation plan naming every audio stage,
    # and the CTA cover regenerate scope.
    ctx.write_json(
        "operator/remediation_plan.json",
        {
            "version": 1,
            "active": True,
            "error_class": "vo_contract_repair",
            "consumer_stage": "mix",
            "allowed_rerun_stages": sorted(AUDIO_MUTATING),
        },
        skip_handoff=True,
    )
    monkeypatch.setattr(ctx, "_cta_cover_regenerate_inner", True, raising=False)
    for stage in sorted(AUDIO_MUTATING):
        assert exemption_for(ctx, stage, "stage") is None, stage
        _dispatch_rows(ctx, stage, 3)
        assert dispatch_cap_refusal(ctx, stage, kind="stage") is not None, stage
    # check_dispatch counts only finished work, so it needs the marker to see the
    # 3 dispatches at all — the door above is what covers the unmarked case.
    mark_done_raw(ctx, "mix")
    with pytest.raises(LimitExhausted):
        check_dispatch(ctx, identity="mix", kind="stage")


def test_policy_remediation_exemption_is_named_bounded_and_logged(tmp_path: Path) -> None:
    ctx = _driver_ctx(tmp_path, "door_policy_exempt")
    ctx.write_json(
        "operator/remediation_plan.json",
        {
            "version": 1,
            "active": True,
            "error_class": "layup_stale",
            "consumer_stage": "edl",
            "allowed_rerun_stages": ["nugget_layup_compose"],
        },
        skip_handoff=True,
    )
    cap, _ = attempt_cap("nugget_layup_compose")
    _dispatch_rows(ctx, "nugget_layup_compose", cap)
    # Named by the plan: grace applies, and the exemption is on the ledger.
    assert dispatch_cap_refusal(ctx, "nugget_layup_compose") is None
    rows = [r for r in read_ledger(ctx) if r.get("kind") == "budget_exemption"]
    assert rows and rows[-1]["exemption"] == "policy_remediation_plan"
    assert rows[-1]["stage"] == "nugget_layup_compose"
    # Not named by the plan: the plan no longer voids every cap in the run.
    _dispatch_rows(ctx, "transitions", cap)
    assert dispatch_cap_refusal(ctx, "transitions") is not None
    # Grace is bounded — it raises the cap, it does not remove it.
    _dispatch_rows(ctx, "nugget_layup_compose", EXEMPTION_GRACE)
    hit = dispatch_cap_refusal(ctx, "nugget_layup_compose")
    assert hit is not None and hit[1]["exhausted_with_grace"] is True


def test_cta_cover_exemption_is_a_named_identity_set(tmp_path: Path, monkeypatch) -> None:
    ctx = _driver_ctx(tmp_path, "door_cta_exempt")
    assert CTA_COVER_EXEMPT_IDENTITIES == frozenset({"run_chatterbox", "run_s2s"})
    monkeypatch.setattr(ctx, "_cta_cover_regenerate_inner", True, raising=False)
    # Host-tool identity inside the cover scope: bounded grace, logged.
    assert exemption_for(ctx, "run_chatterbox", "host") is not None
    # Anything else in the run is untouched by the cover scope.
    assert exemption_for(ctx, "edl", "stage") is None
    assert exemption_for(ctx, "mix", "stage") is None
