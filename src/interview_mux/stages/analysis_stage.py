"""Shared LLM stage runner with envelope, memory merge, and orchestration loops."""

from __future__ import annotations

from typing import Any, Callable

from interview_mux.analysis_memory import (
    ensure_analysis_workspace,
    sync_content_brief_reanchor_to_state,
    sync_content_brief_to_state,
    sync_gaps_to_state,
    sync_speakers_to_state,
)
from interview_mux.artifact_completeness import attach_gap_fill_to_input
from interview_mux.llm_flow_hardening import (
    complete_llm_stage_or_halt,
    flow_hardening_cfg,
    flow_hardening_enabled,
    llm_stage_progress_ok,
)
from interview_mux.llm_stage_routing import (
    finalize_stage_attempt,
    run_llm_stage_with_routing,
)
from interview_mux.lint_adaptation import format_lint_feedback, itr_repair_hints, lint_retry_strategy
from interview_mux.lint_repair_bridge import RepairOutcome, try_staged_structural_repair
from interview_mux.adaptation_itr_bridge import BridgeOutcome, bridge_adaptation_to_itr
from interview_mux.boundary_observability import oversplit_risk_from_hints
from interview_mux.adaptation_loop_guard import AdaptationLoopGuard
from interview_mux.adaptive_context import plan_context
from interview_mux.operator_recovery import log_adaptation_step, log_operator_halt
from interview_mux.attempt_budget import build_attempt_signature
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext

PersistFn = Callable[[RunContext, dict[str, Any]], None]
SyncFn = Callable[[RunContext, dict[str, Any]], None]
PostLoopHook = Callable[[RunContext, str, dict[str, Any], dict[str, Any], list[str], bool], None]


def _attempt_signature(
    envelope: dict[str, Any],
    volley: list[dict[str, str]],
    schema_errors: list[str],
    lint_errors: list[str] | None = None,
) -> tuple[Any, ...]:
    return build_attempt_signature(envelope, volley, schema_errors, lint_errors)


def _maybe_legacy_flow_persist(
    ctx: RunContext,
    *,
    stage_key: str,
    envelope: dict[str, Any],
    arbiter_result: dict[str, Any] | None,
    schema_errors: list[str],
    output_rel: str | None,
    persist_artifacts: PersistFn,
) -> None:
    """Flow-only: persist top-level envelope keys when artifacts wrapper is absent."""
    if output_rel is None:
        return
    artifacts = envelope.get("artifacts") or {}
    if artifacts or envelope.get("artifacts") is not None:
        return
    from interview_mux.analysis_memory import should_persist_artifacts

    legacy = {k: v for k, v in envelope.items() if k not in ("status", "needs", "memory_updates")}
    if legacy and should_persist_artifacts(
        arbiter_result,
        {"artifacts": legacy, "status": envelope.get("status")},
        schema_errors,
    ):
        persist_artifacts(ctx, legacy)


