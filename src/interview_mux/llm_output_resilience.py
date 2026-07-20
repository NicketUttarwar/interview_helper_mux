"""Legacy resilience stubs — v2 uses llm_simple only."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def artifact_resilience_partial(*_args: Any, **_kwargs: Any) -> list[str]:
    return []


def upstream_artifact_acceptable(*_args: Any, **_kwargs: Any) -> bool:
    return True


def apply_resilience_and_persist(
    ctx: RunContext,
    stage_key: str,
    envelope: dict[str, Any],
    *,
    persist_fn: Any = None,
) -> dict[str, Any]:
    _ = (ctx, stage_key, persist_fn)
    return envelope
