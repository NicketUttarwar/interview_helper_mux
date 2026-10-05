"""Emit Shape ordered_segment_ids dynamically for hybrid bind (per-tape, not template)."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.rank_candidates import chapter_order_from_plan


def derive_shape_ordered_segment_ids(ctx: RunContext, plan: dict[str, Any]) -> list[str]:
    """Best-effort air order for mastering_plan when Shape is ready.

    Prefer (in order):
    1. Existing plan.ordered_segment_ids if already complete
    2. Flattened narrative_plan chapters (story spine)
    3. Episode structure beat order
    4. Current selection order
    5. Manifest chronological ids
    """
    existing = plan.get("ordered_segment_ids")
    if isinstance(existing, list) and existing:
        return [str(s) for s in existing if s]

    if ctx.artifact_exists("master/narrative_plan.json"):
        np = ctx.read_json("master/narrative_plan.json")
        chapter_order = chapter_order_from_plan(np if isinstance(np, dict) else None)
        if chapter_order:
            return chapter_order

    if ctx.artifact_exists("understanding/episode_structure.json"):
        try:
            es = (__import__("interview_mux.episode_structure", fromlist=["load_episode_structure"]).load_episode_structure(ctx) or {})
            if isinstance(es, dict):
                beats = es.get("beats") or es.get("ordered_segment_ids") or []
                if isinstance(beats, list) and beats:
                    if beats and isinstance(beats[0], dict):
                        ids = [str(b.get("segment_id")) for b in beats if b.get("segment_id")]
                    else:
                        ids = [str(s) for s in beats if s]
                    if ids:
                        return ids
                hook = es.get("hook_segment_id")
                if hook and ctx.artifact_exists("segments/manifest.json"):
                    man = ctx.read_json("segments/manifest.json")
                    ids = [
                        str(s.get("segment_id"))
                        for s in ((man or {}).get("segments") or [])
                        if isinstance(s, dict) and s.get("segment_id")
                    ]
                    if hook in ids:
                        rest = [s for s in ids if s != hook]
                        return [str(hook)] + rest
        except Exception:
            pass

    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            ordered = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
            if ordered:
                return ordered

    if ctx.artifact_exists("segments/manifest.json"):
        man = ctx.read_json("segments/manifest.json")
        return [
            str(s.get("segment_id"))
            for s in ((man or {}).get("segments") or [])
            if isinstance(s, dict) and s.get("segment_id")
        ]
    return []


def attach_shape_order(ctx: RunContext, plan: dict[str, Any]) -> dict[str, Any]:
    """Mutate a copy of plan with ordered_segment_ids + order_authority metadata."""
    out = dict(plan)
    ordered = derive_shape_ordered_segment_ids(ctx, out)
    if ordered:
        out["ordered_segment_ids"] = ordered
        out["order_emit"] = {
            "source": "shape_dynamic",
            "count": len(ordered),
            "consumers_bind_global": False,
            "note": "Hybrid bind is per-run via shape_order_bind when story_health passes",
        }
    return out
