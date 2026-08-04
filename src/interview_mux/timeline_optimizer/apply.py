"""Promote best optimizer candidate into live run artifacts (+ optional remaster)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.timeline_optimizer.state import (
    load_best,
    load_optimizer_state,
    save_optimizer_state,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def remaster_sync(ctx: RunContext, *, until_mix: bool = True) -> None:
    """Synchronously rebuild EDL→mix after promoting a new order (no JobRunner)."""
    from interview_mux.stages import assembly
    from interview_mux.v2.config import DELIVERY_ORDER

    for sid in DELIVERY_ORDER:
        if sid not in {
            "edl",
            "assembly_preview",
            "listen_delight_audit",
            "sfx_prompt_craft",
            "mmaudio_sfx",
            "mix",
            "junction_snip_qa",
        }:
            continue
        if sid == "mix" and not until_mix:
            break
        if sid == "junction_snip_qa" and not until_mix:
            break
        marker = ctx.final_path(".stage_done", sid)
        if marker.is_file():
            try:
                marker.unlink()
            except OSError:
                pass

    # Rebuild EDL + mix; reuse existing MMAudio assets when present
    assembly.run_edl(ctx)
    assembly.run_mix(ctx)


def take_best_candidate(
    ctx: RunContext,
    *,
    remaster: bool = False,
    runner: Any | None = None,
    sync_remaster: bool = False,
) -> dict[str, Any]:
    """Write best candidate into selection/transitions/gap/SDP; optionally remaster."""
    best = load_best(ctx)
    if not best:
        return {"ok": False, "error": "no_best_candidate"}

    ordered = [str(s) for s in (best.get("ordered_segment_ids") or []) if s]
    if not ordered:
        return {"ok": False, "error": "empty_order"}

    # Selection
    sel = (
        ctx.read_json("master/selection.json")
        if ctx.artifact_exists("master/selection.json")
        else {"version": 1}
    )
    if not isinstance(sel, dict):
        sel = {"version": 1}
    prev_order = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
    sel = dict(sel)
    sel["ordered_segment_ids"] = ordered
    if best.get("excluded_segment_ids"):
        sel["excluded_segment_ids"] = list(best.get("excluded_segment_ids") or [])
    sel["order_authority"] = "timeline_optimizer"
    sel["optimizer_candidate_id"] = best.get("candidate_id")
    sel["optimizer_score"] = best.get("score")
    from interview_mux.artifact_writes import write_validated_artifact

    write_validated_artifact(
        ctx,
        "master/selection.json",
        sel,
        merge_from_disk=False,
        stage_key="timeline_optimizer",
    )

    if isinstance(best.get("transitions"), dict):
        ctx.write_json("master/transitions.json", best["transitions"])
    if isinstance(best.get("gap_report"), dict):
        ctx.write_json("understanding/gap_report.json", best["gap_report"])
    if isinstance(best.get("sound_design_plan"), dict):
        ctx.write_json(
            "understanding/sound_design_plan.json", best["sound_design_plan"]
        )

    # Refresh bridges + health for promoted order
    try:
        from interview_mux.bridge_voice_policy import annotate_reorder_bridges
        from interview_mux.reorder_bridges import build_reorder_bridges
        from interview_mux.story_health import evaluate_story_health

        by_id = {}
        if ctx.artifact_exists("segments/manifest.json"):
            man = ctx.read_json("segments/manifest.json")
            by_id = {
                str(s["segment_id"]): s
                for s in ((man or {}).get("segments") or [])
                if isinstance(s, dict) and s.get("segment_id")
            }
        bridges = annotate_reorder_bridges(build_reorder_bridges(ordered, by_id))
        ctx.write_json("understanding/reorder_bridges.json", bridges)
        plan = (
            ctx.read_json("master/narrative_plan.json")
            if ctx.artifact_exists("master/narrative_plan.json")
            else None
        )
        health = evaluate_story_health(
            ordered=ordered,
            narrative_plan=plan if isinstance(plan, dict) else None,
            reorder_bridges=bridges,
            gap_report=best.get("gap_report")
            if isinstance(best.get("gap_report"), dict)
            else None,
            transitions=best.get("transitions")
            if isinstance(best.get("transitions"), dict)
            else None,
        )
        ctx.write_json("master/story_health.json", health)
    except Exception as exc:
        ctx.log(f"optimizer promote health refresh: {exc}", level="warning", stage="timeline_optimizer")

    state = load_optimizer_state(ctx)
    promotions = list(state.get("promotions") or [])
    promotions.append(
        {
            "at": _now(),
            "candidate_id": best.get("candidate_id"),
            "score": best.get("score"),
            "remaster": bool(remaster or sync_remaster),
        }
    )
    state["promotions"] = promotions[-20:]
    state["operator_took_best"] = True
    order_changed = prev_order != ordered
    if order_changed:
        state["promoted_needs_remaster"] = True
    save_optimizer_state(ctx, state)

    def _meta(m: dict) -> None:
        m["timeline_optimizer_promoted"] = {
            "candidate_id": best.get("candidate_id"),
            "score": best.get("score"),
            "at": _now(),
            "needs_remaster": order_changed,
        }

    ctx.mutate_run_meta(_meta)

    remaster_started = False
    if (remaster or sync_remaster) and order_changed:
        if runner is not None and not sync_remaster:
            try:
                runner.invalidate_from(ctx.run_id, "edl")
                runner.start(
                    ctx.run_id,
                    mode="delivery",
                    from_stage="edl",
                    until_stage="mix",
                )
                remaster_started = True
                state = load_optimizer_state(ctx)
                state["promoted_needs_remaster"] = False
                save_optimizer_state(ctx, state)
            except Exception as exc:
                ctx.log(
                    f"optimizer remaster start failed: {exc}",
                    level="warning",
                    stage="timeline_optimizer",
                )
        else:
            try:
                def _flag(m: dict) -> None:
                    m["timeline_optimizer_remastering"] = True

                ctx.mutate_run_meta(_flag)
                remaster_sync(ctx, until_mix=True)
                remaster_started = True
                state = load_optimizer_state(ctx)
                state["promoted_needs_remaster"] = False
                save_optimizer_state(ctx, state)
            except Exception as exc:
                ctx.log(
                    f"optimizer sync remaster failed: {exc}",
                    level="warning",
                    stage="timeline_optimizer",
                )
            finally:
                def _clear(m: dict) -> None:
                    m["timeline_optimizer_remastering"] = False

                try:
                    ctx.mutate_run_meta(_clear)
                except Exception:
                    pass

    ctx.log(
        f"timeline_optimizer take-best: {best.get('candidate_id')} "
        f"score={best.get('score')} remaster={remaster_started}",
        level="success",
        stage="timeline_optimizer",
    )
    return {
        "ok": True,
        "candidate_id": best.get("candidate_id"),
        "score": best.get("score"),
        "ordered_segment_ids": ordered,
        "remaster_started": remaster_started,
        "order_changed": order_changed,
    }