def _run_llm_stage_loop(
    ctx: RunContext,
    stage_key: str,
    prompt_rel: str,
    build_stage_input: Callable[[RunContext], dict[str, Any]],
    persist_artifacts: PersistFn,
    *,
    sync_fn: SyncFn | None = None,
    max_iterations: int | None = None,
    output_rel: str | None = None,
    post_loop_hook: PostLoopHook | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[str], bool]:
    """Shared inner retry loop for analysis and flow LLM stages."""
    from interview_mux.analysis_orchestrator import max_iterations_for_stage
    from interview_mux.attempt_budget import check_primary_budget

    limit = max_iterations or max_iterations_for_stage(ctx)
    last_envelope: dict[str, Any] = {}
    last_arbiter: dict[str, Any] = {}
    last_schema_errors: list[str] = []
    last_routed_via_collate = False
    prev_signature: tuple[Any, ...] | None = None
    pending_retry: dict[str, Any] = {}
    lint_history: list[str] = []
    strategy_keys: list[str] = []
    itr_bridge_break = False
    guard = AdaptationLoopGuard.load(ctx, stage_key)

    for attempt in range(1, limit + 1):
        with logged_step(f"{stage_key}/attempt_{attempt}/budget", ctx=ctx, stage=stage_key):
            budget_msg = check_primary_budget(ctx, stage_key)
            if budget_msg:
                ctx.log(budget_msg, level="action", stage=stage_key)
                bridge = bridge_adaptation_to_itr(
                    ctx,
                    stage_key,
                    strategy_key="primary_budget_exhausted",
                    lint_errors=lint_history[-4:] if lint_history else None,
                    halt_kind="primary_budget_exhausted",
                )
                if bridge.outcome == BridgeOutcome.CLEARED:
                    last_envelope = last_envelope or {"status": "complete", "_routing_meta": {}}
                    last_envelope.setdefault("_routing_meta", {})["structural_repair_cleared"] = True
                    itr_bridge_break = True
                    break
                if bridge.outcome == BridgeOutcome.PARTIAL:
                    itr_bridge_break = True
                    break
                log_operator_halt(
                    ctx,
                    stage_key=stage_key,
                    halt_kind="primary_budget_exhausted",
                    message=budget_msg,
                    recovery_from_stage=stage_key,
                    action_id="llm.budget.primary_exhausted",
                )
                from interview_mux.write_staging import set_llm_gate

                set_llm_gate(
                    ctx,
                    stage_key,
                    message=f"LLM stage gate ({stage_key}): {budget_msg}",
                )
                itr_bridge_break = True
                break
            stage_input = attach_gap_fill_to_input(ctx, stage_key, build_stage_input(ctx))
            if pending_retry.get("itr_repair_hint"):
                stage_input = dict(stage_input)
                stage_input["itr_repair_hint"] = pending_retry["itr_repair_hint"]
            if pending_retry.get("lint_feedback"):
                stage_input = dict(stage_input)
                stage_input["lint_feedback"] = pending_retry["lint_feedback"]
            if pending_retry.get("enrich_input"):
                stage_input = dict(stage_input)
                stage_input["lint_retry_hint"] = (
                    "Prior attempt failed lint: anchor every topic and key_claim with "
                    "segment_ids, evidence_segment_ids, or approx_time_range; avoid generic "
                    "theme names without transcript evidence."
                )
            if pending_retry.get("inject_missing_segment_ids") and stage_input.get(
                "classification_obligation"
            ):
                from interview_mux.classification_obligation import missing_segment_ids

                obligation = stage_input["classification_obligation"]
                prior_segments = (last_envelope.get("artifacts") or {}).get("segments") or []
                missing = missing_segment_ids(obligation, prior_segments)
                if missing:
                    stage_input = dict(stage_input)
                    stage_input["classification_obligation_retry"] = {
                        "missing_segment_ids": missing,
                        "instruction": (
                            "Prior attempt omitted these segment ids — classify each one."
                        ),
                    }
            context_plan = plan_context(
                stage_key,
                attempt,
                stage_input,
                lint_history,
                guard,
                pending_retry=pending_retry,
            )
            if context_plan.exhausted:
                recovery_stage = context_plan.upstream_rerun or stage_key
                bridge = bridge_adaptation_to_itr(
                    ctx,
                    stage_key,
                    strategy_key=str(context_plan.strategy_key or "exhausted"),
                    lint_errors=lint_history[-4:] if lint_history else None,
                    halt_kind="adaptation_exhausted",
                )
                if bridge.outcome == BridgeOutcome.CLEARED:
                    last_envelope = last_envelope or {"status": "complete", "_routing_meta": {}}
                    last_envelope.setdefault("_routing_meta", {})["structural_repair_cleared"] = True
                    itr_bridge_break = True
                    break
                if bridge.outcome == BridgeOutcome.PARTIAL:
                    itr_bridge_break = True
                    break
                halt_msg = (
                    f"Stage {stage_key}: adaptation exhausted ({context_plan.reason}). "
                    f"Re-run --from-stage {recovery_stage}."
                )
                log_operator_halt(
                    ctx,
                    stage_key=stage_key,
                    halt_kind="adaptation_exhausted",
                    message=halt_msg,
                    recovery_from_stage=recovery_stage,
                    action_id="llm.adaptation.exhausted",
                    extra_detail={"context_plan": context_plan.to_dict()},
                )
                from interview_mux.write_staging import set_llm_gate

                set_llm_gate(ctx, stage_key, message=f"LLM stage gate ({stage_key}): {bridge.message or halt_msg}")
                itr_bridge_break = True
                break
            force_decompose = bool(
                pending_retry.get("force_decompose") or context_plan.force_decompose
            )
            bump_tier = bool(pending_retry.get("bump_tier") or context_plan.bump_tier)
            system_appendix = pending_retry.get("strict_appendix") or context_plan.system_appendix
            if context_plan.strategy_key not in ("obligation_full", "default"):
                log_adaptation_step(
                    ctx,
                    stage_key=stage_key,
                    message=f"Adaptation: {context_plan.reason}",
                    action_id="llm.adaptation.step",
                    extra_detail=context_plan.to_dict(),
                )
        with logged_step(f"{stage_key}/attempt_{attempt}/routing", ctx=ctx, stage=stage_key):
            envelope, volley, arbiter_result, schema_errors, shard_count, _src = run_llm_stage_with_routing(
                ctx,
                stage_key,
                prompt_rel,
                stage_input,
                attempt=attempt,
                bump_tier=bump_tier,
                force_decompose=force_decompose,
                system_appendix=system_appendix,
                stage_input_obligation=stage_input.get("classification_obligation"),
            )
        with logged_step(f"{stage_key}/attempt_{attempt}/finalize", ctx=ctx, stage=stage_key):
            finalize_stage_attempt(
                ctx,
                stage_key,
                attempt,
                envelope,
                volley,
                arbiter_result,
                schema_errors,
                shard_count,
                persist_artifacts=persist_artifacts,
                sync_fn=sync_fn,
            )
            _maybe_legacy_flow_persist(
                ctx,
                stage_key=stage_key,
                envelope=envelope,
                arbiter_result=arbiter_result,
                schema_errors=schema_errors,
                output_rel=output_rel,
                persist_artifacts=persist_artifacts,
            )
        last_envelope = envelope
        last_arbiter = arbiter_result or {}
        last_schema_errors = schema_errors
        routing = envelope.get("_routing_meta") or {}
        last_routed_via_collate = bool(routing.get("routed_via_collate"))
        lint_errors = routing.get("deterministic_lint_errors") or []
        lint_history.extend(lint_errors)
        pending_retry = {}
        structural_partial = False
        if lint_errors:
            repair = try_staged_structural_repair(ctx, stage_key, lint_errors)
            if repair.outcome == RepairOutcome.REPAIRED_OK:
                envelope.setdefault("_routing_meta", {})["structural_repair_cleared"] = True
                lint_errors = []
                routing["deterministic_lint_errors"] = []
                routing["structural_repair_cleared"] = True
            elif repair.outcome == RepairOutcome.REPAIRED_PARTIAL:
                lint_errors = list(repair.remaining_lint)
                routing["deterministic_lint_errors"] = lint_errors
                structural_partial = True

        itr_hint = itr_repair_hints(schema_errors, lint_errors)
        oversplit = oversplit_risk_from_hints(stage_input.get("pause_ladder_hints"))
        if lint_errors:
            strategy = lint_retry_strategy(
                lint_errors,
                stage_key,
                attempt=attempt,
                prior_strategy_keys=strategy_keys,
                structural_repair_partial=structural_partial,
                oversplit=oversplit,
            )
            if itr_hint:
                strategy = dict(strategy)
                strategy["itr_repair_hint"] = itr_hint
            # First-try: one brief-constrained recovery for duration/budget soft fails
            if stage_key in {
                "narrative_arc_plan",
                "full_master_ranking",
                "sound_design_plan",
            }:
                from interview_mux.first_try import first_try_mode_enabled, first_try_triage_overrides
                from interview_mux.delivery_brief import load_delivery_brief

                joined = " ".join(str(x) for x in lint_errors).lower()
                if first_try_mode_enabled() and any(
                    tok in joined for tok in ("duration", "budget", "too long", "over max", "sfx_density")
                ):
                    overrides = first_try_triage_overrides()
                    if overrides.get("brief_constrained_extra_attempt", True):
                        strategy = dict(strategy)
                        brief = load_delivery_brief(ctx) or {}
                        strategy["itr_repair_hint"] = (
                            (strategy.get("itr_repair_hint") or "")
                            + " Respect delivery_brief target_duration_sec and sfx_density caps: "
                            + str(
                                {
                                    "target_duration_sec": brief.get("target_duration_sec"),
                                    "sfx_density": brief.get("sfx_density"),
                                    "question_budget": brief.get("question_budget"),
                                }
                            )
                        )
                        strategy["strategy_key"] = "brief_constrained_retry"
                        strategy["enrich_input"] = True
            strategy_key = str(strategy.get("strategy_key") or "lint_retry")
            if not guard.record_strategy(
                strategy_key,
                lint_errors=lint_errors,
                missing_segment_ids=(
                    (stage_input.get("classification_obligation_retry") or {}).get(
                        "missing_segment_ids"
                    )
                    if isinstance(stage_input.get("classification_obligation_retry"), dict)
                    else None
                ),
            ):
                bridge = bridge_adaptation_to_itr(
                    ctx,
                    stage_key,
                    strategy_key=strategy_key,
                    lint_errors=lint_errors,
                    halt_kind="adaptation_signature_repeat",
                )
                if bridge.outcome == BridgeOutcome.CLEARED:
                    envelope.setdefault("_routing_meta", {})["structural_repair_cleared"] = True
                    itr_bridge_break = True
                    break
                if bridge.outcome == BridgeOutcome.PARTIAL:
                    itr_bridge_break = True
                    break
                halt_msg = (
                    f"Stage {stage_key}: adaptation loop detected (strategy={strategy_key})."
                )
                log_operator_halt(
                    ctx,
                    stage_key=stage_key,
                    halt_kind="adaptation_signature_repeat",
                    message=halt_msg,
                    recovery_from_stage=stage_key,
                    action_id="llm.adaptation.signature_repeat",
                    extra_detail={"strategy_key": strategy_key, "lint_errors": lint_errors[:4]},
                )
                from interview_mux.write_staging import set_llm_gate

                set_llm_gate(ctx, stage_key, message=f"LLM stage gate ({stage_key}): {bridge.message or halt_msg}")
                itr_bridge_break = True
                break
            strategy_keys.append(strategy_key)
            if strategy.get("force_decompose") and shard_count:
                guard.mark_decompose(shard_count)
            guard.save(ctx)
            if stage_key in ("segment_classification", "boundary_detection"):
                strategy = dict(strategy)
                strategy["lint_feedback"] = format_lint_feedback(
                    lint_errors,
                    stage_key,
                    ctx=ctx,
                    obligation=stage_input.get("classification_obligation"),
                )
            pending_retry = strategy
        elif itr_hint:
            pending_retry = {"itr_repair_hint": itr_hint, "strategy_key": "itr_schema_hint"}

        if flow_hardening_enabled() and flow_hardening_cfg().get("inner_retry_require_delta", True):
            sig = _attempt_signature(envelope, volley, schema_errors, lint_errors)
            if prev_signature is not None and sig == prev_signature and attempt < limit:
                ctx.log(
                    f"Stage {stage_key}: inner retry {attempt} unchanged — stopping early.",
                    level="warning",
                    stage=stage_key,
                )
                break
            prev_signature = sig

        status = envelope.get("status", "complete")
        blocking_needs = [
            n
            for n in envelope.get("needs") or []
            if n.get("blocking") and n.get("type") != "operator"
        ]
        blocking_followups = [
            f
            for f in envelope.get("follow_up_investigations") or []
            if isinstance(f, dict) and f.get("blocking")
        ]
        if status == "complete" and not blocking_needs and not blocking_followups:
            if routing.get("structural_repair_cleared") or itr_bridge_break:
                if routing.get("structural_repair_cleared"):
                    break
            if llm_stage_progress_ok(
                ctx,
                stage_key,
                envelope,
                schema_errors=schema_errors,
                arbiter_result=arbiter_result,
                routed_via_collate=last_routed_via_collate,
            ):
                break
        if itr_bridge_break:
            break
        if attempt < limit and (
            status in ("partial", "needs_input")
            or (status == "blocked" and (blocking_needs or blocking_followups))
            or blocking_needs
            or blocking_followups
        ):
            ctx.log(
                f"Stage {stage_key} attempt {attempt}/{limit}: {status} — retrying with updated memory",
                level="info",
                stage=stage_key,
            )
            continue
        if status == "blocked":
            ctx.log(
                f"Stage {stage_key} blocked: needs={envelope.get('needs')} "
                f"follow_up_investigations={blocking_followups} "
                f"lint={lint_errors[:3]}",
                level="warning",
                stage=stage_key,
            )
        break

    if post_loop_hook is not None:
        post_loop_hook(ctx, stage_key, last_envelope, last_arbiter, last_schema_errors, last_routed_via_collate)

    return last_envelope, last_arbiter, last_schema_errors, last_routed_via_collate


