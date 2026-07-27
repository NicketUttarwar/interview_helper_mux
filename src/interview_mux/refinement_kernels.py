"""Deterministic scoring kernels shared by refinement accept/gate logic."""

from __future__ import annotations

from typing import Any, Literal

from interview_mux.run_context import RunContext

RubricVerdict = Literal["better", "worse", "tie"]


def vo_second_budget(lines: list[dict[str, Any]], wps: float = 2.5) -> float:
    """Estimated seconds of VO audio for a set of interviewer lines."""
    words = 0
    for line in lines:
        if not isinstance(line, dict):
            continue
        text = str(line.get("text") or line.get("script") or "")
        words += len(text.split())
    return words / max(wps, 0.1)


def topic_survival_ok(ctx: RunContext, excludes: list[str] | set[str]) -> bool:
    """True when no topic in coverage_audit would lose every surviving segment.

    Thin wrapper around the same coverage idea used by
    ``framing_coverage_guard`` — reusable for hypothetical candidate excludes
    proposed by a refinement pass before they are committed.
    """
    if not ctx.artifact_exists("master/coverage_audit.json"):
        return True
    audit = ctx.read_json("master/coverage_audit.json")
    if not isinstance(audit, dict):
        return True
    topic_maps = audit.get("topic_segment_map") or audit.get("topics") or []
    excl = {str(x) for x in excludes if str(x)}
    if not excl:
        return True
    for row in topic_maps if isinstance(topic_maps, list) else []:
        if not isinstance(row, dict):
            continue
        segs = [str(s) for s in (row.get("segment_ids") or row.get("segments") or []) if s]
        if segs and all(s in excl for s in segs):
            return False
    return True


def listener_rubric_compare(
    champion_scores: dict[str, float],
    candidate_scores: dict[str, float],
) -> RubricVerdict:
    """Deterministic rubric comparison — mean of score_vector, small tie band."""

    def avg(scores: dict[str, float]) -> float:
        if not scores:
            return 0.0
        return sum(float(v) for v in scores.values()) / max(len(scores), 1)

    champion_avg = avg(champion_scores)
    candidate_avg = avg(candidate_scores)
    if candidate_avg > champion_avg + 0.02:
        return "better"
    if candidate_avg < champion_avg - 0.02:
        return "worse"
    return "tie"


def gap_report_delta(draft: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Line-level diff between a draft and candidate gap_report."""
    draft_lines = {
        str(line.get("line_id") or ""): line
        for line in (draft.get("interviewer_lines") or [])
        if isinstance(line, dict) and line.get("line_id")
    }
    candidate_lines = {
        str(line.get("line_id") or ""): line
        for line in (candidate.get("interviewer_lines") or [])
        if isinstance(line, dict) and line.get("line_id")
    }
    draft_ids, candidate_ids = set(draft_lines), set(candidate_lines)
    kept = sorted(draft_ids & candidate_ids)
    added = sorted(candidate_ids - draft_ids)
    dropped = sorted(draft_ids - candidate_ids)
    rewritten = [
        line_id
        for line_id in kept
        if str(draft_lines[line_id].get("text") or "") != str(candidate_lines[line_id].get("text") or "")
    ]
    meaningful = bool(added or dropped or rewritten) or len(candidate_ids) != len(draft_ids)
    return {
        "kept": kept,
        "rewritten": rewritten,
        "added": added,
        "dropped": dropped,
        "meaningful": meaningful,
    }
