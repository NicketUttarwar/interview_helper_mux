"""Unify selection air-order with narrative_plan constraints.

Selection is authoritative for mix/EDL. Narrative constraints that contradict
the selected order are rewritten deterministically; material conflicts also
get a flagship LLM reconcile that proposes one enjoyable combined order.
"""

from __future__ import annotations

import copy
from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.selection_order_repair import ordering_constraint_errors


def material_order_conflicts(
    ordered: list[str],
    narrative_plan: dict[str, Any] | None,
) -> list[str]:
    """Human-readable conflicts between selection order and narrative constraints."""
    return ordering_constraint_errors(ordered, narrative_plan)


def rewrite_constraints_to_selection(
    narrative_plan: dict[str, Any],
    ordered: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Drop or flip constraints so they never contradict selection air order."""
    applied: list[dict[str, Any]] = []
    out = copy.deepcopy(narrative_plan)
    positions = {sid: idx for idx, sid in enumerate(ordered)}
    order_set = set(positions)
    constraints = out.get("ordering_constraints")
    if not isinstance(constraints, list):
        return out, applied
    kept: list[dict[str, Any]] = []
    for row in constraints:
        if not isinstance(row, dict):
            continue
        before = str(
            row.get("before_segment_id")
            or row.get("before")
            or row.get("setup_segment_id")
            or ""
        ).strip()
        after = str(
            row.get("after_segment_id")
            or row.get("after")
            or row.get("payoff_segment_id")
            or ""
        ).strip()
        if not before or not after or before == after:
            continue
        if before not in order_set or after not in order_set:
            applied.append(
                {
                    "action": "drop_constraint_outside_selection",
                    "before": before,
                    "after": after,
                }
            )
            continue
        if positions[before] < positions[after]:
            kept.append(
                {
                    **row,
                    "before_segment_id": before,
                    "after_segment_id": after,
                }
            )
            continue
        # Contradicts selection — flip to match air order (selection wins).
        flipped = {
            **row,
            "before_segment_id": after,
            "after_segment_id": before,
            "reason": (
                str(row.get("reason") or "")
                + " [flipped to match selection air order]"
            ).strip(),
            "reconciled_from_selection": True,
        }
        kept.append(flipped)
        applied.append(
            {
                "action": "flip_constraint_to_selection",
                "before": before,
                "after": after,
            }
        )
    if applied or kept != constraints:
        out["ordering_constraints"] = kept
    return out, applied


def _segment_blurbs(ctx: RunContext, ordered: list[str], *, max_chars: int = 160) -> list[dict[str, str]]:
    blurbs: list[dict[str, str]] = []
    man: dict[str, Any] = {}
    if ctx.artifact_exists("segments/manifest.json"):
        raw = ctx.read_json("segments/manifest.json")
        if isinstance(raw, dict):
            man = {
                str(s.get("segment_id")): s
                for s in (raw.get("segments") or [])
                if isinstance(s, dict) and s.get("segment_id")
            }
    for sid in ordered[:80]:
        row = man.get(sid) or {}
        text = str(row.get("text") or row.get("text_excerpt") or "").strip()
        if len(text) > max_chars:
            text = text[: max_chars - 1].rstrip() + "…"
        blurbs.append({"segment_id": sid, "excerpt": text})
    return blurbs


def _apply_reconciled_order(
    ctx: RunContext,
    ordered: list[str],
    *,
    source: str,
) -> list[str]:
    """Persist selection order + stamp hash. Returns the order written."""
    if not ordered:
        return ordered
    from interview_mux.order_hash import bump_order_lock

    if not ctx.artifact_exists("master/selection.json"):
        return ordered
    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        return ordered
    live = {
        str(s)
        for s in (sel.get("ordered_segment_ids") or sel.get("selected_segment_ids") or [])
        if s
    }
    # Keep only ids already in selection; preserve relative LLM order.
    cleaned = [sid for sid in ordered if sid in live] or list(sel.get("ordered_segment_ids") or [])
    # Append any selected ids the LLM dropped (end) so we never shrink coverage silently.
    for sid in sel.get("ordered_segment_ids") or []:
        s = str(sid)
        if s and s not in cleaned:
            cleaned.append(s)
    sel = dict(sel)
    previous = dict(sel)
    sel["ordered_segment_ids"] = cleaned
    sel["order_reconcile_source"] = source
    try:
        from interview_mux.air_order_integrity import (
            critical_violations,
            collect_violations,
            on_selection_order_changed,
            repair_air_order_integrity,
        )

        sel, _ = repair_air_order_integrity(ctx, sel)
        violations = collect_violations(ctx, sel)
        if critical_violations(violations) and source.startswith("flagship"):
            ctx.log(
                "order_reconcile: reverting LLM order — critical air_order integrity",
                level="error",
                stage="order_reconcile",
                detail=critical_violations(violations)[:4],
            )
            sel = previous
            sel["ordered_segment_ids"] = [
                str(s) for s in (previous.get("ordered_segment_ids") or []) if s
            ]
    except Exception as exc:
        ctx.log(
            f"order_reconcile integrity repair failed: {exc}",
            level="warning",
            stage="order_reconcile",
        )
    stamped = bump_order_lock(sel, source=f"order_reconcile:{source}")
    from interview_mux.air_order_boundary import commit_selection_mutation

    try:
        commit_selection_mutation(
            ctx,
            stamped,
            producer="order_reconcile",
            stage_key="order_reconcile",
            checkpoint_mode="repair",
            write_committed=True,
            skip_checkpoint=True,
        )
    except Exception:
        ctx.write_json("master/selection.json", stamped)
        try:
            from interview_mux.air_order_integrity import on_selection_order_changed

            on_selection_order_changed(
                ctx, source=f"order_reconcile:{source}", previous=previous, current=stamped
            )
        except Exception:
            pass
    try:
        from interview_mux.nugget_layup import adopt_layup_plan_to_selection

        adopt_layup_plan_to_selection(ctx, persist=True, stage="order_reconcile")
    except Exception:
        pass
    return cleaned


def flagship_order_reconcile(
    ctx: RunContext,
    *,
    ordered: list[str],
    narrative_plan: dict[str, Any],
    conflicts: list[str],
) -> dict[str, Any] | None:
    """Ask flagship LLM for one enjoyable combined order + aligned constraints.

    Fail-open: returns None on any LLM/parse error (caller keeps deterministic rewrite).
    """
    import json

    try:
        from interview_mux.stages.llm_runner import run_prompt_envelope
    except Exception:
        return None

    payload = {
        "goal": (
            "Reconcile selection air-order with narrative ordering constraints into "
            "one enjoyable podcast sequence. Prefer keeping the current selection "
            "order unless a small swap clearly improves setup→payoff."
        ),
        "selection_ordered_segment_ids": ordered[:80],
        "conflicts": conflicts[:12],
        "narrative_plan": {
            "arc_summary": narrative_plan.get("arc_summary"),
            "chapters": narrative_plan.get("chapters") or [],
            "ordering_constraints": narrative_plan.get("ordering_constraints") or [],
            "pacing_notes": narrative_plan.get("pacing_notes"),
        },
        "segment_blurbs": _segment_blurbs(ctx, ordered),
        "rules": [
            "Output only segment_ids already present in selection_ordered_segment_ids",
            "Do not invent speakers or segment ids",
            "ordering_constraints must match the returned order",
            "Keep nearly all selected segments; prefer swaps over drops",
        ],
    }
    try:
        envelope = run_prompt_envelope(
            "order_reconcile",
            "selection/order-reconcile.system.txt",
            user_content=json.dumps(payload, ensure_ascii=False),
            ctx=ctx,
            include_preamble=True,
            explicit_tier="flagship",
            task_kind="primary",
        )
    except Exception as exc:
        ctx.log(
            f"order_reconcile LLM failed (fail-open): {exc}",
            level="warning",
            stage="order_reconcile",
        )
        return None

    arts = envelope.get("artifacts") if isinstance(envelope, dict) else None
    if not isinstance(arts, dict):
        arts = envelope if isinstance(envelope, dict) else {}
    new_order = [str(s) for s in (arts.get("ordered_segment_ids") or []) if s]
    new_constraints = arts.get("ordering_constraints")
    rationale = str(arts.get("rationale") or arts.get("arc_summary") or "").strip()
    if not new_order:
        return None
    return {
        "ordered_segment_ids": new_order,
        "ordering_constraints": new_constraints if isinstance(new_constraints, list) else None,
        "rationale": rationale,
        "raw_artifacts": {k: arts.get(k) for k in ("ordered_segment_ids", "ordering_constraints", "rationale")},
    }


def reconcile_selection_and_narrative(
    ctx: RunContext,
    *,
    allow_llm: bool = True,
    label: str = "order_reconcile",
) -> dict[str, Any]:
    """Deterministic align + optional flagship reconcile. Safe to call repeatedly."""
    report: dict[str, Any] = {
        "ok": True,
        "conflicts_before": [],
        "conflicts_after": [],
        "actions": [],
        "llm_used": False,
    }
    if not ctx.artifact_exists("master/selection.json"):
        report["ok"] = False
        report["actions"].append({"action": "skip", "reason": "no_selection"})
        return report
    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        report["ok"] = False
        return report
    ordered = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
    if not ordered:
        report["actions"].append({"action": "skip", "reason": "empty_order"})
        return report

    plan: dict[str, Any] = {}
    if ctx.artifact_exists("master/narrative_plan.json"):
        raw = ctx.read_json("master/narrative_plan.json")
        if isinstance(raw, dict):
            plan = raw

    # Capture disagreements before any rewrite (for audit + LLM trigger).
    conflicts = material_order_conflicts(ordered, plan)
    report["conflicts_before"] = list(conflicts)

    # Always shrink chapters/constraints onto selection first.
    from interview_mux.artifact_repairs import align_narrative_plan_to_selection

    align_notes = align_narrative_plan_to_selection(ctx, ordered_ids=ordered)
    report["actions"].extend(align_notes)

    if ctx.artifact_exists("master/narrative_plan.json"):
        raw = ctx.read_json("master/narrative_plan.json")
        if isinstance(raw, dict):
            plan = raw

    # Deterministic rewrite: flip/drop any remaining contradictory constraints.
    if plan:
        rewritten, rewrite_notes = rewrite_constraints_to_selection(plan, ordered)
        if rewrite_notes:
            try:
                from interview_mux.write_staging import write_committed_json

                write_committed_json(ctx, "master/narrative_plan.json", rewritten)
            except Exception:
                ctx.write_json("master/narrative_plan.json", rewritten)
            plan = rewritten
            report["actions"].extend(rewrite_notes)

    conflicts_after_det = material_order_conflicts(ordered, plan)
    report["actions"].append(
        {
            "action": "deterministic_rewrite_done",
            "conflicts_remaining": len(conflicts_after_det),
        }
    )

    # Significant disagreements → flagship LLM for best combined enjoyable order
    # (may reorder slightly while keeping selection coverage).
    if allow_llm and conflicts:
        llm_result = flagship_order_reconcile(
            ctx,
            ordered=ordered,
            narrative_plan=plan,
            conflicts=conflicts,
        )
        if llm_result:
            report["llm_used"] = True
            new_order = _apply_reconciled_order(
                ctx,
                list(llm_result.get("ordered_segment_ids") or []),
                source="flagship_llm",
            )
            ordered = new_order
            report["actions"].append(
                {
                    "action": "flagship_order_reconcile",
                    "rationale": llm_result.get("rationale"),
                    "order_len": len(new_order),
                }
            )
            # Re-align narrative onto the LLM order.
            if isinstance(llm_result.get("ordering_constraints"), list):
                plan = dict(plan)
                plan["ordering_constraints"] = llm_result["ordering_constraints"]
                try:
                    from interview_mux.write_staging import write_committed_json

                    write_committed_json(ctx, "master/narrative_plan.json", plan)
                except Exception:
                    ctx.write_json("master/narrative_plan.json", plan)
            align_narrative_plan_to_selection(ctx, ordered_ids=ordered)
            if ctx.artifact_exists("master/narrative_plan.json"):
                raw = ctx.read_json("master/narrative_plan.json")
                if isinstance(raw, dict):
                    plan = raw
                    rewritten, rewrite_notes = rewrite_constraints_to_selection(plan, ordered)
                    if rewrite_notes:
                        try:
                            from interview_mux.write_staging import write_committed_json

                            write_committed_json(ctx, "master/narrative_plan.json", rewritten)
                        except Exception:
                            ctx.write_json("master/narrative_plan.json", rewritten)
                        plan = rewritten
                        report["actions"].extend(rewrite_notes)

    report["conflicts_after"] = material_order_conflicts(ordered, plan)
    report["ok"] = not report["conflicts_after"]
    try:
        from interview_mux.write_staging import write_committed_json

        write_committed_json(
            ctx,
            "master/order_reconcile.json",
            {
                "version": 1,
                "label": label,
                **report,
                "ordered_segment_ids": ordered,
            },
        )
    except Exception:
        ctx.write_json(
            "master/order_reconcile.json",
            {"version": 1, "label": label, **report, "ordered_segment_ids": ordered},
        )
    ctx.log(
        f"{label}: conflicts {len(report['conflicts_before'])}→{len(report['conflicts_after'])} "
        f"llm={report['llm_used']} actions={len(report['actions'])}",
        level="info" if report["ok"] else "warning",
        stage=label,
    )
    return report
