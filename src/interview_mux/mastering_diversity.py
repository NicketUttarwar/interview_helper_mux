"""Measure how different L2 shape candidates actually are.

Spec: docs/cross-cutting/mastering-quality-hardening.md (Workstream 3)
Schema: mastering_diversity_report.schema.json
Artifact: mastering/shape/diversity_report.json
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.mastering_hardening_config import gate_cfg, gate_mode
from interview_mux.run_context import RunContext

DIVERSITY_ARTIFACT = "mastering/shape/diversity_report.json"

AXIS_WEIGHTS: dict[str, float] = {
    "segment_order": 0.30,
    "cold_open_kind": 0.15,
    "duration_band": 0.10,
    "thesis_framing": 0.15,
    "vo_sfx_density": 0.10,
    "ending_kind": 0.10,
    "speaker_balance": 0.10,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _segments(candidate: dict[str, Any]) -> list[str]:
    return [str(s) for s in (candidate.get("ordered_segment_ids") or [])]


def _cold_open_kind(candidate: dict[str, Any]) -> str:
    cold = candidate.get("cold_open")
    if isinstance(cold, dict):
        return str(cold.get("kind") or "none")
    return "none"


def _duration_band(candidate: dict[str, Any]) -> str:
    ms = candidate.get("target_duration_ms") or candidate.get("estimated_duration_ms")
    if not ms:
        return "unknown"
    minutes = float(ms) / 60000.0
    if minutes < 20:
        return "short"
    if minutes < 45:
        return "medium"
    if minutes < 75:
        return "long"
    return "very_long"


def _vo_sfx_density_class(candidate: dict[str, Any]) -> str:
    vo = len(candidate.get("vo_line_ids") or candidate.get("vo_lines") or [])
    sfx = len(candidate.get("sfx_cue_refs") or candidate.get("sfx_cues") or [])
    total = vo + sfx
    if total == 0:
        return "bare"
    if total <= 3:
        return "sparse"
    if total <= 8:
        return "moderate"
    return "rich"


def _order_distance(a: list[str], b: list[str]) -> float:
    """Blend of set difference and sequence disagreement.

    Two candidates using the same segments in a different order are meaningfully
    different, so ordering counts even when the inclusion sets match exactly.
    """
    set_a, set_b = set(a), set(b)
    if not set_a and not set_b:
        return 0.0
    union = set_a | set_b
    jaccard_distance = 1.0 - (len(set_a & set_b) / len(union)) if union else 0.0

    shared = [s for s in a if s in set_b]
    shared_b = [s for s in b if s in set_a]
    if len(shared) > 1:
        rank_b = {s: i for i, s in enumerate(shared_b)}
        inversions = sum(
            1
            for i in range(len(shared))
            for j in range(i + 1, len(shared))
            if rank_b.get(shared[i], 0) > rank_b.get(shared[j], 0)
        )
        pairs = len(shared) * (len(shared) - 1) / 2
        order_distance = inversions / pairs if pairs else 0.0
    else:
        order_distance = 0.0

    return min(1.0, 0.6 * jaccard_distance + 0.4 * order_distance)


def _categorical(a: Any, b: Any) -> float:
    return 0.0 if str(a) == str(b) else 1.0


def _numeric(a: Any, b: Any) -> float:
    try:
        return min(1.0, abs(float(a) - float(b)))
    except (TypeError, ValueError):
        return 0.0 if a == b else 1.0


def candidate_distance(a: dict[str, Any], b: dict[str, Any]) -> dict[str, float]:
    """Per-axis distance in 0..1 between two candidates."""
    return {
        "segment_order": _order_distance(_segments(a), _segments(b)),
        "cold_open_kind": _categorical(_cold_open_kind(a), _cold_open_kind(b)),
        "duration_band": _categorical(_duration_band(a), _duration_band(b)),
        "thesis_framing": _categorical(
            a.get("thesis_framing") or a.get("thesis"), b.get("thesis_framing") or b.get("thesis")
        ),
        "vo_sfx_density": _categorical(_vo_sfx_density_class(a), _vo_sfx_density_class(b)),
        "ending_kind": _categorical(a.get("ending_kind"), b.get("ending_kind")),
        "speaker_balance": _numeric(a.get("speaker_balance"), b.get("speaker_balance")),
    }


def build_diversity_report(
    candidates: list[dict[str, Any]],
    *,
    threshold: float | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conf = gate_cfg("diversity", cfg)
    floor = float(threshold if threshold is not None else conf["min_pairwise_distance"])
    ids = [str(c.get("candidate_id") or f"cand_{i}") for i, c in enumerate(candidates)]

    pairs: list[dict[str, Any]] = []
    remint: list[str] = []
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            per_axis = candidate_distance(candidates[i], candidates[j])
            distance = sum(per_axis[axis] * w for axis, w in AXIS_WEIGHTS.items())
            too_similar = distance < floor
            pairs.append(
                {
                    "a": ids[i],
                    "b": ids[j],
                    "distance": round(distance, 4),
                    "per_axis": {k: round(v, 4) for k, v in per_axis.items()},
                    "too_similar": too_similar,
                }
            )
            if too_similar and ids[j] not in remint:
                remint.append(ids[j])

    min_distance = min((p["distance"] for p in pairs), default=1.0)
    return {
        "version": 1,
        "mode": gate_mode("diversity", cfg),
        "threshold": floor,
        "candidate_ids": ids,
        "axes": [{"axis": a, "weight": w} for a, w in AXIS_WEIGHTS.items()],
        "pairs": pairs,
        "verdict": "remint_required" if remint else "pass",
        "remint_candidate_ids": remint,
        "remint_directives": _remint_directives(pairs, remint),
        "min_distance": round(min_distance, 4),
        "generated_at": _now(),
    }


def _remint_directives(pairs: list[dict[str, Any]], remint: list[str]) -> list[str]:
    """Name the axes that collapsed so the remint has somewhere to go."""
    directives: list[str] = []
    for cand in remint:
        axes: set[str] = set()
        for pair in pairs:
            if not pair["too_similar"] or cand not in (pair["a"], pair["b"]):
                continue
            axes.update(axis for axis, d in pair["per_axis"].items() if d < 0.2)
        if axes:
            directives.append(
                f"{cand}: differentiate on {', '.join(sorted(axes))} — currently a near-clone"
            )
        else:
            directives.append(f"{cand}: too close to a sibling candidate; propose a distinct shape")
    return directives


def needs_remint(report: dict[str, Any]) -> bool:
    return report.get("verdict") == "remint_required"


def write_diversity_report(ctx: RunContext, report: dict[str, Any]) -> None:
    ctx.write_json(DIVERSITY_ARTIFACT, report)
