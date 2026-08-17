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


def _candidates(ctx: RunContext) -> list[dict[str, Any]]:
    for rel in (
        "mastering/shape/candidates.json",
        "mastering/shape/l2_candidates.json",
        "mastering/mastering_plan.json",
    ):
        if not ctx.artifact_exists(rel):
            continue
        raw = ctx.read_json(rel)
        if isinstance(raw, dict):
            rows = raw.get("candidates") or raw.get("modes") or []
            if isinstance(rows, list) and rows:
                return [r for r in rows if isinstance(r, dict)]
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
    return []


def run_shape_pre_gates(ctx: RunContext) -> dict[str, Any]:
    from interview_mux.mastering_shape_gates import run_pre_critique_gates

    cands = _candidates(ctx)
    result = run_pre_critique_gates(ctx, cands)
    return {
        "ok": True,
        "candidate_count": len(getattr(result, "candidates", cands) or cands),
        "soft_gate_fallback": not cands,
    }


def run_shape_post_gates(ctx: RunContext) -> dict[str, Any]:
    from interview_mux.mastering_shape_gates import run_post_critique_gates

    critique: dict[str, Any] = {}
    if ctx.artifact_exists("mastering/shape/cross_critique.json"):
        raw = ctx.read_json("mastering/shape/cross_critique.json")
        if isinstance(raw, dict):
            critique = raw
    frontier, survivors = run_post_critique_gates(ctx, critique, _candidates(ctx))
    return {"ok": True, "frontier": frontier is not None, "survivors": len(survivors or [])}
