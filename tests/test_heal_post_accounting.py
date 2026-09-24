"""Post-Heal Accounting B+ (MUX_FORENSICS=0) — HC-POST-HEAL-BUDGET P1–P11."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from interview_mux.heal_post_accounting import (
    POST_HEAL_EPOCH_ALLOW,
    finalize_post_heal_accounting,
    reclaim_class_signature_on_predicate_progress,
)
from interview_mux.identical_failures import (
    IDENTICAL_FAILURES_REL,
    read_identical_failures,
    record_class_failure,
)
from interview_mux.recovery_controller import (
    _append_action,
    attempt_count,
    signature_key,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture(autouse=True)
def _forensics_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")


@pytest.fixture
def ctx(tmp_path: Path) -> RunContext:
    return isolated_run_ctx(tmp_path, "post_heal_acct")


def test_p1_recovered_does_not_mirror(ctx: RunContext) -> None:
    sig = signature_key("edl", "vo_seated_coverage")
    _append_action(
        ctx,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signature": sig,
            "playbook_id": "vo_seated_coverage",
            "status": "recovered",
        },
    )
    assert attempt_count(ctx, sig) == 0
    doc = read_identical_failures(ctx)
    for row in (doc.get("signatures") or {}).values():
        if not isinstance(row, dict):
            continue
        if str(row.get("error_class") or "") == "vo_seated_coverage":
            assert int(row.get("count") or 0) == 0


def test_p2_recovered_then_escalate_fuels(ctx: RunContext) -> None:
    sig = signature_key("edl", "vo_seated_coverage")
    _append_action(
        ctx,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signature": sig,
            "playbook_id": "vo_seated_coverage",
            "status": "recovered",
        },
    )
    assert attempt_count(ctx, sig) == 0
    _append_action(
        ctx,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signature": sig,
            "playbook_id": "vo_seated_coverage",
            "status": "escalate",
        },
    )
    assert attempt_count(ctx, sig) >= 1


def test_p3_predicate_flip_clears_preheal_count(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.stage_predicate_token",
        lambda _ctx, _stage: "new_token",
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.predicate_flipped",
        lambda _ctx, _stage, prior: str(prior or "") != "new_token",
    )
    row = record_class_failure(
        ctx,
        failed_stage="edl",
        error_class="vo_seated_coverage",
        resume_attempted="edl",
    )
    # Force prior token + count=2 as if pre-heal thrash.
    doc = read_identical_failures(ctx)
    sig = str(row.get("signature") or "")
    stored = dict((doc.get("signatures") or {}).get(sig) or row)
    stored["count"] = 2
    stored["predicate_token"] = "old_token"
    stored["halt"] = False
    doc.setdefault("signatures", {})[sig] = stored
    ctx.write_json(IDENTICAL_FAILURES_REL, doc, skip_handoff=True)

    cleared = reclaim_class_signature_on_predicate_progress(
        ctx, failed_stage="edl", error_class="vo_seated_coverage"
    )
    assert cleared >= 1
    after = read_identical_failures(ctx)
    cleared_row = (after.get("signatures") or {}).get(sig) or {}
    assert int(cleared_row.get("count") or 0) == 0
    assert cleared_row.get("halt") is False


def test_p3_anti_c_recovered_alone_no_clear(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.stage_predicate_token",
        lambda _ctx, _stage: "same_token",
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.predicate_flipped",
        lambda _ctx, _stage, prior: False,
    )
    row = record_class_failure(
        ctx,
        failed_stage="edl",
        error_class="vo_seated_coverage",
    )
    doc = read_identical_failures(ctx)
    sig = str(row.get("signature") or "")
    stored = dict((doc.get("signatures") or {}).get(sig) or row)
    stored["count"] = 2
    stored["predicate_token"] = "same_token"
    doc.setdefault("signatures", {})[sig] = stored
    ctx.write_json(IDENTICAL_FAILURES_REL, doc, skip_handoff=True)

    result = finalize_post_heal_accounting(
        ctx,
        signature=signature_key("edl", "vo_seated_coverage"),
        status="recovered",
        playbook_id="vo_seated_coverage",
    )
    assert result.mirrored is False
    assert result.epoch_stamped is False
    assert result.signature_cleared == 0
    after = (read_identical_failures(ctx).get("signatures") or {}).get(sig) or {}
    assert int(after.get("count") or 0) == 2


def test_anti_c_epoch_allow_empty() -> None:
    assert len(POST_HEAL_EPOCH_ALLOW) == 0


def test_p9_unstick_does_not_zero_identical(ctx: RunContext) -> None:
    row = record_class_failure(
        ctx,
        failed_stage="edl",
        error_class="vo_seated_coverage",
    )
    sig = str(row.get("signature") or "")
    doc = read_identical_failures(ctx)
    stored = dict((doc.get("signatures") or {}).get(sig) or row)
    stored["count"] = 2
    doc.setdefault("signatures", {})[sig] = stored
    ctx.write_json(IDENTICAL_FAILURES_REL, doc, skip_handoff=True)

    from interview_mux.delivery_unstick import run_delivery_unstick

    run_delivery_unstick(ctx)
    after = (read_identical_failures(ctx).get("signatures") or {}).get(sig) or {}
    assert int(after.get("count") or 0) == 2


def test_p11_entrypoint_is_append_action(ctx: RunContext) -> None:
    """Recovered accounting must go through finalize_post_heal_accounting."""
    import interview_mux.heal_post_accounting as pha

    calls: list[str] = []
    real = pha.finalize_post_heal_accounting

    def _wrap(*args: object, **kwargs: object) -> object:
        calls.append(str(kwargs.get("status") or ""))
        return real(*args, **kwargs)

    pha.finalize_post_heal_accounting = _wrap  # type: ignore[assignment]
    try:
        # Re-bind recovery_controller's import path via _append_action lazy import.
        sig = signature_key("edl", "empty_snap")
        _append_action(
            ctx,
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "signature": sig,
                "playbook_id": "empty_snap",
                "status": "recovered",
            },
        )
    finally:
        pha.finalize_post_heal_accounting = real  # type: ignore[assignment]
    assert "recovered" in calls


def test_p10_recovered_then_same_fp_no_identical_from_success(ctx: RunContext) -> None:
    """E2E sketch: one recovered must not create identical thrash fuel."""
    sig = signature_key("mix", "incomplete_cut_unresolved")
    _append_action(
        ctx,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signature": sig,
            "playbook_id": "incomplete_cut_unresolved",
            "status": "recovered",
        },
    )
    assert attempt_count(ctx, sig) == 0
    # Fail path still fuels:
    _append_action(
        ctx,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signature": sig,
            "playbook_id": "incomplete_cut_unresolved",
            "status": "escalate",
        },
    )
    assert attempt_count(ctx, sig) >= 1


def test_p4_sticky_not_cleared_by_accounting_alone(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import thrash_hardening as th

    sticky_calls: list[str] = []
    real_note = th.note_sticky_heal_attempt

    def _note(*a: object, **k: object) -> object:
        sticky_calls.append("note")
        return real_note(*a, **k)

    monkeypatch.setattr(th, "note_sticky_heal_attempt", _note)
    finalize_post_heal_accounting(
        ctx,
        signature=signature_key("edl", "vo_seated_coverage"),
        status="recovered",
        playbook_id="vo_seated_coverage",
    )
    assert sticky_calls == []
