"""Legacy step-through cleanup — pauses between stages were removed; only reset helpers remain."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext


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
