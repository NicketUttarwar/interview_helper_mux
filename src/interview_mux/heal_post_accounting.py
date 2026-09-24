"""Post-Heal Accounting Constitution (Heal Clinic post_heal_budget_thrash B+).

HC-POST-HEAL-BUDGET — plug into BUD-1 + Heal Success; not a fifth brand.

``finalize_post_heal_accounting`` is the sole post-recover accounting entrypoint
(pipeline / homunculus / driver reach it only via recovery ``_append_action``).

Laws:
- P1: recovered rows do not R12c-mirror into identical
- P2: recovered rows do not burn recovery_attempt_budget (see attempt_count)
- P3: ship predicate-progress reclaim — clear that signature when token flips
- anti-C: recovered alone never stamps budget_epoch / never clears without flip
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from interview_mux.run_context import RunContext

# Default empty — identity/global epoch on predicate flip is opt-in only.
# Signature clear (P3) is the default reclaim; BUD-1 still owns product epoch.
POST_HEAL_EPOCH_ALLOW: frozenset[str] = frozenset()

# Recovered never fuels recovery_attempt_budget (P2). Allowlist unused by default.
POST_HEAL_COUNT_RECOVERED_ATTEMPTS: bool = False


@dataclass(frozen=True)
class PostHealAccountingResult:
    mirrored: bool
    signature_cleared: int
    epoch_stamped: bool
    detail: str


def _parse_signature_key(signature: str) -> tuple[str, str]:
    parts = str(signature or "").split(":", 1)
    if len(parts) != 2:
        return "", ""
    return parts[0].strip(), parts[1].strip()


def reclaim_class_signature_on_predicate_progress(
    ctx: RunContext,
    *,
    failed_stage: str,
    error_class: str,
) -> int:
    """P3: zero identical class rows for stage/class when predicate token flipped.

    Anti-C: if a prior token is present and has **not** flipped, leave counts.
    Rows without a prior token are not cleared on recovered alone (need a flip
    signal — empty prior is treated as no progress proof).
    """
    stage = str(failed_stage or "").strip()
    cls = str(error_class or "").strip()
    if not stage or not cls:
        return 0
    from interview_mux.identical_failures import (
        _utc_now,
        _write,
        read_identical_failures,
    )
    from interview_mux.thrash_hardening import predicate_flipped, stage_predicate_token

    doc = read_identical_failures(ctx)
    signatures = dict(doc.get("signatures") or {})
    cleared = 0
    for sig, row in list(signatures.items()):
        if not isinstance(row, dict):
            continue
        if str(row.get("failed_stage") or "").strip() != stage:
            continue
        if str(row.get("error_class") or row.get("producer") or "").strip() != cls:
            continue
        prior = row.get("predicate_token")
        prior_s = str(prior).strip() if isinstance(prior, str) else ""
        if not prior_s:
            # Anti-C: no prior token → do not clear on recovered alone.
            continue
        if not predicate_flipped(ctx, stage, prior_s):
            continue
        out = dict(row)
        out["count"] = 0
        out["halt"] = False
        out["cleared_at"] = _utc_now()
        out["predicate_token"] = stage_predicate_token(ctx, stage)
        out["cleared_reason"] = "post_heal_predicate_progress"
        signatures[sig] = out
        cleared += 1
        try:
            from interview_mux.thrash_hardening import clear_thrash_on_predicate_flip

            clear_thrash_on_predicate_flip(ctx, stage=stage, prior_token=prior_s)
        except Exception:
            pass
    if not cleared:
        return 0
    doc["signatures"] = signatures
    doc["updated_at"] = _utc_now()
    _write(ctx, doc)
    return cleared


def finalize_post_heal_accounting(
    ctx: RunContext,
    *,
    signature: str,
    status: str,
    playbook_id: str = "",
    stage_id: str = "",
    resume_attempted: str = "",
) -> PostHealAccountingResult:
    """Sole post-recover accounting gate (P11).

    Callers: recovery_controller ``_append_action`` only. Pipeline / runtime /
    driver must reach this via ``handle_stage_failure`` → ``_append_action``.
    """
    status_l = str(status or "").strip().lower()
    sig = str(signature or "").strip()
    pid = str(playbook_id or "").strip()
    stage_from_sig, error_class = _parse_signature_key(sig)
    stage = str(stage_id or stage_from_sig or "").strip()

    if status_l == "recovered":
        # P1: do not R12c-mirror recovered into identical.
        cleared = 0
        if stage and error_class:
            try:
                cleared = int(
                    reclaim_class_signature_on_predicate_progress(
                        ctx, failed_stage=stage, error_class=error_class
                    )
                    or 0
                )
            except Exception:
                cleared = 0
        epoch = False
        # anti-C: never stamp global budget_epoch on recovered alone.
        # Opt-in POST_HEAL_EPOCH_ALLOW only after predicate reclaim cleared.
        if cleared and pid and pid in POST_HEAL_EPOCH_ALLOW:
            try:
                from interview_mux.homunculus.ledger import stamp_budget_epoch

                stamp_budget_epoch(
                    ctx,
                    reason=f"post_heal_predicate:{pid}"[:80],
                )
                epoch = True
            except Exception:
                epoch = False
        return PostHealAccountingResult(
            False,
            cleared,
            epoch,
            "recovered_no_mirror"
            + (f"+cleared={cleared}" if cleared else "+no_predicate_flip"),
        )

    # Escalate / other: keep R12c mirror for classified playbooks.
    mirrored = False
    if sig:
        try:
            from interview_mux.recovery_controller import (
                _mirror_recovery_to_identical_failures,
                has_classified_playbook,
            )

            if error_class and has_classified_playbook(error_class):
                _mirror_recovery_to_identical_failures(
                    ctx,
                    sig,
                    resume_attempted=str(resume_attempted or pid or ""),
                )
                mirrored = True
        except Exception:
            mirrored = False
    return PostHealAccountingResult(
        mirrored, 0, False, "escalate_mirror" if mirrored else "escalate_no_mirror"
    )


def recovered_rows_fuel_attempt_budget() -> bool:
    """P2: whether recovered recovery-log rows count toward attempt_count."""
    return bool(POST_HEAL_COUNT_RECOVERED_ATTEMPTS)