def run_analysis_llm_stage(
    ctx: RunContext,
    stage_key: str,
    prompt_rel: str,
    build_stage_input: Callable[[RunContext], dict[str, Any]],
    persist_artifacts: PersistFn,
    *,
    sync_fn: SyncFn | None = None,
    max_iterations: int | None = None,
    auto_complete: bool = True,
) -> dict[str, Any]:
    """Run one analysis LLM stage with inner retry loop until complete or max attempts."""
    from interview_mux.analysis_memory import update_completion_from_analysis

    ensure_analysis_workspace(ctx)

    def _post_analysis(ctx_: RunContext, *_a: Any) -> None:
        update_completion_from_analysis(ctx_)

    last_envelope, last_arbiter, last_schema_errors, last_routed_via_collate = _run_llm_stage_loop(
        ctx,
        stage_key,
        prompt_rel,
        build_stage_input,
        persist_artifacts,
        sync_fn=sync_fn,
        max_iterations=max_iterations,
        post_loop_hook=_post_analysis,
    )

    if last_envelope.get("status") == "complete" and llm_stage_progress_ok(
        ctx,
        stage_key,
        last_envelope,
        schema_errors=last_schema_errors,
        arbiter_result=last_arbiter,
        routed_via_collate=last_routed_via_collate,
    ):
        from interview_mux.analysis_orchestrator import apply_needs_reruns, llm_stage_runners

        apply_needs_reruns(ctx, stage_key, last_envelope, llm_stage_runners(ctx))

    if auto_complete and not _skip_auto_complete_after_bridge(ctx, stage_key):
        complete_llm_stage_or_halt(
            ctx,
            stage_key,
            last_envelope,
            schema_errors=last_schema_errors,
            arbiter_result=last_arbiter,
            routed_via_collate=last_routed_via_collate,
        )

    return last_envelope


