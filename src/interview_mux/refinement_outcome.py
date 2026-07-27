"""Listener outcome trajectory snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

TRAJECTORY_REL = "understanding/listener_outcome_trajectory.json"


def append_listener_outcome(
    ctx: RunContext,
    milestone: str,
    scores_or_notes: dict[str, Any] | str | None = None,
) -> dict[str, Any]:
    if ctx.artifact_exists(TRAJECTORY_REL):
        doc = ctx.read_json(TRAJECTORY_REL)
        if not isinstance(doc, dict):
            doc = {"run_id": ctx.run_id, "schema_version": 1, "points": []}
    else:
        doc = {"run_id": ctx.run_id, "schema_version": 1, "points": []}
    point = {
        "milestone": milestone,
        "at": datetime.now(timezone.utc).isoformat(),
        "payload": scores_or_notes,
    }
    points = list(doc.get("points") or [])
    points.append(point)
    doc["points"] = points
    ctx.write_json(TRAJECTORY_REL, doc)
    ctx.log(
        f"listener_outcome:{milestone}",
        level="info",
        stage=milestone,
        action_id="listener_outcome",
        detail=point if isinstance(point, dict) else {"milestone": milestone},
    )
    return doc
