"""Universal remediation framework — classified playbook ladders with honest outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

REMEDIATION_PLAN_REL = "operator/remediation_plan.json"
EXECUTION_HEALTH_REL = "operator/execution_health.json"
INVALIDATION_LOG_REL = "operator/invalidation_log.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class RemediationPlan:
    error_class: str
    consumer_stage: str
    current_tier: int = 0
    max_tiers: int = 3
    allowed_rerun_stages: list[str] = field(default_factory=list)
    cascade_error_classes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "active": True,
            "error_class": self.error_class,
            "consumer_stage": self.consumer_stage,
            "current_tier": self.current_tier,
            "max_tiers": self.max_tiers,
            "allowed_rerun_stages": list(self.allowed_rerun_stages),
            "cascade_error_classes": list(self.cascade_error_classes),
            "started_at": _utc_now(),
        }


@dataclass
class RemediationOutcome:
    recovered: bool
    error_class: str
    playbook_id: str
    resume_stage: str
    detail: str = ""
    tier: int = 0


# Playbook families that use multi-step ladders (vo_contract uses execution_contract).
_LADDER_ERROR_CLASSES: frozenset[str] = frozenset(
    {"vo_contract_repair", "vo_seated_coverage", "edl_vo_coverage_repair"}
)


def remediation_plan_mutex_allows(ctx: RunContext, error_class: str) -> bool:
    """Only one active remediation ladder — refuse conflicting second ladder."""
    plan = read_active_remediation_plan(ctx)
    if not plan:
        try:
            from interview_mux.execution_contract import read_active_vo_repair_plan

            vo_plan = read_active_vo_repair_plan(ctx)
            if vo_plan and error_class != "vo_contract_repair":
                return False
        except Exception:
            pass
        return True
    active_ec = str(plan.get("error_class") or "")
    if active_ec == error_class:
        return True
    # Mutex vo_contract vs vo_coverage families
    mutex_groups = (
        frozenset({"vo_contract_repair", "vo_seated_coverage", "edl_vo_coverage_repair"}),
    )
    for group in mutex_groups:
        if active_ec in group and error_class in group and active_ec != error_class:
            return False
    return True


def read_active_remediation_plan(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(REMEDIATION_PLAN_REL):
        return None
    try:
        doc = ctx.read_json(REMEDIATION_PLAN_REL)
    except Exception:
        return None
    if not isinstance(doc, dict) or doc.get("completed") or not doc.get("active"):
        return None
    return doc


def policy_remediation_active(ctx: RunContext) -> bool:
    if read_active_remediation_plan(ctx):
        return True
    try:
        from interview_mux.execution_contract import read_active_vo_repair_plan

        return read_active_vo_repair_plan(ctx) is not None
    except Exception:
        return False


def failure_in_active_remediation(
    ctx: RunContext,
    *,
    failed_stage: str,
    producer: str,
) -> bool:
    plan = read_active_remediation_plan(ctx)
    if not plan:
        return False
    root = str(plan.get("error_class") or "")
    if producer and producer == root:
        return True
    cascade = {str(c) for c in (plan.get("cascade_error_classes") or [])}
    if producer in cascade:
        return True
    from interview_mux.refinement_passes import filter_retired_refine_stages

    invalidate = set(filter_retired_refine_stages(plan.get("allowed_rerun_stages") or []))
    if failed_stage in invalidate:
        return True
    return False


def mark_remediation_plan_completed(ctx: RunContext) -> None:
    if not ctx.artifact_exists(REMEDIATION_PLAN_REL):
        return
    try:
        plan = ctx.read_json(REMEDIATION_PLAN_REL)
        if isinstance(plan, dict):
            plan = dict(plan)
            plan["active"] = False
            plan["completed"] = True
            plan["completed_at"] = _utc_now()
            ctx.write_json(REMEDIATION_PLAN_REL, plan, skip_handoff=True)
    except Exception:
        pass


def write_remediation_plan(ctx: RunContext, plan: RemediationPlan) -> None:
    ctx.write_json(REMEDIATION_PLAN_REL, plan.to_dict(), skip_handoff=True)


def honest_playbook_outcome(
    ctx: RunContext,
    *,
    error_class: str,
    consumer_stage: str,
    playbook_id: str,
    artifacts_written: list[str],
    pre_check: callable | None = None,
    post_check: callable | None = None,
) -> RemediationOutcome:
    """Honest recovered only when post_check passes (default: no automatic True)."""
    if pre_check and not pre_check(ctx):
        return RemediationOutcome(
            recovered=False,
            error_class=error_class,
            playbook_id=playbook_id,
            resume_stage=consumer_stage,
            detail="pre_check_failed",
        )
    if post_check is not None:
        ok = post_check(ctx)
    elif error_class == "vo_contract_repair":
        from interview_mux.vo_contract import validate_vo_contract

        ok = not validate_vo_contract(ctx)
    elif error_class in {"vo_seated_coverage", "edl_vo_coverage_repair"}:
        from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

        ok = not compact_vo_coverage_stale_or_missing(ctx)
    else:
        ok = bool(artifacts_written)
    return RemediationOutcome(
        recovered=ok,
        error_class=error_class,
        playbook_id=playbook_id,
        resume_stage=consumer_stage,
        detail="validated" if ok else "post_check_failed",
    )


def _playbook_resume_stage(error_class: str, consumer_stage: str) -> str:
    try:
        from interview_mux.heal_routing import PLAYBOOK_REGISTRY

        spec = PLAYBOOK_REGISTRY.get(error_class)
        if spec:
            return str(spec.resume_stage or consumer_stage)
    except Exception:
        pass
    return consumer_stage


def run_classified_ladder(
    ctx: RunContext,
    *,
    consumer_stage: str,
    exc: BaseException,
    error_class: str | None = None,
) -> RemediationOutcome:
    """Dispatch classified recovery: vo_contract ladder or single playbook with honest check."""
    from interview_mux.recovery_controller import (
        classify_error_class,
        handle_stage_failure,
        has_classified_playbook,
    )

    ec = error_class or classify_error_class(consumer_stage, exc) or ""
    if not ec or not has_classified_playbook(ec):
        return RemediationOutcome(
            recovered=False,
            error_class=ec,
            playbook_id="none",
            resume_stage=consumer_stage,
            detail="unclassified",
        )

    if not remediation_plan_mutex_allows(ctx, ec):
        return RemediationOutcome(
            recovered=False,
            error_class=ec,
            playbook_id="mutex_blocked",
            resume_stage=consumer_stage,
            detail="active_remediation_plan_conflict",
        )

    update_execution_health(
        ctx,
        consumer_stage=consumer_stage,
        error_class=ec,
        remediation_in_progress=True,
    )

    if ec == "vo_contract_repair":
        from interview_mux.execution_contract import run_vo_contract_ladder

        result = run_vo_contract_ladder(ctx, consumer_stage=consumer_stage)
        update_execution_health(
            ctx,
            consumer_stage=consumer_stage,
            error_class=ec,
            last_tier=result.tier,
            remediation_in_progress=result.recovered,
        )
        return RemediationOutcome(
            recovered=result.recovered and result.contract_ok,
            error_class=ec,
            playbook_id="vo_contract_ladder",
            resume_stage=result.resume_stage or _playbook_resume_stage(ec, consumer_stage),
            detail=result.detail,
        )

    if ec in {"vo_seated_coverage", "edl_vo_coverage_repair"}:
        from interview_mux.execution_contract import run_edl_vo_coverage_ladder
        from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

        result = run_edl_vo_coverage_ladder(ctx, consumer_stage=consumer_stage)
        still_missing = compact_vo_coverage_stale_or_missing(ctx)
        resume = "vo_synthesize" if still_missing else (
            result.resume_stage or "vo_synthesize"
        )
        update_execution_health(
            ctx,
            consumer_stage=consumer_stage,
            error_class=ec,
            last_tier=result.tier,
            remediation_in_progress=result.recovered,
        )
        return RemediationOutcome(
            recovered=result.recovered,
            error_class=ec,
            playbook_id="edl_vo_coverage_ladder",
            resume_stage=resume,
            detail=result.detail,
        )

    write_remediation_plan(
        ctx,
        RemediationPlan(
            error_class=ec,
            consumer_stage=consumer_stage,
            allowed_rerun_stages=[_playbook_resume_stage(ec, consumer_stage)],
            cascade_error_classes=[ec],
        ),
    )
    result = handle_stage_failure(ctx, consumer_stage, exc)
    mark_remediation_plan_completed(ctx)
    update_execution_health(
        ctx,
        consumer_stage=consumer_stage,
        error_class=ec,
        remediation_in_progress=result.status == "recovered",
    )
    return RemediationOutcome(
        recovered=result.status == "recovered",
        error_class=ec,
        playbook_id=result.playbook_id,
        resume_stage=result.resume_stage,
        detail=result.detail,
    )


def update_execution_health(
    ctx: RunContext,
    *,
    consumer_stage: str = "",
    error_class: str = "",
    last_tier: str = "",
    remediation_in_progress: bool = False,
    predicate_count: int | None = None,
    automated_blocker: str = "",
    esr_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prev: dict[str, Any] = {}
    if ctx.artifact_exists(EXECUTION_HEALTH_REL):
        try:
            doc = ctx.read_json(EXECUTION_HEALTH_REL)
            if isinstance(doc, dict):
                prev = doc
        except Exception:
            pass
    row = {
        "version": 1,
        "last_progress_at": _utc_now(),
        "consumer_stage": consumer_stage or prev.get("consumer_stage") or "",
        "error_class": error_class or prev.get("error_class") or "",
        "last_tier": last_tier or prev.get("last_tier") or "",
        "remediation_in_progress": remediation_in_progress,
        "predicate_count": predicate_count if predicate_count is not None else prev.get("predicate_count", 0),
        "automated_blocker": automated_blocker or prev.get("automated_blocker") or "",
        "esr": esr_summary
        if esr_summary is not None
        else (prev.get("esr") if isinstance(prev.get("esr"), dict) else {}),
    }
    ctx.write_json(EXECUTION_HEALTH_REL, row, skip_handoff=True)
    return row


def append_invalidation_log(
    ctx: RunContext,
    *,
    stage: str,
    invalidated_artifacts: list[str],
    reconcile_status: str = "pending",
    profile_id: str = "",
    forbidden_skipped: list[str] | None = None,
) -> None:
    path = ctx.run_dir / INVALIDATION_LOG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    row = {
        "ts": _utc_now(),
        "stage": stage,
        "invalidated_artifacts": invalidated_artifacts[:24],
        "reconcile_status": reconcile_status,
        "profile_id": profile_id or "",
        "forbidden_skipped": list(forbidden_skipped or [])[:24],
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def reconcile_invalidated_bundle(
    ctx: RunContext,
    invalidated_stages: list[str] | tuple[str, ...],
    *,
    reason: str = "",
    skip_delivery_batch: bool = False,
    skip_invariants: bool = False,
) -> list[str]:
    """Post-invalidation reconcile: invariants + contract + delivery batch + clear halts."""
    stages = [str(s) for s in invalidated_stages if s]
    append_invalidation_log(
        ctx,
        stage=stages[0] if stages else "bundle",
        invalidated_artifacts=stages,
        reconcile_status="running",
    )
    notes: list[str] = []
    if not skip_invariants:
        try:
            from interview_mux.execution_invariants import run_execution_invariants

            report = run_execution_invariants(
                ctx,
                reason=reason or "invalidation_bundle",
                consumer_stage=stages[0] if stages else "",
            )
            if report.get("fixes_applied"):
                notes.extend(report.get("fixes_applied") or [])
        except Exception:
            pass
    try:
        from interview_mux.execution_contract import reconcile_execution_contract

        reconcile_execution_contract(ctx, reason=reason or "invalidation_bundle")
        notes.append("execution_contract")
    except Exception:
        pass
    if not skip_delivery_batch:
        try:
            from interview_mux.delivery_guardrails import reconcile_delivery_batch

            cleared = reconcile_delivery_batch(ctx)
            notes.extend(cleared or [])
        except Exception:
            pass
    try:
        from interview_mux.identical_failures import clear_halts_for_stages

        if stages:
            clear_halts_for_stages(ctx, frozenset(stages))
    except Exception:
        pass
    append_invalidation_log(
        ctx,
        stage=stages[0] if stages else "bundle",
        invalidated_artifacts=stages,
        reconcile_status="complete",
    )
    return list(dict.fromkeys(notes))


def run_delivery_recover_preflight(
    ctx: RunContext,
    *,
    consumer_stage: str = "",
    message: str = "",
) -> RemediationOutcome:
    """Server/GUI preflight: try classified ladder before surfacing block."""
    exc = RuntimeError(message or "delivery recover preflight")
    stage = consumer_stage or "nugget_layup_compose"
    return run_classified_ladder(ctx, consumer_stage=stage, exc=exc)
