"""Gate categories. Homunculus is controller on 0.1.0; G0 still blocks."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

CATEGORIES = (
    "transcript_integrity",
    "framing_consent",
    "vo_pickup",
    "preclean",
    "nle",
    "listen",
    "optimizer",
    "quality_ship",
    "publish",
    "prompt_promotion",
)


def category_status(ctx: RunContext) -> dict[str, Any]:
    from interview_mux.gates import (
        check_g1_vo,
        check_transcript_review_pending,
    )

    g0_open = False
    try:
        g0_open = bool(check_transcript_review_pending(ctx))
    except Exception:
        g0_open = False
    g1 = {}
    try:
        g1 = check_g1_vo(ctx) or {}
    except Exception:
        g1 = {}
    return {
        "transcript_integrity": {"open": g0_open, "blocks_analysis": g0_open},
        "vo_pickup": {"open": bool(g1.get("pending"))},
        "categories": list(CATEGORIES),
    }
