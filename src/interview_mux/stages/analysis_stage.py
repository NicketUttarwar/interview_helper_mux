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
from interview_mux.context_volley import volley_char_estimate
from interview_mux.llm_flow_hardening import (
    complete_llm_stage_or_halt,
    flow_hardening_cfg,
    flow_hardening_enabled,
    llm_stage_progress_ok,
)
from interview_mux.llm_stage_routing import finalize_stage_attempt, run_llm_stage_with_routing
from interview_mux.run_context import RunContext

PersistFn = Callable[[RunContext, dict[str, Any]], None]
SyncFn = Callable[[RunContext, dict[str, Any]], None]


def _attempt_signature(
    envelope: dict[str, Any],
    volley: list[dict[str, str]],
    schema_errors: list[str],
) -> tuple[Any, ...]:
    return (
        envelope.get("status"),
        tuple(schema_errors[:3]),
        volley_char_estimate(volley),
    )


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
    from interview_mux.analysis_orchestrator import max_iterations_for_stage

    ensure_analysis_workspace(ctx)
    limit = max_iterations or max_iterations_for_stage(ctx)
    last_envelope: dict[str, Any] = {}
    last_volley: list[dict[str, str]] = []
    last_arbiter: dict[str, Any] = {}
    last_schema_errors: list[str] = []
    last_routed_via_collate = False
    prev_signature: tuple[Any, ...] | None = None

    for attempt in range(1, limit + 1):
        stage_input = attach_gap_fill_to_input(ctx, stage_key, build_stage_input(ctx))
        envelope, volley, arbiter_result, schema_errors, shard_count, _src = run_llm_stage_with_routing(
            ctx,
            stage_key,
            prompt_rel,
            stage_input,
            attempt=attempt,
        )
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
        last_envelope = envelope
        last_volley = volley
        last_arbiter = arbiter_result or {}
        last_schema_errors = schema_errors
        routing = envelope.get("_routing_meta") or {}
        last_routed_via_collate = bool(routing.get("routed_via_collate"))

        if flow_hardening_enabled() and flow_hardening_cfg().get("inner_retry_require_delta", True):
            sig = _attempt_signature(envelope, volley, schema_errors)
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
        if status == "complete" and not blocking_needs:
            if llm_stage_progress_ok(
                ctx,
                stage_key,
                envelope,
                schema_errors=schema_errors,
                arbiter_result=arbiter_result,
                routed_via_collate=last_routed_via_collate,
            ):
                break
        if status == "blocked":
            ctx.log(
                f"Stage {stage_key} blocked: {envelope.get('needs')}",
                level="warning",
                stage=stage_key,
            )
            break
        if attempt < limit and (status in ("partial", "needs_input") or blocking_needs):
            ctx.log(
                f"Stage {stage_key} attempt {attempt}/{limit}: {status} — retrying with updated memory",
                level="info",
                stage=stage_key,
            )
            continue
        break

    from interview_mux.analysis_memory import update_completion_from_analysis

    update_completion_from_analysis(ctx)
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

    if auto_complete:
        complete_llm_stage_or_halt(
            ctx,
            stage_key,
            last_envelope,
            schema_errors=last_schema_errors,
            arbiter_result=last_arbiter,
            routed_via_collate=last_routed_via_collate,
        )

    return last_envelope


def run_flow_llm_stage(
    ctx: RunContext,
    stage_key: str,
    prompt_rel: str,
    build_stage_input: Callable[[RunContext], dict[str, Any]],
    persist_artifacts: PersistFn,
    *,
    output_rel: str | None = None,
    auto_complete: bool = True,
) -> dict[str, Any]:
    """Flow stages: single envelope call with analysis memory padding and full routing."""
    ensure_analysis_workspace(ctx)
    stage_input = attach_gap_fill_to_input(ctx, stage_key, build_stage_input(ctx))
    envelope, volley, arbiter_result, schema_errors, shard_count, _src = run_llm_stage_with_routing(
        ctx,
        stage_key,
        prompt_rel,
        stage_input,
        attempt=1,
    )
    finalize_stage_attempt(
        ctx,
        stage_key,
        1,
        envelope,
        volley,
        arbiter_result,
        schema_errors,
        shard_count,
        persist_artifacts=persist_artifacts,
    )
    routing = envelope.get("_routing_meta") or {}
    routed_via_collate = bool(routing.get("routed_via_collate"))
    artifacts = envelope.get("artifacts") or {}
    if not artifacts and output_rel and envelope.get("artifacts") is None:
        from interview_mux.analysis_memory import should_persist_artifacts

        legacy = {k: v for k, v in envelope.items() if k not in ("status", "needs", "memory_updates")}
        if legacy and should_persist_artifacts(
            arbiter_result,
            {"artifacts": legacy, "status": envelope.get("status")},
            schema_errors,
        ):
            persist_artifacts(ctx, legacy)
    if envelope.get("status") == "complete" and llm_stage_progress_ok(
        ctx,
        stage_key,
        envelope,
        schema_errors=schema_errors,
        arbiter_result=arbiter_result,
        routed_via_collate=routed_via_collate,
    ):
        from interview_mux.analysis_orchestrator import apply_needs_reruns, llm_stage_runners

        apply_needs_reruns(ctx, stage_key, envelope, llm_stage_runners(ctx))

    if auto_complete:
        complete_llm_stage_or_halt(
            ctx,
            stage_key,
            envelope,
            schema_errors=schema_errors,
            arbiter_result=arbiter_result,
            routed_via_collate=routed_via_collate,
        )

    return envelope


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
