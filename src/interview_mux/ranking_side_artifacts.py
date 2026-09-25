"""Post-ranking side artifacts — owned by first consumer after ranking (S6).

Builds reorder bridges, refreshes story_health (with bridges), speaker_delivery_plan,
and gap VO rebudget notes. Must not mutate ``master/selection.json`` membership.
"""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def ensure_ranking_side_artifacts(
    ctx: RunContext,
    *,
    stage_key: str = "selection_order_sanitize",
) -> None:
    """Fail-open side writes after sealed selection exists (FMR S6)."""
    try:
        from interview_mux.split_plan import clear_split_rerank_cascade

        clear_split_rerank_cascade(ctx)
    except Exception:
        pass

    ordered: list[str] = []
    try:
        if ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                ordered = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
    except Exception:
        ordered = []

    plan: dict[str, Any] | None = None
    mp: dict[str, Any] | None = None
    by_id: dict[str, Any] = {}
    hook_id: str | None = None
    try:
        if ctx.artifact_exists("master/narrative_plan.json"):
            raw = ctx.read_json("master/narrative_plan.json")
            plan = raw if isinstance(raw, dict) else None
        if ctx.artifact_exists("mastering/mastering_plan.json"):
            raw_mp = ctx.read_json("mastering/mastering_plan.json")
            mp = raw_mp if isinstance(raw_mp, dict) else None
        if ctx.artifact_exists("segments/manifest.json"):
            man = ctx.read_json("segments/manifest.json")
            by_id = {
                str(s["segment_id"]): s
                for s in (man.get("segments") or [])
                if isinstance(s, dict) and s.get("segment_id")
            }
        if ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict) and sel.get("native_cold_open_segment_id"):
                hook_id = str(sel.get("native_cold_open_segment_id"))
    except Exception:
        pass

    try:
        from interview_mux.reorder_bridges import build_reorder_bridges
        from interview_mux.bridge_voice_policy import annotate_reorder_bridges

        chapter_ends: set[str] = set()
        if isinstance(plan, dict):
            for ch in plan.get("chapters") or []:
                if isinstance(ch, dict):
                    ids = [str(x) for x in (ch.get("segment_ids") or []) if x]
                    if ids:
                        chapter_ends.add(ids[-1])
        narrative_mode = None
        if isinstance(mp, dict) and mp.get("narrative_mode"):
            narrative_mode = str(mp.get("narrative_mode"))
        elif isinstance(plan, dict) and plan.get("narrative_mode"):
            narrative_mode = str(plan.get("narrative_mode"))
        vo_shape = None
        try:
            from interview_mux.speaker_delivery_plan import episode_vo_identity

            vo_shape = str((episode_vo_identity(ctx) or {}).get("vo_shape") or "") or None
        except Exception:
            vo_shape = None
        bridges = annotate_reorder_bridges(
            build_reorder_bridges(ordered, by_id, chapter_ends=chapter_ends),
            narrative_mode=narrative_mode,
            episode_vo_shape=vo_shape,
        )
        try:
            from interview_mux.bridge_completeness import mint_needs_spoken_glue_placeholders

            bridges = mint_needs_spoken_glue_placeholders(ctx, bridges, ordered=ordered)
        except Exception:
            pass
        ctx.write_json(
            "understanding/reorder_bridges.json", bridges, stage_key=stage_key
        )
    except Exception as exc:
        try:
            ctx.log(
                f"reorder_bridges side artifacts skipped: {exc}",
                level="warning",
                stage=stage_key,
            )
        except Exception:
            pass

    try:
        from interview_mux.story_health import evaluate_story_health

        gap = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else None
        )
        cov = (
            ctx.read_json("master/coverage_audit.json")
            if ctx.artifact_exists("master/coverage_audit.json")
            else None
        )
        bridges_doc = (
            ctx.read_json("understanding/reorder_bridges.json")
            if ctx.artifact_exists("understanding/reorder_bridges.json")
            else None
        )
        health = evaluate_story_health(
            ordered=ordered,
            narrative_plan=plan,
            coverage_audit=cov if isinstance(cov, dict) else None,
            reorder_bridges=bridges_doc if isinstance(bridges_doc, dict) else None,
            gap_report=gap if isinstance(gap, dict) else None,
            hook_segment_id=hook_id,
            ctx=ctx,
        )
        ctx.write_json("master/story_health.json", health, stage_key=stage_key)
        if health.get("verdict") in {"fail", "warn"}:
            ctx.log(
                f"story_health {health.get('verdict')} after ranking sides "
                f"({health.get('error_count')} issues)",
                level="warning",
                stage=stage_key,
                detail=(health.get("issues") or [])[:6],
            )
    except Exception as exc:
        try:
            ctx.log(
                f"story_health side artifacts skipped: {exc}",
                level="warning",
                stage=stage_key,
            )
        except Exception:
            pass

    try:
        from interview_mux.speaker_delivery_plan import write_speaker_delivery_plan

        write_speaker_delivery_plan(ctx, stage_key=stage_key)
    except Exception as exc:
        try:
            ctx.log(
                f"speaker_delivery_plan skipped: {exc}",
                level="warning",
                stage=stage_key,
            )
        except Exception:
            pass

    try:
        from interview_mux.gap_vo_rebudget import note_gap_vo_rebudget_after_selection

        note_gap_vo_rebudget_after_selection(ctx, stage_key=stage_key)
    except Exception:
        pass
