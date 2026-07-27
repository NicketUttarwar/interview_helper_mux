"""Shadow scoring — informational score written whenever a pass is skipped."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.refinement_catalog import refinement_cfg
from interview_mux.refinement_flow_integrity import DRAFT_REL, FINAL_REL
from interview_mux.run_context import RunContext

SHADOW_DIR = "understanding/refinement_shadow"


def shadow_score_enabled(cfg: dict[str, Any] | None = None) -> bool:
    block = refinement_cfg(cfg).get("shadow_score") or {}
    return bool(block.get("enabled", True))


def maybe_write_shadow_score(ctx: RunContext, pass_id_or_class: str) -> dict[str, Any] | None:
    """Write a lightweight informational score when a refinement pass is skipped.

    Never blocks or gates anything — purely observational so operators/analytics
    can see what a Pass 2 *might* have changed, without spending an LLM call.
    """
    if not shadow_score_enabled():
        return None
    draft = ctx.read_json(DRAFT_REL) if ctx.artifact_exists(DRAFT_REL) else None
    final = ctx.read_json(FINAL_REL) if ctx.artifact_exists(FINAL_REL) else None
    draft_lines = len((draft or {}).get("interviewer_lines") or []) if isinstance(draft, dict) else 0
    final_lines = len((final or {}).get("interviewer_lines") or []) if isinstance(final, dict) else 0
    doc = {
        "pass_id_or_class": pass_id_or_class,
        "at": datetime.now(timezone.utc).isoformat(),
        "draft_line_count": draft_lines,
        "final_line_count": final_lines,
        "heuristic": "skip_preserves_draft",
        "note": "Shadow score when Pass 2 skipped — informational only, never gates a decision.",
    }
    ctx.write_json(f"{SHADOW_DIR}/{pass_id_or_class}.json", doc)
    ctx.log(
        f"Shadow score written for {pass_id_or_class}",
        level="info",
        stage=pass_id_or_class,
        action_id="refinement_shadow",
        detail=doc,
    )
    return doc


def load_shadow_score(ctx: RunContext, pass_id_or_class: str) -> dict[str, Any] | None:
    rel = f"{SHADOW_DIR}/{pass_id_or_class}.json"
    if not ctx.artifact_exists(rel):
        return None
    doc = ctx.read_json(rel)
    return doc if isinstance(doc, dict) else None
