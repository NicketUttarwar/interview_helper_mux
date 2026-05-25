"""Shared LLM stage runner with envelope, memory merge, and orchestration loops."""

from __future__ import annotations

from typing import Any, Callable

from interview_mux.analysis_memory import (
    apply_envelope_to_memory,
    ensure_analysis_workspace,
    record_stage_attempt,
    sync_content_brief_to_state,
    sync_gaps_to_state,
    sync_speakers_to_state,
    update_completion_from_analysis,
)
from interview_mux.context_volley import build_message_volley
from interview_mux.run_context import RunContext
from interview_mux.prompt_validation import (
    format_validation_feedback,
    validate_stage_artifacts,
)
from interview_mux.stages.llm_runner import run_prompt_envelope

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
        stage_input = build_stage_input(ctx)
        volley = build_message_volley(ctx, stage_key, stage_input)
        envelope = run_prompt_envelope(
            stage_key,
            prompt_rel,
            messages=volley,
            ctx=ctx,
        )
        artifacts = envelope.get("artifacts") or {}
        schema_errors = validate_stage_artifacts(stage_key, artifacts)
        if schema_errors and attempt < limit:
            ctx.log(
                f"Stage {stage_key} attempt {attempt}: artifact schema errors — retrying",
                level="warning",
                stage=stage_key,
            )
            volley = [
                *volley,
                {
                    "role": "user",
                    "content": format_validation_feedback(schema_errors),
                },
            ]
            envelope = run_prompt_envelope(
                stage_key,
                prompt_rel,
                messages=volley,
                ctx=ctx,
            )
            artifacts = envelope.get("artifacts") or {}
            schema_errors = validate_stage_artifacts(stage_key, artifacts)

        record_stage_attempt(ctx, stage_key, attempt, envelope, context_volley=volley)
        last_envelope = envelope

        if schema_errors:
            ctx.log(
                f"Stage {stage_key}: artifact validation warnings: {schema_errors[:3]}",
                level="warning",
                stage=stage_key,
            )
        if artifacts:
            persist_artifacts(ctx, artifacts)
        if sync_fn:
            sync_fn(ctx, artifacts)

        apply_envelope_to_memory(ctx, stage_key, envelope)
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
    """Flow stages: single envelope call with analysis memory padding."""
    ensure_analysis_workspace(ctx)
    stage_input = build_stage_input(ctx)
    volley = build_message_volley(ctx, stage_key, stage_input)
    envelope = run_prompt_envelope(
        stage_key,
        prompt_rel,
        messages=volley,
        ctx=ctx,
    )
    artifacts = envelope.get("artifacts") or {}
    schema_errors = validate_stage_artifacts(stage_key, artifacts)
    if schema_errors:
        volley_retry = [
            *volley,
            {"role": "user", "content": format_validation_feedback(schema_errors)},
        ]
        envelope = run_prompt_envelope(
            stage_key,
            prompt_rel,
            messages=volley_retry,
            ctx=ctx,
        )
        artifacts = envelope.get("artifacts") or {}
        schema_errors = validate_stage_artifacts(stage_key, artifacts)
        if schema_errors:
            ctx.log(
                f"Stage {stage_key}: artifact validation warnings: {schema_errors[:3]}",
                level="warning",
                stage=stage_key,
            )
        volley = volley_retry
    record_stage_attempt(ctx, stage_key, 1, envelope, context_volley=volley)
    if artifacts:
        persist_artifacts(ctx, artifacts)
    elif output_rel and envelope.get("artifacts") is None:
        legacy = {k: v for k, v in envelope.items() if k not in ("status", "needs", "memory_updates")}
        if legacy:
            persist_artifacts(ctx, legacy)
    apply_envelope_to_memory(ctx, stage_key, envelope)
    return envelope


# Re-export sync helpers for stage modules
__all__ = [
    "run_analysis_llm_stage",
    "run_flow_llm_stage",
    "sync_content_brief_to_state",
    "sync_gaps_to_state",
    "sync_speakers_to_state",
]
