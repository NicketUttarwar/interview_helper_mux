"""Operator-visible logs for boundary_detection enrichment (Wave B H-SEG-02 / H-ORC-01)."""

from __future__ import annotations

from typing import Any

from interview_mux.interview_spine.constants import (
    BOUNDARY_VOLLEY_MAX_SPINE_EVENTS,
    PAUSE_LADDER_MS,
    PAUSE_LADDER_OVERSPLIT_400MS_COUNT,
)
from interview_mux.interview_spine.paths import SPINE_PATH
from interview_mux.run_context import RunContext


def pace_class_from_sap(ctx: RunContext) -> str:
    if not ctx.artifact_exists("understanding/source_acoustic_profile.json"):
        return "conversational"
    sap = ctx.read_json("understanding/source_acoustic_profile.json")
    if not isinstance(sap, dict):
        return "conversational"
    return str((sap.get("pacing") or {}).get("pace_class") or "conversational")


def ladder_guidance_for_pace(pace_class: str) -> str:
    if pace_class == "calm":
        return (
            "pace_class calm: prefer 700/1200 ms ladder tiers; "
            "400 ms tier is advisory only for reflective pauses."
        )
    if pace_class == "dense":
        return "pace_class dense: prefer 700/1200 ms before 400 ms for technical speech."
    return "pace_class conversational: standard 400/700/1200 ms ladder preference."


def oversplit_risk_from_hints(hints: dict[str, Any] | None) -> bool:
    if not isinstance(hints, dict):
        return False
    candidates = hints.get("candidates") or hints.get("pre_thin_candidates") or []
    tier400 = next(
        (c for c in candidates if c.get("threshold_ms") == PAUSE_LADDER_MS[0]),
        None,
    )
    if isinstance(tier400, dict):
        count = int(tier400.get("count") or 0)
        return count > PAUSE_LADDER_OVERSPLIT_400MS_COUNT
    return False


def spine_truncation_risk(ctx: RunContext, full_count: int | None = None) -> bool:
    if full_count is None:
        if not ctx.artifact_exists(SPINE_PATH):
            return False
        full = ctx.read_json(SPINE_PATH)
        full_count = len(full.get("boundary_events") or []) if isinstance(full, dict) else 0
    return int(full_count) > BOUNDARY_VOLLEY_MAX_SPINE_EVENTS


def observe_boundary_detection_input(
    ctx: RunContext,
    payload: dict[str, Any],
    *,
    pre_thin_counts: dict[str, Any] | None = None,
) -> None:
    """Emit gui_log warnings for oversplit risk and spine volley truncation."""
    hints = payload.get("pause_ladder_hints")
    if isinstance(hints, dict):
        candidates = (pre_thin_counts or {}).get("candidates") or hints.get("candidates") or []
        if not candidates:
            ctx.log(
                "pause_ladder_hints empty — boundary stage falls back to pause_split_ms.",
                level="info",
                stage="boundary_detection",
            )
        tier400 = next(
            (c for c in candidates if c.get("threshold_ms") == PAUSE_LADDER_MS[0]),
            None,
        )
        if isinstance(tier400, dict) and int(tier400.get("count") or 0) > PAUSE_LADDER_OVERSPLIT_400MS_COUNT:
            ctx.log(
                f"pause_ladder_oversplit_risk: 400 ms tier has {tier400['count']} hits "
                f"(>{PAUSE_LADDER_OVERSPLIT_400MS_COUNT}); prefer longer tiers on fireside/calm speech.",
                level="warning",
                stage="boundary_detection",
                detail="pause_ladder_oversplit_risk",
            )

    spine_compact = payload.get("interview_spine")
    if not isinstance(spine_compact, dict) or not ctx.artifact_exists(SPINE_PATH):
        return
    full = ctx.read_json(SPINE_PATH)
    total = len(full.get("boundary_events") or []) if isinstance(full, dict) else 0
    compact_n = len(spine_compact.get("boundary_events") or [])
    if total > BOUNDARY_VOLLEY_MAX_SPINE_EVENTS:
        omitted = total - min(compact_n, BOUNDARY_VOLLEY_MAX_SPINE_EVENTS)
        ctx.log(
            f"boundary_detection volley truncated ({omitted} spine events omitted).",
            level="warning",
            stage="boundary_detection",
            detail={"total_spine_events": total, "volley_cap": BOUNDARY_VOLLEY_MAX_SPINE_EVENTS},
        )
