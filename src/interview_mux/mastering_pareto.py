"""Keep shape candidates on a Pareto frontier instead of collapsing to one score.

Spec: docs/cross-cutting/mastering-quality-hardening.md (Workstream 10)
Schema: mastering_pareto_frontier.schema.json
Artifact: mastering/shape/pareto.json

A single aggregate score hides fatal weaknesses: a candidate that is mediocre
everywhere can outrank one that is exceptional where this tape needs it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.mastering_hardening_config import gate_cfg, gate_mode
from interview_mux.run_context import RunContext

PARETO_ARTIFACT = "mastering/shape/pareto.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dominates(a: dict[str, float], b: dict[str, float], dimensions: list[str]) -> bool:
    """True when `a` is at least as good everywhere and strictly better somewhere."""
    at_least_as_good = all(a.get(d, 0.0) >= b.get(d, 0.0) for d in dimensions)
    strictly_better = any(a.get(d, 0.0) > b.get(d, 0.0) for d in dimensions)
    return at_least_as_good and strictly_better


def build_frontier(
    survivors: list[dict[str, Any]],
    *,
    dimensions: list[str] | None = None,
    hard_failed: list[dict[str, Any]] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Partition survivors into a non-dominated frontier and the candidates it dominates.

    `survivors` are `{candidate_id, dimension_scores}` rows from the L4 arbiter.
    """
    conf = gate_cfg("pareto", cfg)
    min_frontier = max(1, int(conf.get("min_frontier_size") or 1))

    scored = [
        (str(s.get("candidate_id")), _scores(s))
        for s in survivors
        if s.get("candidate_id") is not None
    ]
    dims = dimensions or sorted({d for _, sc in scored for d in sc})

    frontier: list[dict[str, Any]] = []
    dominated: list[dict[str, Any]] = []
    for cid, scores in scored:
        dominators = [
            other_id
            for other_id, other_scores in scored
            if other_id != cid and dominates(other_scores, scores, dims)
        ]
        if dominators:
            dominated.append({"candidate_id": cid, "dominated_by": dominators, "scores": scores})
        else:
            frontier.append(
                {
                    "candidate_id": cid,
                    "scores": scores,
                    "best_dimensions": _best_dimensions(scores, scored, dims),
                    "tradeoff_note": None,
                }
            )

    # Never starve synthesize: promote the strongest dominated candidates back if needed.
    while len(frontier) < min_frontier and dominated:
        promoted = max(dominated, key=lambda d: sum(d["scores"].values()))
        dominated.remove(promoted)
        frontier.append(
            {
                "candidate_id": promoted["candidate_id"],
                "scores": promoted["scores"],
                "best_dimensions": [],
                "tradeoff_note": "promoted to satisfy min_frontier_size",
            }
        )

    for member in frontier:
        if member["tradeoff_note"] is None:
            member["tradeoff_note"] = _tradeoff_note(member, dims)

    return {
        "version": 1,
        "mode": gate_mode("pareto", cfg),
        "dimensions": dims,
        "frontier": sorted(frontier, key=lambda m: -sum(m["scores"].values())),
        "dominated": dominated,
        "hard_failed": list(hard_failed or []),
        "generated_at": _now(),
    }


def _scores(survivor: dict[str, Any]) -> dict[str, float]:
    raw = survivor.get("dimension_scores") or survivor.get("scores") or {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def _best_dimensions(
    scores: dict[str, float], scored: list[tuple[str, dict[str, float]]], dims: list[str]
) -> list[str]:
    best: list[str] = []
    for dim in dims:
        peak = max((sc.get(dim, 0.0) for _, sc in scored), default=0.0)
        if scores.get(dim, 0.0) >= peak:
            best.append(dim)
    return best


def _tradeoff_note(member: dict[str, Any], dims: list[str]) -> str | None:
    scores = member["scores"]
    if not scores:
        return None
    strongest = max(dims, key=lambda d: scores.get(d, 0.0), default=None)
    weakest = min(dims, key=lambda d: scores.get(d, 0.0), default=None)
    if not strongest or not weakest or strongest == weakest:
        return None
    return f"leads on {strongest}, pays for it on {weakest}"


def frontier_candidate_ids(frontier: dict[str, Any]) -> list[str]:
    return [str(m.get("candidate_id")) for m in (frontier.get("frontier") or [])]


def select_synthesize_inputs(
    frontier: dict[str, Any], candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Restrict synthesize inputs to frontier survivors (advisory mode passes all through)."""
    if frontier.get("mode") != "authoritative":
        return list(candidates)
    allowed = set(frontier_candidate_ids(frontier))
    selected = [c for c in candidates if str(c.get("candidate_id")) in allowed]
    return selected or list(candidates)


def write_frontier(ctx: RunContext, frontier: dict[str, Any]) -> None:
    ctx.write_json(PARETO_ARTIFACT, frontier)
