"""Shared LLM stage runner — v2 simplified path via llm_simple."""

from __future__ import annotations

from typing import Any, Callable

from interview_mux.analysis_memory import (
    ensure_analysis_workspace,
    sync_content_brief_reanchor_to_state,
    sync_content_brief_to_state,
    sync_gaps_to_state,
    sync_speakers_to_state,
    update_completion_from_analysis,
)
from interview_mux.llm_flow_hardening import llm_stage_progress_ok
from interview_mux.llm_simple import run_llm_stage_simple
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
    auto_complete: bool = True,
) -> dict[str, Any]:
    """Run one analysis LLM stage (max 2 attempts via llm_simple)."""
    _ = max_iterations
    ensure_analysis_workspace(ctx)
    envelope = run_llm_stage_simple(
        ctx,
        stage_key,
        prompt_rel,
        build_stage_input,
        persist_artifacts,
        sync_fn=sync_fn,
        auto_complete=auto_complete,
    )
    update_completion_from_analysis(ctx)
    return envelope


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
    """Run one delivery LLM stage (max 2 attempts via llm_simple)."""
    _ = output_rel, max_iterations
    ensure_analysis_workspace(ctx)
    return run_llm_stage_simple(
        ctx,
        stage_key,
        prompt_rel,
        build_stage_input,
        persist_artifacts,
        auto_complete=auto_complete,
    )


__all__ = [
    "run_analysis_llm_stage",
    "run_flow_llm_stage",
    "sync_content_brief_to_state",
    "sync_content_brief_reanchor_to_state",
    "sync_gaps_to_state",
    "sync_speakers_to_state",
    "llm_stage_progress_ok",
]
