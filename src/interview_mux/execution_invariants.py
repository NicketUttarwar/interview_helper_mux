"""Proactive execution invariants — fix holes before consumer stages block."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

CONSUMER_STAGES = frozenset(
    {
        "nugget_layup_compose",
        "vo_synthesize",
        "edl_narrative_audit",
        "edl",
        "mix",
        "vo_line_adjudicate",
        "air_script_seams",
    }
)


def invariants_enabled() -> bool:
    try:
        from interview_mux.config import merged_config

        root = merged_config()
        mastering = root.get("mastering") if isinstance(root, dict) else {}
        resilience = (mastering or {}).get("resilience") if isinstance(mastering, dict) else {}
        if isinstance(resilience, dict):
            return bool(resilience.get("proactive_invariants_enabled", True))
    except Exception:
        pass
    return True


def invariant_vo_contract(ctx: RunContext) -> list[str]:
    from interview_mux.execution_contract import reconcile_execution_contract, run_vo_contract_ladder
    from interview_mux.vo_contract import validate_vo_contract

    reconcile_execution_contract(ctx, reason="invariant_vo_contract")
    violations = validate_vo_contract(ctx)
    if not violations:
        return []
    result = run_vo_contract_ladder(ctx, consumer_stage="invariant")
    if result.contract_ok:
        return ["vo_contract_ladder"]
    return []


def invariant_vo_coverage(ctx: RunContext) -> list[str]:
    from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

    missing = compact_vo_coverage_stale_or_missing(ctx)
    if not missing:
        return []
    from interview_mux.execution_contract import run_edl_vo_coverage_ladder

    result = run_edl_vo_coverage_ladder(ctx, consumer_stage="edl_narrative_audit")
    if result.recovered:
        return ["edl_vo_coverage_ladder"]
    return []


def invariant_hollow_markers(ctx: RunContext) -> list[str]:
    from interview_mux.delivery_guardrails import reconcile_delivery_batch

    cleared = reconcile_delivery_batch(ctx)
    return cleared or []


def invariant_seed_order_preview(ctx: RunContext, consumer_stage: str) -> list[str]:
    if consumer_stage not in {"edl", "mix", "vo_synthesize"}:
        return []
    try:
        from interview_mux.delivery_guardrails import upstream_stale_blockers

        blockers = upstream_stale_blockers(ctx, consumer_stage)
        if not blockers:
            return []
        from interview_mux.remediation_framework import run_classified_ladder

        outcome = run_classified_ladder(
            ctx,
            consumer_stage=consumer_stage,
            exc=RuntimeError(f"stale upstream: {blockers[0]}"),
            error_class="upstream_stale_rerun",
        )
        return ["upstream_stale_rerun"] if outcome.recovered else []
    except Exception:
        return []


def invariant_write_staging(ctx: RunContext) -> list[str]:
    from interview_mux.write_staging import stages_with_pending_writes

    pending = stages_with_pending_writes(ctx)
    producers = {"nugget_layup_compose", "edl", "gap_framing_recompose"}
    hit = [s for s in pending if s in producers]
    return [f"pending_write:{s}" for s in hit]


def run_execution_invariants(
    ctx: RunContext,
    *,
    reason: str,
    consumer_stage: str = "",
) -> dict[str, Any]:
    """Fix-first invariant pass; one ladder attempt for vo_contract if still failing."""
    if not invariants_enabled():
        return {"skipped": True, "reason": reason}

    fixes: list[str] = []
    fixes.extend(invariant_hollow_markers(ctx))
    fixes.extend(invariant_vo_contract(ctx))
    if consumer_stage == "edl_narrative_audit" or consumer_stage == "edl":
        fixes.extend(invariant_vo_coverage(ctx))
    if consumer_stage:
        fixes.extend(invariant_seed_order_preview(ctx, consumer_stage))
    fixes.extend(invariant_write_staging(ctx))

    from interview_mux.vo_contract import validate_vo_contract

    still_bad = validate_vo_contract(ctx)
    return {
        "version": 1,
        "reason": reason,
        "consumer_stage": consumer_stage,
        "fixes_applied": list(dict.fromkeys(fixes)),
        "vo_contract_ok": not still_bad,
        "remaining_violations": still_bad[:6],
    }


def run_consumer_invariants(ctx: RunContext, stage_id: str) -> None:
    if stage_id not in CONSUMER_STAGES:
        return
    run_execution_invariants(ctx, reason=f"pre_{stage_id}", consumer_stage=stage_id)
