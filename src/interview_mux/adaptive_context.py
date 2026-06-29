"""Adaptive context planning for LLM stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from interview_mux.adaptation_loop_guard import AdaptationLoopGuard
from interview_mux.classification_obligation import classification_context_cfg
from interview_mux.stage_coupling import contract_segment_ids

DecomposeMode = Literal["none", "batch", "per_segment"]
ProfileName = Literal["full", "shard", "collate"]


@dataclass
class ContextPlan:
    profile: ProfileName = "full"
    decompose_mode: DecomposeMode = "none"
    obligation_enabled: bool = True
    bump_tier: bool = False
    system_appendix: str | None = None
    strategy_key: str = "obligation_full"
    reason: str = ""
    exhausted: bool = False
    force_decompose: bool = False
    upstream_rerun: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "decompose_mode": self.decompose_mode,
            "obligation_enabled": self.obligation_enabled,
            "bump_tier": self.bump_tier,
            "strategy_key": self.strategy_key,
            "reason": self.reason,
            "exhausted": self.exhausted,
            "force_decompose": self.force_decompose,
            "upstream_rerun": self.upstream_rerun,
        }


def _segment_count(stage_input: dict[str, Any]) -> int:
    boundaries = stage_input.get("boundaries")
    if isinstance(boundaries, dict):
        return len(contract_segment_ids(boundaries))
    return 0


def plan_context(
    stage_key: str,
    attempt: int,
    stage_input: dict[str, Any],
    lint_history: list[str],
    guard: AdaptationLoopGuard,
    pending_retry: dict[str, Any] | None = None,
) -> ContextPlan:
    """Choose volley/decompose strategy for this attempt."""
    cfg = classification_context_cfg()
    pending = pending_retry or {}
    plan = ContextPlan(obligation_enabled=bool(cfg.get("classification_obligation_enabled", True)))

    if guard.is_exhausted():
        plan.exhausted = True
        plan.reason = "adaptation budget exhausted"
        plan.strategy_key = "exhausted"
        return plan

    if pending.get("upstream_rerun"):
        plan.exhausted = True
        plan.upstream_rerun = str(pending["upstream_rerun"])
        plan.reason = f"upstream rerun required: {plan.upstream_rerun}"
        plan.strategy_key = "upstream_boundary_rerun"
        guard.request_upstream_rerun()
        return plan

    if stage_key != "segment_classification":
        plan.reason = "default full volley"
        return plan

    seg_count = _segment_count(stage_input)
    per_seg_max = int(cfg.get("per_segment_shard_max", 20))
    proactive_threshold = int(cfg.get("proactive_decompose_segments", 0))

    if pending.get("force_decompose") and guard.can_decompose():
        plan.force_decompose = True
        plan.decompose_mode = "per_segment" if seg_count <= per_seg_max else "batch"
        plan.profile = "shard"
        plan.strategy_key = str(pending.get("strategy_key") or "lint_decompose")
        plan.system_appendix = pending.get("strict_appendix")
        plan.bump_tier = bool(pending.get("bump_tier"))
        plan.reason = f"lint-driven decompose ({plan.decompose_mode})"
        return plan

    if attempt == 1 and proactive_threshold > 0 and seg_count <= proactive_threshold:
        if guard.can_decompose():
            plan.force_decompose = True
            plan.decompose_mode = "per_segment"
            plan.profile = "shard"
            plan.strategy_key = "proactive_per_segment"
            plan.reason = f"proactive per-segment decompose ({seg_count} segments)"
            return plan

    if any("segment_coverage_ratio" in e for e in lint_history) and attempt >= 2:
        if guard.can_decompose():
            plan.force_decompose = True
            plan.decompose_mode = "per_segment" if seg_count <= per_seg_max else "batch"
            plan.profile = "shard"
            plan.strategy_key = "coverage_decompose"
            plan.reason = "coverage lint — per-segment decompose"
            return plan

    if any("interviewee_answer" in e for e in lint_history) and attempt >= 2:
        if guard.can_decompose():
            plan.force_decompose = True
            plan.decompose_mode = "per_segment" if seg_count <= per_seg_max else "batch"
            plan.profile = "shard"
            plan.strategy_key = "type_diversity_decompose"
            from interview_mux.lint_adaptation import _LINT_CLASSIFICATION_TYPE_APPENDIX

            plan.system_appendix = _LINT_CLASSIFICATION_TYPE_APPENDIX
            plan.reason = "mono-type lint — decompose with type appendix"
            return plan

    plan.reason = "full obligation volley"
    plan.strategy_key = "obligation_full"
    return plan
