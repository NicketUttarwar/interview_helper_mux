"""Hybrid Shape consumers_bind: prefer plan order when complete + healthy.

Shape synthesis stays **dynamic by default** — this helper only decides whether a
bespoke plan's emitted order is healthy enough to bind for *this run*.
Global ``consumers_bind`` should remain false; callers use per-run authority.
"""

from __future__ import annotations

from typing import Any

from interview_mux.story_health import evaluate_story_health


def shape_order_bindable(
    plan: dict[str, Any] | None,
    *,
    kept_ids: set[str],
    narrative_plan: dict[str, Any] | None = None,
) -> tuple[bool, list[str], str]:
    """Return (ok, ordered_ids, reason)."""
    if not isinstance(plan, dict):
        return False, [], "no_plan"
    # A-03: hybrid bind requires authoritative complete (soft-gate emit alone must not bind).
    if str(plan.get("plan_status") or "") != "complete":
        return False, [], "plan_not_complete"
    from interview_mux.air_script import (
        load_air_script,
        omitted_segment_ids,
        ordered_ids_from_air_script,
    )

    air_ids = ordered_ids_from_air_script(plan)
    omitted = omitted_segment_ids(plan)
    script = load_air_script(plan) or {}
    if air_ids:
        lint = script.get("story_clarity") if isinstance(script.get("story_clarity"), dict) else {}
        follow = float(lint.get("story_followability") or 0.85) if lint else 0.85
        if lint and lint.get("ok") is False:
            return False, air_ids, "air_script_story_clarity_fail"
        if follow < 0.75:
            return False, air_ids, "air_script_followability_low"
        effective_kept = (kept_ids - omitted) if kept_ids else set(air_ids)
        filtered = [s for s in air_ids if s in effective_kept] if effective_kept else air_ids
        if effective_kept and set(filtered) != effective_kept:
            missing = sorted(effective_kept - set(filtered))
            if missing:
                return False, filtered, f"air_script_missing_kept:{missing[:6]}"
        return True, filtered, "air_script_bind"
    raw = plan.get("ordered_segment_ids")
    if not isinstance(raw, list) or not raw:
        return False, [], "plan_missing_ordered_segment_ids"
    ordered = [str(s) for s in raw if s]
    if not ordered:
        return False, [], "empty_plan_order"
    # Must cover kept ids (allow plan to be a subset only if equals after filter)
    filtered = [s for s in ordered if s in kept_ids] if kept_ids else ordered
    if kept_ids and set(filtered) != kept_ids:
        missing = sorted(kept_ids - set(filtered))
        extra_ok = True  # extras outside kept are dropped
        if missing:
            return False, filtered, f"plan_order_missing_kept:{missing[:6]}"
    health = evaluate_story_health(
        ordered=filtered,
        narrative_plan=narrative_plan,
        nle_overlay_applied=False,
    )
    if health.get("verdict") == "fail":
        return False, filtered, "story_health_fail"
    return True, filtered, "bind_ok"


def resolve_air_order(
    *,
    mastering_plan: dict[str, Any] | None,
    selection_ordered: list[str] | None,
    narrative_plan: dict[str, Any] | None = None,
    prefer_shape: bool = True,
) -> dict[str, Any]:
    """Pick Shape vs ranking order with hybrid lean-toward-bind."""
    sel = [str(s) for s in (selection_ordered or []) if s]
    kept = set(sel)
    if prefer_shape:
        ok, ordered, reason = shape_order_bindable(
            mastering_plan, kept_ids=kept, narrative_plan=narrative_plan
        )
        if ok and ordered:
            return {
                "order_authority": "shape",
                "ordered_segment_ids": ordered,
                "bind_reason": reason,
            }
        return {
            "order_authority": "ranking",
            "ordered_segment_ids": sel,
            "bind_reason": reason if prefer_shape else "prefer_shape_false",
        }
    return {
        "order_authority": "ranking",
        "ordered_segment_ids": sel,
        "bind_reason": "prefer_shape_false",
    }
