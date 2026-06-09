"""Legacy step-through cleanup — pauses between stages were removed; only reset helpers remain."""

from __future__ import annotations

from typing import Any

from interview_mux.journey_state import read_run_meta
from interview_mux.run_context import RunContext


def _step_through_block(ctx: RunContext) -> dict[str, Any]:
    meta = read_run_meta(ctx)
    block = meta.get("step_through")
    return dict(block) if isinstance(block, dict) else {}


def clear_step_through_from(ctx: RunContext, stage: str, order: list[str]) -> None:
    if stage not in order:
        return
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

    def _patch(meta: dict[str, Any]) -> None:
        if block:
            meta["step_through"] = block
        elif "step_through" in meta:
            del meta["step_through"]

    ctx.mutate_run_meta(_patch)


def reset_step_through_session(ctx: RunContext) -> None:
    def _patch(meta: dict[str, Any]) -> None:
        meta.pop("step_through", None)

    ctx.mutate_run_meta(_patch)
