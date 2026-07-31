"""Dual-candidate master order: score Shape vs ranking and commit the healthier listen."""

from __future__ import annotations

from typing import Any

from interview_mux.story_health import evaluate_story_health


def _score_order(
    ordered: list[str],
    *,
    narrative_plan: dict[str, Any] | None,
    reorder_bridges: dict[str, Any] | None = None,
    gap_report: dict[str, Any] | None = None,
    transitions: dict[str, Any] | None = None,
    hook_segment_id: str | None = None,
) -> tuple[float, dict[str, Any]]:
    """Higher is better. Uses story_health + simple listen heuristics."""
    health = evaluate_story_health(
        ordered=ordered,
        narrative_plan=narrative_plan,
        reorder_bridges=reorder_bridges,
        gap_report=gap_report,
        transitions=transitions,
        nle_overlay_applied=False,
        hook_segment_id=hook_segment_id,
    )
    score = 100.0
    if health.get("verdict") == "fail":
        score -= 40.0 + 8.0 * float(health.get("error_count") or 0)
    elif health.get("verdict") == "warn":
        score -= 10.0 + 3.0 * float(health.get("warning_count") or 0)

    # Prefer fewer reorder bridges (less VO glue burden)
    pairs = []
    if isinstance(reorder_bridges, dict):
        pairs = [p for p in (reorder_bridges.get("pairs") or []) if isinstance(p, dict)]
    score -= min(25.0, 1.5 * len(pairs))

    # Hook early bonus
    if hook_segment_id and ordered:
        try:
            idx = ordered.index(str(hook_segment_id))
            score += max(0.0, 12.0 - 4.0 * idx)
        except ValueError:
            score -= 8.0

    # Mild preference for finishing with declared finale chapter members
    if isinstance(narrative_plan, dict):
        chapters = [c for c in (narrative_plan.get("chapters") or []) if isinstance(c, dict)]
        if chapters and ordered:
            finale_ids = [str(x) for x in (chapters[-1].get("segment_ids") or []) if x]
            if finale_ids and ordered[-1] in finale_ids:
                score += 6.0

    return score, health


def pick_best_order(
    candidates: list[dict[str, Any]],
    *,
    narrative_plan: dict[str, Any] | None = None,
    segments_by_id: dict[str, dict[str, Any]] | None = None,
    gap_report: dict[str, Any] | None = None,
    transitions: dict[str, Any] | None = None,
    hook_segment_id: str | None = None,
) -> dict[str, Any]:
    """Score candidates and return rank_candidates doc + winner order.

    Each candidate: ``{"source": str, "ordered_segment_ids": list[str]}``.
    """
    from interview_mux.reorder_bridges import build_reorder_bridges

    by_id = segments_by_id or {}
    scored: list[dict[str, Any]] = []
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        ordered = [str(s) for s in (cand.get("ordered_segment_ids") or []) if s]
        if not ordered:
            continue
        bridges = build_reorder_bridges(ordered, by_id) if by_id else {"pairs": [], "count": 0}
        score, health = _score_order(
            ordered,
            narrative_plan=narrative_plan,
            reorder_bridges=bridges,
            gap_report=gap_report,
            transitions=transitions,
            hook_segment_id=hook_segment_id,
        )
        scored.append(
            {
                "source": str(cand.get("source") or "unknown"),
                "ordered_segment_ids": ordered,
                "score": round(score, 2),
                "story_health_verdict": health.get("verdict"),
                "bridge_count": len(bridges.get("pairs") or []),
            }
        )

    if not scored:
        return {
            "version": 1,
            "candidates": [],
            "winner": None,
            "ordered_segment_ids": [],
        }

    scored.sort(key=lambda r: float(r.get("score") or -999), reverse=True)
    winner = scored[0]
    return {
        "version": 1,
        "candidates": scored[:4],
        "winner": winner.get("source"),
        "ordered_segment_ids": list(winner.get("ordered_segment_ids") or []),
        "winner_score": winner.get("score"),
    }


def chapter_order_from_plan(narrative_plan: dict[str, Any] | None) -> list[str]:
    """Flatten narrative_plan chapter segment_ids into an air order candidate."""
    if not isinstance(narrative_plan, dict):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for ch in narrative_plan.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        for sid in ch.get("segment_ids") or []:
            s = str(sid)
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    return out
