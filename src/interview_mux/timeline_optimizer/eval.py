"""Score optimizer candidates (cheap proxies; full remaster optional later)."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def _segments_by_id(ctx: RunContext) -> dict[str, dict[str, Any]]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return {}
    man = ctx.read_json("segments/manifest.json")
    return {
        str(s["segment_id"]): s
        for s in ((man or {}).get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    }


def score_candidate(ctx: RunContext, candidate: dict[str, Any]) -> dict[str, Any]:
    """Return score breakdown; higher total is better."""
    from interview_mux.bridge_completeness import missing_reorder_bridges
    from interview_mux.listen_quality import evaluate_listen_critic
    from interview_mux.reorder_bridges import build_reorder_bridges
    from interview_mux.bridge_voice_policy import annotate_reorder_bridges
    from interview_mux.story_health import evaluate_story_health

    ordered = [str(s) for s in (candidate.get("ordered_segment_ids") or []) if s]
    by_id = _segments_by_id(ctx)
    plan = (
        ctx.read_json("master/narrative_plan.json")
        if ctx.artifact_exists("master/narrative_plan.json")
        else None
    )
    bridges = annotate_reorder_bridges(
        build_reorder_bridges(ordered, by_id),
        narrative_mode=None,
    )
    gap = candidate.get("gap_report")
    tr = candidate.get("transitions")
    health = evaluate_story_health(
        ordered=ordered,
        narrative_plan=plan if isinstance(plan, dict) else None,
        reorder_bridges=bridges,
        gap_report=gap if isinstance(gap, dict) else None,
        transitions=tr if isinstance(tr, dict) else None,
        nle_overlay_applied=False,
    )
    hook_id = None
    if ctx.artifact_exists("understanding/episode_structure.json"):
        try:
            es = (__import__("interview_mux.episode_structure", fromlist=["load_episode_structure"]).load_episode_structure(ctx) or {})
            if isinstance(es, dict):
                hook_id = es.get("hook_segment_id")
        except Exception:
            hook_id = None
    critic = evaluate_listen_critic(
        ordered=ordered,
        story_health=health,
        hook_segment_id=str(hook_id) if hook_id else None,
        segments_by_id=by_id,
        narrative_plan=plan if isinstance(plan, dict) else None,
        gap_report=gap if isinstance(gap, dict) else None,
        sound_design_plan=candidate.get("sound_design_plan")
        if isinstance(candidate.get("sound_design_plan"), dict)
        else None,
    )
    missing = missing_reorder_bridges(
        bridges,
        gap_report=gap if isinstance(gap, dict) else None,
        transitions=tr if isinstance(tr, dict) else None,
    )

    score = 100.0
    if health.get("verdict") == "fail":
        score -= 35.0 + 6.0 * float(health.get("error_count") or 0)
    elif health.get("verdict") == "warn":
        score -= 8.0 + 2.0 * float(health.get("warning_count") or 0)
    score -= min(20.0, 2.0 * len(missing))
    q = float(critic.get("quality_score") or 50.0)
    score = 0.55 * score + 0.45 * q
    # Prefer fewer exclusions unless they were intentional low-energy cuts
    excl = candidate.get("excluded_segment_ids") or []
    if isinstance(excl, list) and len(excl) > 8:
        score -= 0.5 * (len(excl) - 8)
    # Reward hook early
    if hook_id and ordered and str(hook_id) in ordered[:3]:
        score += 4.0

    return {
        "score": round(score, 2),
        "story_health": health,
        "listen_critic": critic,
        "missing_bridges": len(missing),
        "bridge_count": len(bridges.get("pairs") or []),
    }
