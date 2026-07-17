"""Human-readable copy for Stage Decision Wizard."""

from __future__ import annotations

from typing import Any


def stage_title(stage_id: str) -> str:
    try:
        from interview_mux.web.stages import STAGE_BY_ID

        info = STAGE_BY_ID.get(stage_id)
        if info:
            return info.title
    except Exception:
        pass
    return stage_id.replace("_", " ").title()


def propagation_headline(plan: dict[str, Any]) -> str:
    stale = plan.get("stale_stages") or []
    if not stale:
        return "Downstream stages may be outdated"
    titles = [stage_title(sid) for sid in stale[:3]]
    if len(stale) == 1:
        return f"{titles[0]} used the previous version of this stage's output"
    if len(stale) == 2:
        return f"{titles[0]} and {titles[1]} used outdated outputs from this fix"
    extra = len(stale) - 2
    return f"{titles[0]}, {titles[1]}, and {extra} more stage(s) used outdated outputs"


def propagation_detail(plan: dict[str, Any]) -> str:
    stale = plan.get("stale_stages") or []
    if not stale:
        errors = plan.get("cross_errors") or []
        if errors:
            return str(errors[0])
        return "Re-running affected stages keeps later analysis consistent with your changes."
    names = ", ".join(stage_title(sid) for sid in stale[:4])
    return f"Affected: {names}. Re-running refreshes them from your updated artifacts."


def issue_headline(item: dict[str, Any]) -> str:
    msg = str(item.get("message") or "Artifact issue needs your choice")
    seg = item.get("segment_id")
    if seg and seg not in msg:
        return f"{msg} ({seg})"
    return msg


def issue_detail(item: dict[str, Any], stage_key: str) -> str:
    upstream = item.get("suggested_upstream_stage")
    if upstream:
        return (
            f"This issue in {stage_title(stage_key)} may be fixed by re-running "
            f"{stage_title(str(upstream))}."
        )
    strategy = str(item.get("repair_strategy") or "")
    if strategy == "infer_segment_types":
        return "Pick the segment type that best matches the transcript."
    if strategy == "merge_overlap":
        return "Choose how to resolve overlapping segment times."
    return "Select the option that best matches your intent for this artifact."


def upstream_rerun_headline(upstream_stage: str) -> str:
    return f"Re-run {stage_title(upstream_stage)}?"


def upstream_rerun_detail(stage_key: str, upstream_stage: str) -> str:
    return (
        f"An issue in {stage_title(stage_key)} often comes from outdated "
        f"{stage_title(upstream_stage)} output."
    )


def warning_headline(count: int, *, auto_fixed: int = 0) -> str:
    if auto_fixed <= 0:
        return "Review autopilot output"
    if count == 1:
        return "Autopilot applied 1 automatic fix"
    return f"Autopilot applied {count} automatic fixes"


def warning_detail(warnings: list[str]) -> str:
    if warnings:
        return warnings[0]
    return "Review staged outputs before saving — some issues were resolved automatically."
