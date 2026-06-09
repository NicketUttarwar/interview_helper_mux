"""Review checkpoints for per-interview (custom run) descriptive artifacts.

Zero-shot pipeline runs stop after each stage that writes flagship LLM profile / planning
JSON until the operator acknowledges the handoff in the GUI.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from interview_mux.config import merged_config
from interview_mux.journey_state import read_run_meta
from interview_mux.prompt_validation import ARTIFACT_WRITE_VALIDATORS, STAGE_ARTIFACT_DISK_PATHS
from interview_mux.run_context import RunContext

# Operational paths — written by ingest/STT/operator tooling, not custom-run review.
_NON_CUSTOM_RUN_PATHS = frozenset(
    {
        "run_meta.json",
        "ingest/checksums.json",
        "transcript/corrections.json",
        "transcript/review_queue.json",
        "segments/nle_edits.json",
    }
)

CUSTOM_RUN_ARTIFACT_PATHS: frozenset[str] = frozenset(
    p for p in ARTIFACT_WRITE_VALIDATORS if p not in _NON_CUSTOM_RUN_PATHS
)

# Pipeline stage ids that may pause for handoff (LLM + acoustic profile).
STAGES_REQUIRING_HANDOFF_REVIEW: frozenset[str] = frozenset(
    {
        *STAGE_ARTIFACT_DISK_PATHS.keys(),
        "source_acoustic_profile",
    }
)

_PATH_TO_STAGE: dict[str, str] = {}
for _stage_key, _rel in STAGE_ARTIFACT_DISK_PATHS.items():
    _PATH_TO_STAGE.setdefault(_rel, _stage_key)

active_pipeline_stage: ContextVar[str | None] = ContextVar("active_pipeline_stage", default=None)

_PIPELINE_STAGE_ORDER: list[str] | None = None


def _pipeline_stage_order() -> list[str]:
    global _PIPELINE_STAGE_ORDER
    if _PIPELINE_STAGE_ORDER is not None:
        return _PIPELINE_STAGE_ORDER
    from interview_mux.pipeline import ANALYSIS_ORDER, FLOW1_ORDER, FLOW2_ORDER, FLOW3_ORDER

    order: list[str] = []
    for sid in (
        *ANALYSIS_ORDER,
        "transcript_review",
        "topic_coverage_audit",
        *FLOW1_ORDER,
        *FLOW2_ORDER,
        *FLOW3_ORDER,
    ):
        if sid not in order:
            order.append(sid)
    _PIPELINE_STAGE_ORDER = order
    return order


def handoff_between_stages_enabled() -> bool:
    cfg = merged_config().get("journey_ui") or {}
    if not isinstance(cfg, dict):
        return True
    return bool(cfg.get("require_handoff_between_stages", True))


def is_custom_run_artifact(rel_path: str) -> bool:
    return rel_path in CUSTOM_RUN_ARTIFACT_PATHS


def stage_for_custom_run_path(rel_path: str) -> str | None:
    return _PATH_TO_STAGE.get(rel_path)


def handoff_acknowledged(ctx: RunContext, stage_id: str) -> bool:
    ack = read_run_meta(ctx).get("handoff_ack") or {}
    return bool(ack.get(stage_id))


def record_custom_run_write(
    ctx: RunContext,
    rel_path: str,
    *,
    stage_key: str | None = None,
) -> None:
    """Track a custom-run artifact write and clear prior ack for that stage."""
    if not is_custom_run_artifact(rel_path):
        return
    sid = (
        stage_key
        or active_pipeline_stage.get()
        or stage_for_custom_run_path(rel_path)
        or "analysis_profile"
    )
    def _patch(meta: dict[str, Any]) -> None:
        pending: dict[str, list[str]] = dict(meta.get("handoff_pending_writes") or {})
        paths = list(pending.get(sid) or [])
        if rel_path not in paths:
            paths.append(rel_path)
        pending[sid] = paths
        meta["handoff_pending_writes"] = pending
        ack = dict(meta.get("handoff_ack") or {})
        if sid in ack:
            del ack[sid]
            meta["handoff_ack"] = ack

    ctx.mutate_run_meta(_patch)


def custom_run_paths_for_stage(ctx: RunContext, stage_id: str) -> list[str]:
    """Union of registry artifacts, pending writes, and on-disk custom-run files for a stage."""
    from interview_mux.web.stages import STAGE_BY_ID

    paths: list[str] = []
    info = STAGE_BY_ID.get(stage_id)
    if info:
        for p in info.artifacts:
            if is_custom_run_artifact(p):
                paths.append(p)
    meta = read_run_meta(ctx)
    for p in (meta.get("handoff_pending_writes") or {}).get(stage_id) or []:
        if p not in paths:
            paths.append(p)
    if stage_id == "analysis_profile":
        for p in (
            "understanding/analysis_state.json",
            "understanding/investigation_queue.json",
        ):
            if p not in paths:
                paths.append(p)
    present = [p for p in paths if ctx.artifact_exists(p)]
    return present or paths


def handoff_paths_for_stage(ctx: RunContext, stage_id: str) -> list[str]:
    """Custom-run paths for a stage that are complete and ready for operator review."""
    from interview_mux.artifact_completeness import artifact_ready_for_review

    return [p for p in custom_run_paths_for_stage(ctx, stage_id) if artifact_ready_for_review(p, ctx)]


def pending_handoff_stage(ctx: RunContext) -> str | None:
    """Earliest completed stage (pipeline order) with unacknowledged custom-run handoff."""
    if not handoff_between_stages_enabled():
        return None
    for sid in _pipeline_stage_order():
        if sid not in STAGES_REQUIRING_HANDOFF_REVIEW:
            continue
        if not ctx.is_done(sid):
            continue
        if handoff_acknowledged(ctx, sid):
            continue
        paths = handoff_paths_for_stage(ctx, sid)
        if paths:
            return sid
    return None


def handoff_review_message(ctx: RunContext, stage_id: str) -> str:
    from interview_mux.web.stages import STAGE_BY_ID

    info = STAGE_BY_ID.get(stage_id)
    title = info.title if info else stage_id
    paths = handoff_paths_for_stage(ctx, stage_id)
    names = ", ".join(paths[:4])
    if len(paths) > 4:
        names += f", +{len(paths) - 4} more"
    return (
        f"{title} produced AI outputs ({names}). "
        "Review in the GUI, then acknowledge before the next stage."
    )


def require_handoff_clear(ctx: RunContext) -> None:
    """Raise SystemExit when an unacknowledged custom-run handoff blocks continuation."""
    sid = pending_handoff_stage(ctx)
    if not sid:
        return
    msg = handoff_review_message(ctx, sid)
    ctx.log(
        msg,
        level="action",
        stage=sid,
        detail={"handoff": handoff_paths_for_stage(ctx, sid)},
    )
    raise SystemExit(msg)


def pause_after_stage_if_needed(ctx: RunContext, stage_name: str) -> None:
    """Stop batch pipeline execution until the operator acknowledges this stage's handoff."""
    if not handoff_between_stages_enabled():
        return
    if stage_name not in STAGES_REQUIRING_HANDOFF_REVIEW:
        return
    if not ctx.is_done(stage_name):
        return
    if handoff_acknowledged(ctx, stage_name):
        return
    paths = handoff_paths_for_stage(ctx, stage_name)
    if not paths:
        raw_paths = custom_run_paths_for_stage(ctx, stage_name)
        if raw_paths and any(ctx.artifact_exists(p) for p in raw_paths):
            ctx.log(
                f"{stage_name} outputs still partial — skipping handoff until artifacts are complete.",
                level="warning",
                stage=stage_name,
            )
        return
    require_handoff_clear(ctx)


def check_handoff_before_execute(ctx: RunContext) -> str | None:
    """Return an error message when execution must wait for handoff review."""
    sid = pending_handoff_stage(ctx)
    if not sid:
        return None
    return handoff_review_message(ctx, sid)


def filter_custom_run_handoff_paths(paths: list[str]) -> list[str]:
    return [p for p in paths if is_custom_run_artifact(p)]
