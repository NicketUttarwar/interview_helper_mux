from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from interview_mux.value_analysis.config import require_value_analysis_flag

OUTCOME_PREFIXES = ("LEX-", "COM-", "CRE-")
MECHANISM_PREFIX = "MEC-"
MOONSHOT_PREFIX = "MOO-"

PROFILE_WEIGHTS: dict[str, dict[str, float]] = {
    "listener-first": {"out": 0.60, "mec": 0.25, "moo": 0.10, "sec": 0.05},
    "idea-first": {"out": 0.70, "mec": 0.20, "moo": 0.05, "sec": 0.05},
    "moonshot-upside": {"out": 0.50, "mec": 0.20, "moo": 0.25, "sec": 0.05},
    "creator-first": {"out": 0.45, "mec": 0.20, "moo": 0.10, "sec": 0.25},
    "equal": {"out": 0.25, "mec": 0.25, "moo": 0.25, "sec": 0.25},
}


def load_scorecard(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def _mean_scores(scores: dict[str, Any], prefix: str | tuple[str, ...]) -> float | None:
    prefixes = (prefix,) if isinstance(prefix, str) else prefix
    vals: list[float] = []
    for key, val in scores.items():
        if any(str(key).startswith(p) for p in prefixes):
            try:
                vals.append(float(val))
            except (TypeError, ValueError):
                continue
    if not vals:
        return None
    return sum(vals) / len(vals)


def _candidate_components(candidate: dict[str, Any], section_fit: float) -> dict[str, float]:
    scores = candidate.get("scores") if isinstance(candidate.get("scores"), dict) else {}
    outcome = _mean_scores(scores, OUTCOME_PREFIXES)
    mechanism = _mean_scores(scores, MECHANISM_PREFIX)
    moonshot = _mean_scores(scores, MOONSHOT_PREFIX)
    return {
        "outcome": outcome if outcome is not None else 0.0,
        "mechanism": mechanism if mechanism is not None else 0.0,
        "moonshot": moonshot if moonshot is not None else 0.0,
        "section_fit": float(candidate.get("section_fit", section_fit) or section_fit),
    }


def global_score(components: dict[str, float], profile: str) -> float:
    weights = PROFILE_WEIGHTS.get(profile, PROFILE_WEIGHTS["listener-first"])
    return (
        weights["out"] * components["outcome"]
        + weights["mec"] * components["mechanism"]
        + weights["moo"] * components["moonshot"]
        + weights["sec"] * components["section_fit"]
    )


def aggregate(
    scorecard: dict[str, Any],
    profiles: list[str] | None = None,
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    require_value_analysis_flag(cfg, "spike_scoring")
    chosen = profiles or ["listener-first", "idea-first"]
    section = str(scorecard.get("section", "unknown"))
    section_fit = float(scorecard.get("section_fit", 3) or 3)
    candidates = scorecard.get("candidates") or []
    if not isinstance(candidates, list):
        raise ValueError("scorecard.candidates must be a list")

    ranked_by_profile: dict[str, list[dict[str, Any]]] = {}
    for profile in chosen:
        if profile not in PROFILE_WEIGHTS:
            raise ValueError(f"Unknown profile: {profile}")
        scored: list[dict[str, Any]] = []
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            comp = _candidate_components(cand, section_fit)
            scored.append(
                {
                    "id": cand.get("id"),
                    "label": cand.get("label", cand.get("id")),
                    "global_score": round(global_score(comp, profile), 3),
                    "components": {k: round(v, 3) for k, v in comp.items()},
                }
            )
        scored.sort(key=lambda x: x["global_score"], reverse=True)
        for rank, row in enumerate(scored, start=1):
            row["rank"] = rank
        ranked_by_profile[profile] = scored

    primary = ranked_by_profile.get(chosen[0], [])
    markdown = _markdown_table(section, primary, chosen[0])
    return {
        "section": section,
        "profiles": chosen,
        "ranked": ranked_by_profile,
        "winner": primary[0] if primary else None,
        "markdown": markdown,
    }


def _markdown_table(section: str, ranked: list[dict[str, Any]], profile: str) -> str:
    lines = [
        f"## Spike results — {section} ({profile})",
        "",
        "| Rank | Candidate | Score | Outcome | Mechanism | Moonshot | Section fit |",
        "|------|-----------|-------|---------|-------------|----------|-------------|",
    ]
    for row in ranked:
        comp = row.get("components") or {}
        lines.append(
            f"| {row.get('rank')} | {row.get('label')} | {row.get('global_score')} "
            f"| {comp.get('outcome')} | {comp.get('mechanism')} | {comp.get('moonshot')} | {comp.get('section_fit')} |"
        )
    return "\n".join(lines)
