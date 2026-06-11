"""Per-stage attempt budgets — loop circuit-breaker for LLM routing."""

from __future__ import annotations

import json
from typing import Any

from interview_mux.config import merged_config
from interview_mux.llm_flow_hardening import flow_hardening_cfg, flow_hardening_enabled
from interview_mux.run_context import RunContext

ORCHESTRATION_PATH = "understanding/analysis_orchestration.json"


def _budget_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    return flow_hardening_cfg(cfg)


def max_primary_attempts(cfg: dict[str, Any] | None = None) -> int:
    return int(_budget_cfg(cfg).get("max_primary_attempts_per_stage", 4))


def max_arbiter_rejects(cfg: dict[str, Any] | None = None) -> int:
    return int(_budget_cfg(cfg).get("max_arbiter_rejects_per_stage", 3))


def stuck_signature_threshold(cfg: dict[str, Any] | None = None) -> int:
    return int(_budget_cfg(cfg).get("stuck_signature_threshold", 2))


def _orch(ctx: RunContext) -> dict[str, Any]:
    if ctx.artifact_exists(ORCHESTRATION_PATH):
        doc = ctx.read_json(ORCHESTRATION_PATH)
        if isinstance(doc, dict):
            return doc
    return {}


def _save_orch(ctx: RunContext, orch: dict[str, Any]) -> None:
    ctx.write_json(ORCHESTRATION_PATH, orch, skip_handoff=True)


def record_primary_attempt(ctx: RunContext, stage_key: str) -> int:
    orch = _orch(ctx)
    counts = orch.setdefault("primary_attempt_counts", {})
    n = int(counts.get(stage_key, 0)) + 1
    counts[stage_key] = n
    _save_orch(ctx, orch)
    return n


def record_arbiter_reject(ctx: RunContext, stage_key: str, verdict: str) -> int:
    if verdict in ("accept",):
        return arbiter_reject_count(ctx, stage_key)
    orch = _orch(ctx)
    counts = orch.setdefault("arbiter_reject_counts", {})
    n = int(counts.get(stage_key, 0)) + 1
    counts[stage_key] = n
    _save_orch(ctx, orch)
    return n


def primary_attempt_count(ctx: RunContext, stage_key: str) -> int:
    return int(_orch(ctx).get("primary_attempt_counts", {}).get(stage_key, 0))


def arbiter_reject_count(ctx: RunContext, stage_key: str) -> int:
    return int(_orch(ctx).get("arbiter_reject_counts", {}).get(stage_key, 0))


def _signature_key(signature: tuple[Any, ...]) -> str:
    return json.dumps(signature, sort_keys=True, default=str)


def record_stuck_signature(
    ctx: RunContext,
    stage_key: str,
    signature: tuple[Any, ...],
) -> int:
    orch = _orch(ctx)
    stuck = orch.setdefault("stuck_signatures", {})
    key = f"{stage_key}"
    sig_key = _signature_key(signature)
    prev = stuck.get(key)
    if prev == sig_key:
        n = int(orch.setdefault("stuck_counts", {}).get(key, 0)) + 1
        orch.setdefault("stuck_counts", {})[key] = n
    else:
        stuck[key] = sig_key
        orch.setdefault("stuck_counts", {})[key] = 1
        n = 1
    _save_orch(ctx, orch)
    return n


def stuck_count(ctx: RunContext, stage_key: str) -> int:
    return int(_orch(ctx).get("stuck_counts", {}).get(stage_key, 0))


def check_primary_budget(ctx: RunContext, stage_key: str) -> str | None:
    if not flow_hardening_enabled():
        return None
    n = primary_attempt_count(ctx, stage_key)
    cap = max_primary_attempts()
    if n >= cap:
        return (
            f"Stage {stage_key}: primary attempt budget exhausted ({n}/{cap}). "
            f"Inspect understanding/stage_runs/{stage_key}/, fix artifacts, re-run --from-stage {stage_key}."
        )
    return None


def check_arbiter_budget(ctx: RunContext, stage_key: str) -> str | None:
    if not flow_hardening_enabled():
        return None
    n = arbiter_reject_count(ctx, stage_key)
    cap = max_arbiter_rejects()
    if n >= cap:
        return (
            f"Stage {stage_key}: arbiter reject budget exhausted ({n}/{cap}). "
            f"Use Fill gaps or operator review; re-run --from-stage {stage_key}."
        )
    return None


def is_stuck(ctx: RunContext, stage_key: str) -> bool:
    return stuck_count(ctx, stage_key) >= stuck_signature_threshold()


def budget_extra_for_attempt(
    ctx: RunContext,
    stage_key: str,
    *,
    attempt_signature: tuple[Any, ...] | None = None,
    arbiter_verdict: str | None = None,
    lint_errors: list[str] | None = None,
) -> dict[str, Any]:
    """Metadata recorded in stage_runs attempt files."""
    out: dict[str, Any] = {
        "primary_attempt_count": primary_attempt_count(ctx, stage_key),
        "arbiter_reject_count": arbiter_reject_count(ctx, stage_key),
        "budget_remaining_primary": max(0, max_primary_attempts() - primary_attempt_count(ctx, stage_key)),
    }
    if attempt_signature is not None:
        out["attempt_signature"] = list(attempt_signature)
        out["stuck_count"] = record_stuck_signature(ctx, stage_key, attempt_signature)
    if arbiter_verdict:
        out["arbiter_verdict"] = arbiter_verdict
    if lint_errors:
        out["deterministic_lint_errors"] = lint_errors[:8]
    return out
