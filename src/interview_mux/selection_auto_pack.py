"""Deterministic selection trim to fit delivery_brief duration max."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def _segment_duration_ms(seg: dict[str, Any]) -> int:
    if seg.get("duration_ms") is not None:
        try:
            return max(0, int(seg["duration_ms"]))
        except (TypeError, ValueError):
            pass
    try:
        return max(0, int(seg.get("end_ms", 0)) - int(seg.get("start_ms", 0)))
    except (TypeError, ValueError):
        return 0


def _arc_critical_ids(ctx: RunContext) -> set[str]:
    ids: set[str] = set()
    if ctx.artifact_exists("master/narrative_plan.json"):
        plan = ctx.read_json("master/narrative_plan.json")
        if isinstance(plan, dict):
            for key in ("must_keep_segment_ids", "spine_segment_ids", "anchor_segment_ids"):
                for sid in plan.get(key) or []:
                    if sid:
                        ids.add(str(sid))
            for act in plan.get("acts") or []:
                if isinstance(act, dict):
                    for sid in act.get("segment_ids") or []:
                        if sid:
                            ids.add(str(sid))
    try:
        from interview_mux.stages.audio_probes import authoritative_must_keep_ids

        ids |= authoritative_must_keep_ids(ctx)
    except Exception:
        pass
    return ids


def estimated_duration_sec(ctx: RunContext, ordered_ids: list[str]) -> float:
    if not ctx.artifact_exists("segments/manifest.json"):
        return 0.0
    man = ctx.read_json("segments/manifest.json")
    by_id = {
        str(s.get("segment_id") or s.get("id") or ""): s
        for s in (man.get("segments") or [])
        if isinstance(s, dict)
    }
    total_ms = 0
    for sid in ordered_ids:
        seg = by_id.get(str(sid))
        if seg:
            total_ms += _segment_duration_ms(seg)
    return total_ms / 1000.0


def auto_pack_selection_to_brief(
    ctx: RunContext,
    selection: dict[str, Any],
    *,
    stage: str = "full_master_ranking",
) -> dict[str, Any]:
    """Drop lowest-ranked non-arc-critical segments until within brief max duration.

    Returns updated selection (may be unchanged). Logs pipeline.selection.auto_pack.
    """
    from interview_mux.delivery_brief import load_delivery_brief
    from interview_mux.first_try import first_try_mode_enabled

    if not first_try_mode_enabled():
        return selection
    brief = load_delivery_brief(ctx)
    if not brief:
        return selection
    budget = brief.get("target_duration_sec") if isinstance(brief.get("target_duration_sec"), dict) else {}
    max_sec = budget.get("max")
    try:
        max_sec_f = float(max_sec) if max_sec is not None else None
    except (TypeError, ValueError):
        max_sec_f = None
    if max_sec_f is None or max_sec_f <= 0:
        return selection

    ordered = [str(x) for x in (selection.get("ordered_segment_ids") or []) if x]
    if not ordered:
        return selection
    est = estimated_duration_sec(ctx, ordered)
    if est <= max_sec_f:
        return selection

    critical = _arc_critical_ids(ctx)
    ranks = selection.get("segment_ranks") or selection.get("ranks") or {}
    if not isinstance(ranks, dict):
        ranks = {}

    def rank_of(sid: str) -> float:
        try:
            return float(ranks.get(sid, 9999))
        except (TypeError, ValueError):
            return 9999.0

    droppable = [sid for sid in ordered if sid not in critical]
    droppable.sort(key=rank_of, reverse=True)  # drop worst ranks first
    dropped: list[str] = []
    remaining = list(ordered)
    for sid in droppable:
        if estimated_duration_sec(ctx, remaining) <= max_sec_f:
            break
        if len(remaining) <= max(1, len(critical) or 1):
            break
        remaining = [x for x in remaining if x != sid]
        dropped.append(sid)

    if not dropped:
        return selection

    out = dict(selection)
    out["ordered_segment_ids"] = remaining
    excluded = list(out.get("excluded_segment_ids") or [])
    for sid in dropped:
        if sid not in excluded:
            excluded.append(sid)
    out["excluded_segment_ids"] = excluded
    meta = dict(out.get("_meta") or {})
    meta["auto_pack"] = {
        "dropped": dropped,
        "before_sec": round(est, 1),
        "after_sec": round(estimated_duration_sec(ctx, remaining), 1),
        "max_sec": max_sec_f,
    }
    out["_meta"] = meta
    ctx.log(
        f"Selection auto-pack: dropped {len(dropped)} segment(s) to fit brief max {max_sec_f:.0f}s",
        level="info",
        stage=stage,
        action_id="pipeline.selection.auto_pack",
        detail={
            "event": "selection_auto_pack",
            "dropped": dropped[:20],
            "before_sec": est,
            "after_sec": meta["auto_pack"]["after_sec"],
            "max_sec": max_sec_f,
        },
    )
    return out
