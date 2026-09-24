"""Deterministic open-shape repair for ranking and downstream remutate.

Repair-then-commit: fix late-opening / guest-first / hook placement without
refusing selection persist solely on open-shape lint.
"""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

OPEN_WINDOW_SLOTS = 3


def open_shape_criticals(
    ctx: RunContext,
    selection: dict[str, Any],
) -> list[dict[str, Any]]:
    """Collect open-shape critical integrity violations for a selection."""
    from interview_mux.air_order_integrity import (
        chapter_opening_mask_violations,
        late_opening_cluster_violations,
    )

    ordered = [str(s) for s in (selection.get("ordered_segment_ids") or []) if s]
    out: list[dict[str, Any]] = []
    try:
        out.extend(late_opening_cluster_violations(ctx, ordered))
    except Exception:
        pass
    try:
        out.extend(chapter_opening_mask_violations(ctx, selection))
    except Exception:
        pass
    return [v for v in out if str(v.get("severity") or "").lower() == "critical" or v.get("code")]


def candidate_has_open_shape_criticals(
    ctx: RunContext | None,
    ordered: list[str],
    *,
    selection_shell: dict[str, Any] | None = None,
) -> bool:
    """True when an order candidate still has late-opening / mask criticals."""
    if not ordered:
        return True
    shell = dict(selection_shell or {})
    shell["ordered_segment_ids"] = list(ordered)
    if ctx is None:
        return False
    return bool(open_shape_criticals(ctx, shell))


