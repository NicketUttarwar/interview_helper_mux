"""12A — homunculus halt plan snapshot for Executions tab."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

PLAN_REL = "mastering/homunculus/plan.json"


def write_halt_plan(
    ctx: RunContext,
    *,
    last_target: str = "",
    blockers: list[str] | None = None,
    attempted_heals: list[str] | None = None,
    recommended_next: str = "",
    reason: str = "",
) -> dict[str, Any]:
    pipeline_mode: dict[str, Any] | None = None
    try:
        from interview_mux.pipeline_mode import resolve_effective_mode

        pipeline_mode = resolve_effective_mode(ctx)
    except Exception:
        pipeline_mode = None
    doc: dict[str, Any] = {
        "last_target": last_target,
        "blockers": list(blockers or [])[:12],
        "attempted_heals": list(attempted_heals or [])[:12],
        "recommended_next": recommended_next,
        "pipeline_mode": pipeline_mode,
        "reason": reason[:400],
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    ctx.write_json(PLAN_REL, doc, skip_handoff=True)
    return doc


def read_halt_plan(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(PLAN_REL):
        return None
    doc = ctx.read_json(PLAN_REL)
    return doc if isinstance(doc, dict) else None


__all__ = ["PLAN_REL", "read_halt_plan", "write_halt_plan"]
