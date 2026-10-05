"""Deterministic story-health scorecard for master ordering."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from interview_mux.selection_order_repair import (
    finale_tail_errors,
    ordering_constraint_errors,
)

if TYPE_CHECKING:
    from interview_mux.run_context import RunContext


def evaluate_story_health(
    *,
    ordered: list[str],
    narrative_plan: dict[str, Any] | None = None,
    coverage_audit: dict[str, Any] | None = None,
    reorder_bridges: dict[str, Any] | None = None,
    gap_report: dict[str, Any] | None = None,
    transitions: dict[str, Any] | None = None,
    nle_overlay_applied: bool = False,
    hook_segment_id: str | None = None,
    ctx: RunContext | None = None,
) -> dict[str, Any]:
    """Return story_health document.

    App-base failures → verdict ``fail`` (caller should repair).
    Post-NLE-only chronology issues → ``warn`` when ``nle_overlay_applied`` (ship anyway).
    """
    issues: list[dict[str, Any]] = []
    ordered_ids = [str(s) for s in ordered if s]

    for msg in ordering_constraint_errors(ordered_ids, narrative_plan):
        issues.append({"code": "ordering_constraint", "severity": "error", "message": msg})
    selection_chapters = None
    if ctx is not None:
        try:
            if ctx.artifact_exists("master/selection.json"):
                sel = ctx.read_json("master/selection.json")
                sel_order = [str(s) for s in ((sel or {}).get("ordered_segment_ids") or []) if s]
                if sel_order == ordered_ids:
                    selection_chapters = (sel or {}).get("chapters")
        except Exception:
            selection_chapters = None
    for msg in finale_tail_errors(ordered_ids, narrative_plan, selection_chapters):
        issues.append({"code": "finale_tail", "severity": "error", "message": msg})

    if ctx is not None and ordered_ids:
        from interview_mux.air_order_integrity import (
            late_opening_cluster_violations,
            reverse_tape_jump_violations,
        )

        for v in reverse_tape_jump_violations(ctx, ordered_ids):
            issues.append(
                {
                    "code": "reverse_tape_jump",
                    "severity": "error",
                    "message": str(v.get("message") or v.get("code") or ""),
                }
            )
        for v in late_opening_cluster_violations(ctx, ordered_ids):
            issues.append(
                {
                    "code": "late_opening_cluster",
                    "severity": "error",
                    "message": str(v.get("message") or v.get("code") or ""),
                }
            )

    if ordered_ids and hook_segment_id and str(hook_segment_id) not in {
        ordered_ids[0],
        *(ordered_ids[:3] if len(ordered_ids) >= 3 else ordered_ids),
    }:
        # Soft: hook preferred early but not always seg_0
        issues.append(
            {
                "code": "hook_not_early",
                "severity": "warn",
                "message": f"hook segment {hook_segment_id} not in first three air slots",
            }
        )

    # Bridge completeness for declared reorder pairs (pair-specific glue only)
    from interview_mux.bridge_completeness import missing_reorder_bridges

    # Same inputs as bridge completeness and the mint: justified layup skips,
    # hitch air already seated in the EDL, and pairs the mint must never
    # bridge. Without them this read "fail" with 4 missing bridges while
    # bridge completeness was complete (exec_017, ISSUES 166).
    skip_ids = None
    edl_doc = None
    if ctx is not None:
        try:
            from interview_mux.bridge_completeness import justified_skip_before_ids

            skip_ids = justified_skip_before_ids(ctx)
            if ctx.artifact_exists("master/edl.json"):
                edl_doc = ctx.read_json("master/edl.json")
        except Exception:
            skip_ids, edl_doc = None, None
    misses = missing_reorder_bridges(
        reorder_bridges if isinstance(reorder_bridges, dict) else None,
        gap_report=gap_report if isinstance(gap_report, dict) else None,
        transitions=transitions if isinstance(transitions, dict) else None,
        justified_skip_before_ids=skip_ids,
        edl=edl_doc if isinstance(edl_doc, dict) else None,
    )
    if ctx is not None and misses:
        try:
            from interview_mux.bridge_completeness import forbidden_bridge_pairs

            forbidden = forbidden_bridge_pairs(ctx, misses)
            misses = [
                m
                for m in misses
                if (m.get("after_segment_id"), m.get("before_segment_id")) not in forbidden
            ]
        except Exception:
            pass
    for miss in misses:
        a = miss.get("after_segment_id")
        b = miss.get("before_segment_id")
        issues.append(
            {
                "code": "missing_reorder_bridge",
                "severity": "error",
                "message": f"missing bridge for reorder adjacency {a} -> {b}",
            }
        )

    if isinstance(coverage_audit, dict):
        orphans = coverage_audit.get("orphan_segment_ids") or []
        if orphans and isinstance(orphans, list) and len(orphans) > 12:
            issues.append(
                {
                    "code": "many_orphans",
                    "severity": "warn",
                    "message": f"coverage_audit lists {len(orphans)} orphan segments",
                }
            )

    errors = [i for i in issues if i.get("severity") == "error"]
    warns = [i for i in issues if i.get("severity") == "warn"]
    if errors and nle_overlay_applied:
        # Operator overlay chronology: warn and ship
        verdict = "warn"
        for i in errors:
            i["severity"] = "warn"
            i["nle_softened"] = True
        warns = [i for i in issues if i.get("severity") == "warn"]
        errors = []
    elif errors:
        verdict = "fail"
    elif warns:
        verdict = "warn"
    else:
        verdict = "pass"

    return {
        "version": 1,
        "verdict": verdict,
        "nle_overlay_applied": bool(nle_overlay_applied),
        "ordered_segment_ids": ordered_ids,
        "error_count": len(errors),
        "warning_count": len(warns),
        "issues": issues,
    }
