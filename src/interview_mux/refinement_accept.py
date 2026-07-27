"""Accept/reject a gap_framing_recompose candidate against the champion."""

from __future__ import annotations

from typing import Any

from interview_mux.refinement_cascade import write_cascade
from interview_mux.refinement_champion import load_champion, promote_candidate
from interview_mux.refinement_flow_integrity import DRAFT_REL, FINAL_REL
from interview_mux.refinement_kernels import (
    gap_report_delta,
    listener_rubric_compare,
    vo_second_budget,
)
from interview_mux.run_context import RunContext


def _orphan_count(report: dict[str, Any], ordered: list[str]) -> int:
    """Interviewer lines that target/support nothing in the kept order."""
    ordered_set = set(ordered)
    orphans = 0
    for line in report.get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        target = str(line.get("targets_segment_id") or "")
        supports = line.get("supports_segment_ids") or []
        ok = (target and target in ordered_set) or any(str(s) in ordered_set for s in supports)
        category = str(line.get("line_category") or "")
        if category in ("episode_preface", "cold_open") or line.get("cold_open"):
            ok = True
        if not ok:
            orphans += 1
    return orphans


def score_gap_report(report: dict[str, Any], ordered: list[str]) -> dict[str, float]:
    """Deterministic rubric: clarity (no orphans), succinctness (VO budget), hook (has preface)."""
    lines = [line for line in (report.get("interviewer_lines") or []) if isinstance(line, dict)]
    orphans = _orphan_count(report, ordered) if ordered else 0
    n = max(len(lines), 1)
    succinctness = max(0.0, 1.0 - (vo_second_budget(lines) / 180.0))
    clarity = max(0.0, 1.0 - orphans / n)
    hook = 0.7 if any(str(line.get("line_category") or "") == "episode_preface" for line in lines) else 0.5
    return {
        "clarity": round(clarity, 3),
        "succinctness": round(min(succinctness, 1.0), 3),
        "hook": hook,
    }


def accept_gap_recompose(
    ctx: RunContext,
    candidate_report: dict[str, Any],
    candidate_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministic accept/reject for a gap_framing_recompose candidate.

    Runs (in order): meaningful-delta check (noop guard), feasibility
    (targets must be inside the kept order), and a deterministic listener
    rubric comparison against the current champion. On accept: writes
    gap_report.json + plan, promotes the champion, and writes the
    downstream cascade. On reject/noop: the draft remains authoritative.
    """
    draft = ctx.read_json(DRAFT_REL) if ctx.artifact_exists(DRAFT_REL) else {"interviewer_lines": []}
    if not isinstance(draft, dict):
        draft = {"interviewer_lines": []}

    ordered: list[str] = []
    if ctx.artifact_exists("master/selection.json"):
        selection = ctx.read_json("master/selection.json")
        if isinstance(selection, dict):
            ordered = [str(x) for x in (selection.get("ordered_segment_ids") or [])]

    delta = gap_report_delta(draft, candidate_report)
    if not delta["meaningful"]:
        ctx.write_json(FINAL_REL, draft)
        return {"accepted": False, "reason_code": "noop", "delta": delta}

    # Sticky operator pins survive recompose as long as their target is still kept.
    pinned = [
        line
        for line in draft.get("interviewer_lines") or []
        if isinstance(line, dict)
        and str(line.get("origin") or "") == "operator"
        and (not ordered or not str(line.get("targets_segment_id") or "") or str(line.get("targets_segment_id")) in ordered)
    ]
    if pinned:
        candidate_lines = list(candidate_report.get("interviewer_lines") or [])
        have = {str(line.get("line_id")) for line in candidate_lines if isinstance(line, dict)}
        for pin in pinned:
            if str(pin.get("line_id")) not in have:
                candidate_lines.append(pin)
        candidate_report = {**candidate_report, "interviewer_lines": candidate_lines}

    orphans = _orphan_count(candidate_report, ordered) if ordered else 0
    if ordered and orphans > 0:
        return {"accepted": False, "reason_code": "feasibility_orphans", "orphans": orphans, "delta": delta}

    champion = load_champion(ctx, "gap_vo")
    champion_scores = (champion or {}).get("score_vector") or score_gap_report(draft, ordered)
    candidate_scores = score_gap_report(candidate_report, ordered)
    verdict = listener_rubric_compare(champion_scores, candidate_scores)
    if verdict == "worse":
        ctx.write_json(FINAL_REL, draft)
        return {
            "accepted": False,
            "reason_code": "rejected_rubric",
            "delta": delta,
            "champion_scores": champion_scores,
            "candidate_scores": candidate_scores,
        }

    ctx.write_json(FINAL_REL, candidate_report)
    if isinstance(candidate_plan, dict):
        ctx.write_json("understanding/gap_framing_plan.json", candidate_plan)
    promote_candidate(
        ctx,
        "gap_vo",
        [FINAL_REL, "understanding/gap_framing_plan.json"],
        candidate_scores,
        source="gap_framing_recompose",
    )
    write_cascade(
        ctx,
        changed_line_ids=list(delta["rewritten"]) + list(delta["added"]),
        dropped_line_ids=list(delta["dropped"]),
    )
    return {
        "accepted": True,
        "reason_code": "accepted",
        "delta": delta,
        "candidate_scores": candidate_scores,
    }
