"""Shape organ — schedule existing Shape stages / gates as tools; soft-gate is fallback."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

SHAPE_STAGES = (
    "mastering_shape_agenda",
    "mastering_shape_candidates",
    "mastering_plan_synthesize",
    "mastering_plan_confirm",
)


def shape_status(ctx: RunContext) -> dict[str, Any]:
    done = [s for s in SHAPE_STAGES if ctx.artifact_exists(f".stage_done/{s}")]
    return {"stages": list(SHAPE_STAGES), "done": done, "soft_gate_fallback": True}
