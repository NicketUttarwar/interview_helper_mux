"""Shared LLM stage runner with envelope, memory merge, and orchestration loops."""

from __future__ import annotations

from typing import Any, Callable

from interview_mux.analysis_memory import (
    ensure_analysis_workspace,
    sync_content_brief_to_state,
    sync_gaps_to_state,
    sync_speakers_to_state,
    update_completion_from_analysis,
)
from interview_mux.artifact_completeness import attach_gap_fill_to_input
from interview_mux.llm_stage_routing import finalize_stage_attempt, run_llm_stage_with_routing
from interview_mux.run_context import RunContext

PersistFn = Callable[[RunContext, dict[str, Any]], None]
SyncFn = Callable[[RunContext, dict[str, Any]], None]


def run_analysis_llm_stage(
    ctx: RunContext,
    stage_key: str,
    prompt_rel: str,
    build_stage_input: Callable[[RunContext], dict[str, Any]],
    persist_artifacts: PersistFn,
    *,
    sync_fn: SyncFn | None = None,
    max_iterations: int | None = None,
) -> dict[str, Any]:
    """Run one analysis LLM stage with inner retry loop until complete or max attempts."""
    from interview_mux.analysis_orchestrator import max_iterations_for_stage

    ensure_analysis_workspace(ctx)
    limit = max_iterations or max_iterations_for_stage(ctx)
    last_envelope: dict[str, Any] = {}

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
        status = envelope.get("status", "complete")
        blocking_needs = [
            n
            for n in envelope.get("needs") or []
            if n.get("blocking") and n.get("type") != "operator"
        ]
        if status == "complete" and not blocking_needs:
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

    update_completion_from_analysis(ctx)
    return last_envelope


def run_flow_llm_stage(
    ctx: RunContext,
    stage_key: str,
    prompt_rel: str,
    build_stage_input: Callable[[RunContext], dict[str, Any]],
    persist_artifacts: PersistFn,
    *,
    output_rel: str | None = None,
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
    artifacts = envelope.get("artifacts") or {}
    if not artifacts and output_rel and envelope.get("artifacts") is None:
        from interview_mux.analysis_memory import should_persist_artifacts

        legacy = {k: v for k, v in envelope.items() if k not in ("status", "needs", "memory_updates")}
        if legacy and should_persist_artifacts(arbiter_result, {"artifacts": legacy, "status": envelope.get("status")}, schema_errors):
            persist_artifacts(ctx, legacy)
    return envelope


# Re-export sync helpers for stage modules
__all__ = [
    "run_analysis_llm_stage",
    "run_flow_llm_stage",
    "sync_content_brief_to_state",
    "sync_gaps_to_state",
    "sync_speakers_to_state",
]
