"""Root-cause routing and downstream propagation planning for ITR."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from interview_mux.artifact_cross_validate import STAGE_CHECKPOINTS, validate_cross_artifacts
from interview_mux.config import merged_config
from interview_mux.issue_severity_rules import ClassifiedIssue
from interview_mux.llm_flow_hardening import resolve_llm_upstream_stage

_PROPAGATION_FROM: dict[str, tuple[str, ...]] = {
    "boundary_detection": (
        "segment_classification",
        "content_brief_reanchor",
        "sonic_context_build",
        "sound_design_palettes",
        "missing_framing",
        "optimal_questions",
    ),
    "segment_classification": (
        "content_brief_reanchor",
        "sonic_context_build",
        "sound_design_palettes",
        "missing_framing",
        "optimal_questions",
    ),
    "speaker_roles": ("content_context", "boundary_detection", "segment_classification"),
    "content_context": ("boundary_detection", "segment_classification", "content_brief_reanchor"),
    "content_brief_reanchor": (
        "sonic_context_build",
        "sound_design_palettes",
        "missing_framing",
        "optimal_questions",
    ),
    "sound_design_palettes": ("missing_framing", "optimal_questions"),
    "topic_coverage_audit": ("narrative_arc_plan", "full_master_ranking", "transitions"),
    "narrative_arc_plan": ("full_master_ranking", "transitions"),
    "full_master_ranking": ("transitions", "sound_design_plan_flow1", "edl_flow1"),
    "transitions": ("sound_design_plan_flow1", "edl_flow1"),
    "sound_design_plan_flow1": ("sfx_prompt_craft", "edl_flow1"),
    "sound_design_plan_flow2": ("sfx_prompt_craft",),
    "highlight_selection": ("sound_design_plan_flow2",),
}

_CHECKPOINTS_BY_FROM: dict[str, tuple[str, ...]] = {
    "boundary_detection": ("post_boundary_detection", "post_segmentation"),
    "segment_classification": ("post_segmentation", "post_reanchor", "post_gaps"),
}


def _triage_cfg() -> dict[str, Any]:
    return (merged_config().get("analysis") or {}).get("artifact_issue_triage") or {}


@dataclass
class StalePropagationPlan:
    from_stage: str
    stale_stages: list[str] = field(default_factory=list)
    invalidate_from: str | None = None
    cross_errors: list[str] = field(default_factory=list)
    cross_errors_by_checkpoint: dict[str, list[str]] = field(default_factory=dict)
    suggested_upstream_stage: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "from_stage": self.from_stage,
            "stale_stages": self.stale_stages,
            "invalidate_from": self.invalidate_from,
            "cross_errors": self.cross_errors[:12],
            "cross_errors_by_checkpoint": {
                k: v[:4] for k, v in self.cross_errors_by_checkpoint.items()
            },
            "suggested_upstream_stage": self.suggested_upstream_stage,
            "has_blocking": bool(self.cross_errors or self.stale_stages),
        }


def resolve_upstream_for_issue(
    issue: ClassifiedIssue,
    stage_key: str,
    ctx: Any | None = None,
) -> str | None:
    """Map a classified issue to the upstream stage that likely caused it."""
    low = issue.message.lower()
    upstream = resolve_llm_upstream_stage(ctx, stage_key) if ctx else None

    if issue.kind == "overlap" or "not monotonic" in low or "timeline" in low:
        if stage_key == "segment_classification":
            return "boundary_detection"
        return upstream

    if "boundary" in low and "not in manifest" in low:
        return "boundary_detection"

    if "not in manifest" in low:
        if stage_key in ("missing_framing", "optimal_questions", "topic_coverage_audit"):
            return "segment_classification"
        return upstream

    if "key_claim without evidence" in low or "generic theme" in low:
        if stage_key == "content_context":
            return None
        return "content_context"

    if issue.repair_strategy == "drop_orphan_ref" and "segment" in low:
        return "segment_classification"

    return upstream


def build_recovery_actions(
    issue: ClassifiedIssue,
    stage_key: str,
    ctx: Any | None = None,
) -> list[dict[str, Any]]:
    """Operator-executable recovery actions for a clarification item."""
    actions: list[dict[str, Any]] = [
        {"type": "apply_repair", "label": "Apply auto-repair"},
    ]
    upstream = resolve_upstream_for_issue(issue, stage_key, ctx)
    if upstream:
        label = upstream.replace("_", " ").title()
        actions.append(
            {
                "type": "rerun_upstream",
                "label": f"Re-run {label}",
                "stage": upstream,
            }
        )
    actions.append({"type": "dismiss", "label": "Dismiss (non-blocking)"})
    return actions


def resolve_recovery_plan(
    ctx: Any,
    stage_key: str,
    issues: list[ClassifiedIssue],
) -> dict[str, Any]:
    """Aggregate recovery hints for multiple open issues."""
    upstreams: list[str] = []
    for issue in issues:
        up = resolve_upstream_for_issue(issue, stage_key, ctx)
        if up and up not in upstreams:
            upstreams.append(up)
    propagation = compute_stale_downstream(ctx, stage_key)
    return {
        "stage_key": stage_key,
        "suggested_upstream_stages": upstreams,
        "propagation_plan": propagation.summary(),
    }


def plan_stale_downstream(ctx: Any, from_stage: str) -> StalePropagationPlan:
    """Read-only: stale stages and cross-validation errors without mutating summaries."""
    plan = StalePropagationPlan(from_stage=from_stage)
    if from_stage not in _PROPAGATION_FROM:
        return plan

    candidates = list(_PROPAGATION_FROM[from_stage])
    plan.stale_stages = [sid for sid in candidates if ctx.is_done(sid)]
    if plan.stale_stages:
        plan.invalidate_from = plan.stale_stages[0]

    for checkpoint in _CHECKPOINTS_BY_FROM.get(from_stage, ()):
        errs = validate_cross_artifacts(ctx, checkpoint)
        if errs:
            plan.cross_errors_by_checkpoint[checkpoint] = errs
            plan.cross_errors.extend(errs)

    if plan.cross_errors and not plan.invalidate_from:
        for stage_key, checkpoint in STAGE_CHECKPOINTS.items():
            if checkpoint in plan.cross_errors_by_checkpoint and stage_key in candidates:
                plan.invalidate_from = stage_key
                break

    if from_stage == "segment_classification" and plan.cross_errors:
        plan.suggested_upstream_stage = "boundary_detection"
    elif from_stage == "boundary_detection" and plan.cross_errors:
        for err in plan.cross_errors:
            if "manifest" in err.lower() or "segment" in err.lower():
                plan.suggested_upstream_stage = "segment_classification"
                break

    return plan


def invalidate_stale_downstream(ctx: Any, from_stage: str) -> None:
    """Mutate analysis summaries for downstream stages after confirmed propagation."""
    if from_stage not in _PROPAGATION_FROM:
        return
    from interview_mux.artifact_cross_validate import invalidate_stage_summaries

    invalidate_stage_summaries(ctx, tuple(_PROPAGATION_FROM[from_stage]))


def compute_stale_downstream(ctx: Any, from_stage: str) -> StalePropagationPlan:
    """Identify downstream stages stale after an upstream artifact fix (read-only plan)."""
    return plan_stale_downstream(ctx, from_stage)


def revalidate_downstream_for_stage(ctx: Any, stage_key: str) -> list[str]:
    """Cross-validate downstream checkpoints after upstream artifact repair."""
    if not _triage_cfg().get("revalidate_downstream_on_segment_fix", True):
        return []
    if stage_key not in _CHECKPOINTS_BY_FROM:
        return []
    return plan_stale_downstream(ctx, stage_key).cross_errors


def downstream_auto_continue_count(ctx: Any) -> int:
    path = "understanding/analysis_orchestration.json"
    if not ctx.artifact_exists(path):
        return 0
    doc = ctx.read_json(path)
    if not isinstance(doc, dict):
        return 0
    return int(doc.get("itr_downstream_auto_continue_count") or 0)


def record_downstream_auto_continue(ctx: Any) -> int:
    path = "understanding/analysis_orchestration.json"
    doc = ctx.read_json(path) if ctx.artifact_exists(path) else {}
    if not isinstance(doc, dict):
        doc = {}
    n = int(doc.get("itr_downstream_auto_continue_count") or 0) + 1
    doc["itr_downstream_auto_continue_count"] = n
    ctx.write_json(path, doc, skip_handoff=True)
    return n


def can_downstream_auto_continue(ctx: Any) -> bool:
    cap = int(_triage_cfg().get("max_downstream_auto_continue") or 1)
    return downstream_auto_continue_count(ctx) < cap


def upstream_rerun_count(ctx: Any) -> int:
    if not ctx.artifact_exists("understanding/analysis_orchestration.json"):
        return 0
    doc = ctx.read_json("understanding/analysis_orchestration.json")
    if not isinstance(doc, dict):
        return 0
    return int(doc.get("itr_upstream_rerun_count") or 0)


def record_upstream_rerun(ctx: Any) -> int:
    path = "understanding/analysis_orchestration.json"
    doc = ctx.read_json(path) if ctx.artifact_exists(path) else {}
    if not isinstance(doc, dict):
        doc = {}
    n = int(doc.get("itr_upstream_rerun_count") or 0) + 1
    doc["itr_upstream_rerun_count"] = n
    ctx.write_json(path, doc, skip_handoff=True)
    return n


def can_upstream_rerun(ctx: Any) -> bool:
    cap = int(_triage_cfg().get("max_upstream_reruns_per_run") or 2)
    return upstream_rerun_count(ctx) < cap
