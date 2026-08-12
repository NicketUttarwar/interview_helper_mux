"""Typed remutate actions for edl_narrative_audit fail (no verdict soft-pass)."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

REMUTATE_REL = "mastering/edl_narrative_remutate.json"
MAX_ATTEMPTS = 2

# Allowlisted issue → action classifiers (substring match on lowered text).
_CLASSIFIERS: list[tuple[str, tuple[str, ...]]] = [
    (
        "rerank",
        (
            "rerank",
            "full_master_ranking",
            "reorder",
            "selection order",
            "ordered_segment",
            "finale",
            "leftover",
            "appear after",
            "early-chapter",
            "early-story",
        ),
    ),
    (
        "transitions",
        (
            "transition",
            "bridge",
            "seam",
            "hinge",
            "chapter join",
        ),
    ),
    (
        "rebase_gap_vo",
        (
            "gap vo",
            "gap_report",
            "vo pickup",
            "missing_question",
            "interviewer line",
            "layup",
            "framing line",
        ),
    ),
    (
        "drop_blank",
        (
            "blank segment",
            "unusable segment",
            "empty segment",
            "near-silence",
        ),
    ),
]

_ACTION_STAGES: dict[str, list[str]] = {
    "rerank": ["full_master_ranking", "edl_narrative_audit"],
    "transitions": ["transitions", "edl_narrative_audit"],
    "rebase_gap_vo": ["selection_framing_apply", "nugget_layup_compose", "edl_narrative_audit"],
    "drop_blank": ["full_master_ranking", "edl_narrative_audit"],
    "operator": [],
}


def classify_edl_narrative_issue(text: str) -> str:
    blob = str(text or "").strip().lower()
    if not blob:
        return "operator"
    for action, needles in _CLASSIFIERS:
        if any(n in blob for n in needles):
            return action
    return "operator"


def classify_edl_narrative_audit(audit: dict[str, Any] | None) -> list[str]:
    if not isinstance(audit, dict):
        return ["operator"]
    actions: list[str] = []
    for issue in audit.get("blocking_issues") or []:
        if isinstance(issue, dict):
            blob = " ".join(
                str(issue.get(k) or "")
                for k in ("issue", "summary", "reason", "recommended_action")
            )
        else:
            blob = str(issue or "")
        actions.append(classify_edl_narrative_issue(blob))
    for raw in audit.get("recommended_actions") or []:
        actions.append(classify_edl_narrative_issue(str(raw or "")))
    # Stable unique order
    out: list[str] = []
    for a in actions:
        if a not in out:
            out.append(a)
    return out or ["operator"]


def plan_edl_narrative_remutate(
    ctx: RunContext, audit: dict[str, Any]
) -> dict[str, Any]:
    prior = (
        ctx.read_json(REMUTATE_REL)
        if ctx.artifact_exists(REMUTATE_REL)
        else {}
    )
    attempt = int((prior or {}).get("attempt") or 0) + 1
    actions = classify_edl_narrative_audit(audit)
    stages: list[str] = []
    for action in actions:
        for sid in _ACTION_STAGES.get(action) or []:
            if sid not in stages:
                stages.append(sid)
    plan = {
        "version": 1,
        "attempt": attempt,
        "max_attempts": MAX_ATTEMPTS,
        "actions": actions,
        "from_stages": stages,
        "from_stage": stages[0] if stages else None,
        "exhausted": attempt > MAX_ATTEMPTS or not stages,
    }
    ctx.write_json(REMUTATE_REL, plan)
    return plan


def apply_edl_narrative_remutate(ctx: RunContext, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Clear mapped stage markers so delivery can re-enter. Does not soft-pass audit."""
    doc = plan or (
        ctx.read_json(REMUTATE_REL) if ctx.artifact_exists(REMUTATE_REL) else None
    )
    if not isinstance(doc, dict) or doc.get("exhausted"):
        return {"ok": False, "reason": "exhausted_or_missing"}
    cleared: list[str] = []
    for sid in doc.get("from_stages") or []:
        marker = ctx.run_dir / ".stage_done" / str(sid)
        if marker.is_file():
            marker.unlink(missing_ok=True)
            cleared.append(str(sid))
    # Force a fresh audit after remutate.
    for sid in ("edl", "edl_narrative_audit"):
        marker = ctx.run_dir / ".stage_done" / sid
        if marker.is_file():
            marker.unlink(missing_ok=True)
            cleared.append(sid)
    ctx.log(
        f"edl_narrative remutate attempt {doc.get('attempt')}: "
        f"actions={doc.get('actions')} cleared={cleared[:8]}",
        level="warning",
        stage="edl_narrative_audit",
    )
    return {"ok": True, "cleared": cleared, "from_stage": doc.get("from_stage")}