def repair_open_shape_selection(
    ctx: RunContext,
    selection: dict[str, Any],
    *,
    hook_segment_id: str | None = None,
    stage: str = "full_master_ranking",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """One-pass open-shape repair: hook early + opening-tape integrity.

    Never raises solely for remaining open-shape issues — callers commit anyway.
    """
    from interview_mux.air_order_integrity import repair_air_order_integrity
    from interview_mux.listen_quality import ensure_hook_early

    out = dict(selection)
    actions: list[dict[str, Any]] = []
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    hook = hook_segment_id or out.get("native_cold_open_segment_id")
    if hook:
        ordered, moved = ensure_hook_early(ordered, str(hook))
        if moved:
            out["ordered_segment_ids"] = ordered
            actions.append({"action": "ensure_hook_early", "hook": str(hook)})
    try:
        repaired, integ_actions = repair_air_order_integrity(ctx, out)
        out = repaired
        actions.extend(integ_actions)
    except Exception as exc:
        try:
            ctx.log(
                f"open_shape_repair integrity pass skipped: {exc}",
                level="warning",
                stage=stage,
            )
        except Exception:
            pass
    if actions:
        try:
            ctx.log(
                f"open_shape_repair: {len(actions)} action(s)",
                level="info",
                stage=stage,
                detail=actions[:8],
            )
        except Exception:
            pass
    return out, actions


def preserve_ranking_membership(
    prior_ordered: list[str],
    new_ordered: list[str],
    *,
    manifest_ids: set[str] | None = None,
) -> list[str]:
    """Keep prior ranking membership; new order is a reordering head when possible."""
    prior = [str(s) for s in prior_ordered if s]
    new = [str(s) for s in new_ordered if s]
    if not prior:
        return new
    allowed = manifest_ids if manifest_ids is not None else set(prior) | set(new)
    prior_kept = [s for s in prior if s in allowed]
    if not new:
        return prior_kept
    head = [s for s in new if s in set(prior_kept)]
    if not head:
        # Completely foreign order — keep intersection then append prior tail.
        head = [s for s in new if s in allowed]
    prior_set = set(head)
    tail = [s for s in prior_kept if s not in prior_set]
    return head + tail


def cover_ranking_manifest_membership(
    ctx: RunContext,
    artifacts: dict[str, Any],
    *,
    reason: str = "ranking_membership_cover",
) -> dict[str, Any]:
    """Stamp manifest orphans into excluded so ordered∪excluded covers the universe.

    exec_13177: CTA/NLE materialize added children to ``segments/manifest.json``
    while ranking drops removed them from ordered without excluded → pre-flush
    ``manifest segment X missing from ordered ∪ excluded``.
    """
    out = dict(artifacts) if isinstance(artifacts, dict) else {}
    if not ctx.artifact_exists("segments/manifest.json"):
        return out
    try:
        man = ctx.read_json("segments/manifest.json")
    except Exception:
        return out
    if not isinstance(man, dict):
        return out
    manifest_ids = {
        str(s.get("segment_id") or "")
        for s in (man.get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    }
    ordered = {str(s) for s in (out.get("ordered_segment_ids") or []) if s}
    excl = list(out.get("excluded_segment_ids") or [])
    excl_ids: set[str] = set()
    for row in excl:
        if isinstance(row, dict):
            excl_ids.add(str(row.get("segment_id") or ""))
        else:
            excl_ids.add(str(row or ""))
    orphans = sorted(manifest_ids - ordered - excl_ids)
    if not orphans:
        return out
    rationales = (
        dict(out.get("exclude_rationales") or {})
        if isinstance(out.get("exclude_rationales"), dict)
        else {}
    )
    for sid in orphans:
        excl.append({"segment_id": sid, "reason": reason})
        rationales[sid] = reason
    out["excluded_segment_ids"] = excl
    out["exclude_rationales"] = rationales
    try:
        ctx.log(
            f"ranking_membership_cover: excluded {len(orphans)} manifest orphan(s)",
            level="info",
            stage="full_master_ranking",
            detail={"orphans": orphans[:24]},
        )
    except Exception:
        pass
    return out


def protect_open_window_order(
    previous_ordered: list[str],
    proposed_ordered: list[str],
    *,
    open_slots: int = OPEN_WINDOW_SLOTS,
    allow_override: bool = False,
) -> list[str]:
    """Keep the first K air slots from previous unless open_window_override.

    Remutate may reorder the body freely; open-window natives stay put.
    """
    prev = [str(s) for s in previous_ordered if s]
    prop = [str(s) for s in proposed_ordered if s]
    if allow_override or not prev or not prop:
        return prop
    k = max(1, int(open_slots))
    head = prev[:k]
    head_set = set(head)
    # If proposed already keeps the same head membership+order, accept.
    if prop[: len(head)] == head:
        return prop
    body = [s for s in prop if s not in head_set]
    # Preserve any prior head ids that were dropped from proposed (re-append body only).
    return head + body


def apply_open_window_and_repair(
    ctx: RunContext,
    previous: dict[str, Any] | None,
    proposed: dict[str, Any],
    *,
    mutation_class: str | None = None,
    stage: str = "edl_narrative_remutate",
) -> dict[str, Any]:
    """Freeze open window (unless override) then run shared open-shape repair."""
    out = dict(proposed)
    prev_ids = [
        str(s) for s in ((previous or {}).get("ordered_segment_ids") or []) if s
    ]
    prop_ids = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    allow = str(mutation_class or "") == "open_window_override"
    protected = protect_open_window_order(
        prev_ids, prop_ids, allow_override=allow
    )
    if protected != prop_ids:
        out["ordered_segment_ids"] = protected
        try:
            ctx.log(
                "open_window_freeze: restored first "
                f"{OPEN_WINDOW_SLOTS} slots from prior selection",
                level="info",
                stage=stage,
            )
        except Exception:
            pass
    repaired, _ = repair_open_shape_selection(ctx, out, stage=stage)
    return repaired


def build_deterministic_ranking_fallback(ctx: RunContext) -> dict[str, Any] | None:
    """Chapter → Shape → hard-keep seed when LLM/envelope yields no order."""
    from interview_mux.rank_candidates import chapter_order_from_plan

    manifest_ids: set[str] = set()
    if ctx.artifact_exists("segments/manifest.json"):
        try:
            man = ctx.read_json("segments/manifest.json")
            for row in (man.get("segments") or []) if isinstance(man, dict) else []:
                if isinstance(row, dict) and row.get("segment_id"):
                    manifest_ids.add(str(row["segment_id"]))
        except Exception:
            pass
    if not manifest_ids:
        return None

    ordered: list[str] = []
    source = ""
    plan = None
    if ctx.artifact_exists("master/narrative_plan.json"):
        try:
            plan = ctx.read_json("master/narrative_plan.json")
        except Exception:
            plan = None
    chapter = chapter_order_from_plan(plan if isinstance(plan, dict) else None)
    chapter = [s for s in chapter if s in manifest_ids]
    if chapter:
        ordered = chapter
        source = "narrative_chapters"

    if not ordered and ctx.artifact_exists("mastering/mastering_plan.json"):
        try:
            mp = ctx.read_json("mastering/mastering_plan.json")
            shape = [
                str(s)
                for s in ((mp or {}).get("ordered_segment_ids") or [])
                if str(s) in manifest_ids
            ]
            if shape:
                ordered = shape
                source = "shape"
        except Exception:
            pass

    if not ordered:
        try:
            from interview_mux.hard_keep import hard_keep_segment_ids

            keeps = [s for s in sorted(hard_keep_segment_ids(ctx)) if s in manifest_ids]
            if keeps:
                ordered = keeps
                source = "hard_keep"
        except Exception:
            pass

    if not ordered:
        return None
    return {
        "ordered_segment_ids": ordered,
        "excluded_segment_ids": [],
        "notes": f"deterministic_ranking_fallback:{source}",
        "order_authority": source or "fallback",
        "order_bind_reason": f"deterministic_fallback:{source}",
    }
