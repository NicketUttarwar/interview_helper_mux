"""Deterministic ensemble lint after final gap VO + transitions."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def lint_gap_and_transitions(ctx: RunContext) -> dict[str, Any]:
    """Flag duplicate host bridges that echo gap VO lines (cheap string overlap)."""
    issues: list[dict[str, str]] = []
    gap_texts: list[str] = []
    if ctx.artifact_exists("understanding/gap_report.json"):
        report = ctx.read_json("understanding/gap_report.json")
        if isinstance(report, dict):
            for line in report.get("interviewer_lines") or []:
                if isinstance(line, dict):
                    t = " ".join(str(line.get("text") or line.get("script") or "").lower().split())
                    if t:
                        gap_texts.append(t)

    if ctx.artifact_exists("master/transitions.json"):
        tr = ctx.read_json("master/transitions.json")
        bridges = []
        if isinstance(tr, dict):
            bridges = tr.get("bridges") or tr.get("transitions") or []
        for bridge in bridges if isinstance(bridges, list) else []:
            if not isinstance(bridge, dict):
                continue
            bt = " ".join(str(bridge.get("text") or bridge.get("script") or "").lower().split())
            if not bt or len(bt) < 24:
                continue
            for gt in gap_texts:
                if len(gt) < 24:
                    continue
                # Substantial substring overlap → redundant host voice
                if bt in gt or gt in bt or _token_jaccard(bt, gt) >= 0.72:
                    issues.append(
                        {
                            "code": "redundant_bridge_vs_gap_vo",
                            "bridge_id": str(bridge.get("id") or bridge.get("transition_id") or ""),
                            "detail": "Transition text overlaps a gap VO line",
                        }
                    )
                    break

    payload = {
        "ok": not issues,
        "issues": issues,
        "producer": "refinement_ensemble",
    }
    ctx.write_json("understanding/refinement_ensemble_lint.json", payload)
    if issues:
        ctx.log(
            f"Ensemble lint: {len(issues)} redundant bridge(s) vs gap VO",
            level="warning",
            stage="transitions_refine",
        )
    return payload


def _token_jaccard(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa | sb), 1)
