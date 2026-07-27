"""Downstream invalidation cascade after an accepted refinement candidate."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

CASCADE_REL = "understanding/refinement_cascade.json"

DEFAULT_STAGES_TO_INVALIDATE = ["transitions", "sound_design_vo_finalize"]


def write_cascade(
    ctx: RunContext,
    *,
    changed_line_ids: list[str],
    dropped_line_ids: list[str],
    stages_to_invalidate: list[str] | None = None,
) -> dict[str, Any]:
    """Record which lines/stages must be re-synthesized or re-mixed downstream."""
    doc = {
        "at": datetime.now(timezone.utc).isoformat(),
        "line_ids_changed": list(changed_line_ids),
        "line_ids_dropped": list(dropped_line_ids),
        "stages_to_invalidate": list(stages_to_invalidate or DEFAULT_STAGES_TO_INVALIDATE),
        "g1_synth_line_ids": list(changed_line_ids),
        "remix_after_edl": True,
    }
    ctx.write_json(CASCADE_REL, doc)
    ctx.log(
        "Refinement cascade written — downstream stages flagged for re-synthesis/remix",
        level="info",
        stage="refinement_cascade",
        action_id="refinement_cascade",
        detail=doc,
    )
    return doc


def load_cascade(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(CASCADE_REL):
        return None
    doc = ctx.read_json(CASCADE_REL)
    return doc if isinstance(doc, dict) else None
