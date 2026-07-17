"""Bridge adaptation-loop exhaustion to ITR auto-resolve before hard gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from interview_mux.artifact_auto_resolve import AutoResolveOutcome, auto_resolve_stage
from interview_mux.lint_repair_bridge import try_staged_structural_repair
from interview_mux.stage_acceptance import stage_acceptance_ok


class BridgeOutcome(str, Enum):
    CLEARED = "cleared"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class BridgeResult:
    outcome: BridgeOutcome
    message: str = ""
    open_blocking: int = 0
    auto_resolve_outcome: str | None = None
    acceptance_errors: list[str] = field(default_factory=list)


def _has_staged_artifact(ctx: Any, stage_key: str) -> bool:
    from interview_mux.artifact_issue_triage import _read_stage_artifact

    _rel, artifact = _read_stage_artifact(ctx, stage_key, staged=True)
    return artifact is not None


def _finalize_cleared(ctx: Any, stage_key: str) -> None:
    from interview_mux.artifact_auto_resolve import _clear_propagation_investigations
    from interview_mux.artifact_issue_triage import clear_clarification_gate
    from interview_mux.write_staging import has_pending_writes, record_pending_approval, write_approval_enabled

    _clear_propagation_investigations(ctx, stage_key)
    clear_clarification_gate(ctx, stage_key)
    if write_approval_enabled() and has_pending_writes(ctx, stage_key):
        record_pending_approval(ctx, stage_key)


def bridge_adaptation_to_itr(
    ctx: Any,
    stage_key: str,
    *,
    strategy_key: str,
    lint_errors: list[str] | None = None,
    halt_kind: str = "adaptation_signature_repeat",
) -> BridgeResult:
    from interview_mux.artifact_issue_triage import (
        blocking_issues_remaining,
        set_clarification_gate,
        triage_enabled,
    )

    if not triage_enabled():
        return BridgeResult(
            outcome=BridgeOutcome.FAILED,
            message=f"{stage_key}: ITR disabled — cannot bridge {halt_kind}",
        )

    if not _has_staged_artifact(ctx, stage_key):
        return BridgeResult(
            outcome=BridgeOutcome.FAILED,
            message=f"{stage_key}: no staged artifact for ITR bridge ({halt_kind})",
        )

    ctx.log(
        f"ITR bridge: {halt_kind} strategy={strategy_key}",
        level="info",
        stage=stage_key,
        action_id="itr.bridge.start",
        detail={"lint_errors": (lint_errors or [])[:4], "halt_kind": halt_kind},
    )

    from interview_mux.holistic_fabrication import try_holistic_fabrication_from_staged

    if try_holistic_fabrication_from_staged(ctx, stage_key, lint_errors):
        _finalize_cleared(ctx, stage_key)
        ctx.log(
            f"ITR bridge cleared via holistic fabrication ({halt_kind})",
            level="info",
            stage=stage_key,
            action_id="itr.bridge.holistic_cleared",
        )
        return BridgeResult(
            outcome=BridgeOutcome.CLEARED,
            message=f"{stage_key}: holistic fabrication cleared gate",
        )

    if lint_errors:
        repair = try_staged_structural_repair(ctx, stage_key, lint_errors)
        if repair.acceptance_ok:
            acceptance = stage_acceptance_ok(ctx, stage_key, staged=True, include_cross_validate=False)
            if acceptance.ok and blocking_issues_remaining(ctx, stage_key) == 0:
                _finalize_cleared(ctx, stage_key)
                return BridgeResult(
                    outcome=BridgeOutcome.CLEARED,
                    message=f"{stage_key}: structural repair cleared lint",
                )

    resolve = auto_resolve_stage(ctx, stage_key)
    open_blocking = blocking_issues_remaining(ctx, stage_key)
    acceptance = stage_acceptance_ok(ctx, stage_key, staged=True)

    if acceptance.ok and open_blocking == 0 and resolve.outcome == AutoResolveOutcome.SUCCESS:
        _finalize_cleared(ctx, stage_key)
        ctx.log(
            f"ITR bridge cleared ({halt_kind})",
            level="info",
            stage=stage_key,
            action_id="itr.bridge.cleared",
        )
        return BridgeResult(
            outcome=BridgeOutcome.CLEARED,
            message=f"{stage_key}: auto-resolve cleared issues",
            auto_resolve_outcome=resolve.outcome.value,
        )

    if open_blocking > 0 or not acceptance.ok:
        msg = (
            f"{stage_key}: {open_blocking or len(acceptance.all_errors)} issue(s) "
            "need clarification — use Fix all & continue."
        )
        set_clarification_gate(ctx, stage_key, message=msg)
        ctx.log(
            msg,
            level="warning",
            stage=stage_key,
            action_id="itr.bridge.partial",
            detail={"open_blocking": open_blocking, "acceptance_errors": acceptance.all_errors[:4]},
        )
        return BridgeResult(
            outcome=BridgeOutcome.PARTIAL,
            message=msg,
            open_blocking=open_blocking,
            auto_resolve_outcome=resolve.outcome.value,
            acceptance_errors=acceptance.all_errors[:8],
        )

    ctx.log(
        f"ITR bridge failed ({halt_kind})",
        level="action",
        stage=stage_key,
        action_id="itr.bridge.failed",
        detail={"resolve_outcome": resolve.outcome.value, "errors": resolve.errors[:4]},
    )
    return BridgeResult(
        outcome=BridgeOutcome.FAILED,
        message=f"{stage_key}: ITR bridge could not clear {halt_kind}",
        open_blocking=open_blocking,
        auto_resolve_outcome=resolve.outcome.value,
        acceptance_errors=acceptance.all_errors[:8],
    )
