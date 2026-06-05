"""Pause before each pipeline stage so the operator can proceed or skip."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

StepThroughAction = Literal["proceed", "skip"]

# Operator gates — use checkpoint modal instead of step-through countdown.
STEP_THROUGH_EXCLUDED: frozenset[str] = frozenset(
    {
        "transcript_review",
        "g1_vo_pickup",
        "g2_flow_select",
        "analysis_profile",
    }
)


class StageStepThroughPending(Exception):
    """Pipeline paused until operator proceeds or skips the upcoming stage."""

    def __init__(self, stage_id: str, *, pause_seconds: int) -> None:
        self.stage_id = stage_id
        self.pause_seconds = pause_seconds
        super().__init__(
            f"Step-through pause before '{stage_id}' — proceed or skip within {pause_seconds}s."
        )


def step_through_enabled() -> bool:
    cfg = merged_config().get("journey_ui") or {}
    if not isinstance(cfg, dict):
        return True
    return bool(cfg.get("step_through_between_stages", True))


def step_through_pause_seconds() -> int:
    cfg = merged_config().get("journey_ui") or {}
    if not isinstance(cfg, dict):
        return 10
    raw = cfg.get("step_through_pause_seconds", 10)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 10


def _read_meta(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists("run_meta.json"):
        return {}
    raw = ctx.read_json("run_meta.json")
    return raw if isinstance(raw, dict) else {}


def _write_meta(ctx: RunContext, meta: dict[str, Any]) -> None:
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    ctx.write_json("run_meta.json", meta, skip_handoff=True)


def _step_through_block(ctx: RunContext) -> dict[str, Any]:
    meta = _read_meta(ctx)
    block = meta.get("step_through")
    return dict(block) if isinstance(block, dict) else {}


def pending_step_through_stage(ctx: RunContext) -> str | None:
    if not step_through_enabled():
        return None
    pending = _step_through_block(ctx).get("pending")
    if not isinstance(pending, dict):
        return None
    sid = pending.get("stage_id")
    return str(sid) if sid else None


def clear_step_through_from(ctx: RunContext, stage: str, order: list[str]) -> None:
    if stage not in order:
        return
    meta = _read_meta(ctx)
    block = _step_through_block(ctx)
    approved = dict(block.get("approved") or {})
    idx = order.index(stage)
    for sid in order[idx:]:
        approved.pop(sid, None)
    if approved:
        block["approved"] = approved
    else:
        block.pop("approved", None)
    block.pop("pending", None)
    if block:
        meta["step_through"] = block
    elif "step_through" in meta:
        del meta["step_through"]
    _write_meta(ctx, meta)


def reset_step_through_session(ctx: RunContext) -> None:
    meta = _read_meta(ctx)
    if "step_through" not in meta:
        return
    del meta["step_through"]
    _write_meta(ctx, meta)


def _resume_payload_from_job(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists("gui_job.json"):
        return {}
    job = ctx.read_json("gui_job.json")
    if not isinstance(job, dict):
        return {}
    keys = (
        "mode",
        "stage",
        "flow",
        "from_stage",
        "until_stage",
        "nle_full_refresh",
        "nle_apply_mode",
    )
    return {k: job[k] for k in keys if k in job}


def _approved_action(ctx: RunContext, stage_id: str) -> StepThroughAction | None:
    approved = _step_through_block(ctx).get("approved") or {}
    if not isinstance(approved, dict):
        return None
    action = approved.get(stage_id)
    if action in ("proceed", "skip"):
        return action
    return None


def require_step_through_before_stage(ctx: RunContext, stage_id: str) -> None:
    """Raise StageStepThroughPending when operator confirmation is required."""
    if not step_through_enabled():
        return
    if stage_id in STEP_THROUGH_EXCLUDED:
        return
    if ctx.is_done(stage_id):
        return
    if _approved_action(ctx, stage_id):
        return

    pause_seconds = step_through_pause_seconds()
    meta = _read_meta(ctx)
    block = _step_through_block(ctx)
    pending = block.get("pending")
    if isinstance(pending, dict) and pending.get("stage_id") == stage_id:
        raise StageStepThroughPending(stage_id, pause_seconds=pause_seconds)

    from interview_mux.web.stages import STAGE_BY_ID

    info = STAGE_BY_ID.get(stage_id)
    title = info.title if info else stage_id
    block["pending"] = {
        "stage_id": stage_id,
        "title": title,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "pause_seconds": pause_seconds,
        "resume": _resume_payload_from_job(ctx),
    }
    meta["step_through"] = block
    _write_meta(ctx, meta)
    ctx.log(
        f"Ready to run {title} — proceed or skip in the GUI.",
        level="action",
        stage=stage_id,
        detail={"step_through": True, "pause_seconds": pause_seconds},
    )
    raise StageStepThroughPending(stage_id, pause_seconds=pause_seconds)


def confirm_step_through(
    ctx: RunContext,
    stage_id: str,
    action: StepThroughAction,
) -> dict[str, Any]:
    """Record operator choice and return stored resume payload for JobRunner."""
    pending = _step_through_block(ctx).get("pending")
    if not isinstance(pending, dict) or pending.get("stage_id") != stage_id:
        raise ValueError(f"No step-through pause pending for stage '{stage_id}'.")

    resume = dict(pending.get("resume") or {})
    meta = _read_meta(ctx)
    block = _step_through_block(ctx)
    block.pop("pending", None)
    approved = dict(block.get("approved") or {})
    approved[stage_id] = action
    block["approved"] = approved
    meta["step_through"] = block
    _write_meta(ctx, meta)

    from interview_mux.web.stages import STAGE_BY_ID

    info = STAGE_BY_ID.get(stage_id)
    title = info.title if info else stage_id
    if action == "skip":
        ctx.mark_done(stage_id)
        ctx.log(f"Skipped {title} — continuing pipeline.", level="warning", stage=stage_id)
    else:
        ctx.log(f"Proceeding with {title}.", level="info", stage=stage_id)
    return resume