def _skip_auto_complete_after_bridge(ctx: RunContext, stage_key: str) -> bool:
    from interview_mux.write_staging import read_gui_job

    job = read_gui_job(ctx) or {}
    status = str(job.get("status") or "")
    if status == "needs_clarification" and str(job.get("stage") or "") == stage_key:
        return True
    if status == "gate" and str(job.get("stage") or "") == stage_key:
        return True
    return False


def run_flow_llm_stage(
    ctx: RunContext,
    stage_key: str,
    prompt_rel: str,
    build_stage_input: Callable[[RunContext], dict[str, Any]],
    persist_artifacts: PersistFn,
    *,
    output_rel: str | None = None,
    max_iterations: int | None = None,
    auto_complete: bool = True,
) -> dict[str, Any]:
    """Flow stages: full routing with shared retry loop and analysis memory padding."""
    ensure_analysis_workspace(ctx)

    last_envelope, last_arbiter, last_schema_errors, last_routed_via_collate = _run_llm_stage_loop(
        ctx,
        stage_key,
        prompt_rel,
        build_stage_input,
        persist_artifacts,
        max_iterations=max_iterations,
        output_rel=output_rel,
    )

    if last_envelope.get("status") == "complete" and llm_stage_progress_ok(
        ctx,
        stage_key,
        last_envelope,
        schema_errors=last_schema_errors,
        arbiter_result=last_arbiter,
        routed_via_collate=last_routed_via_collate,
    ):
        from interview_mux.analysis_orchestrator import apply_needs_reruns, llm_stage_runners

        apply_needs_reruns(ctx, stage_key, last_envelope, llm_stage_runners(ctx))

    if auto_complete and not _skip_auto_complete_after_bridge(ctx, stage_key):
        complete_llm_stage_or_halt(
            ctx,
            stage_key,
            last_envelope,
            schema_errors=last_schema_errors,
            arbiter_result=last_arbiter,
            routed_via_collate=last_routed_via_collate,
        )

    return last_envelope


# Re-export sync helpers for stage modules
__all__ = [
    "run_analysis_llm_stage",
    "run_flow_llm_stage",
    "sync_content_brief_to_state",
    "sync_content_brief_reanchor_to_state",
    "sync_gaps_to_state",
    "sync_speakers_to_state",
    "llm_stage_progress_ok",
]
