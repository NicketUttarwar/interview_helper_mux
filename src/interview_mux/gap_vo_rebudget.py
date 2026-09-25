"""Post-ranking VO density re-budget for analysis-era gap compose (R3).

Compose runs before selection; hosted floor / vo_line_budget may have been
scaled from warrant gaps. After selection is sealed (ranking + sanitize),
recompute density notes so layup/compose incompleteness use air-order truth.
"""

from __future__ import annotations

import math
from typing import Any

from interview_mux.run_context import RunContext

REBUDGET_REL = "understanding/gap_vo_rebudget_after_selection.json"


def note_gap_vo_rebudget_after_selection(
    ctx: RunContext, *, stage_key: str | None = None
) -> dict[str, Any] | None:
    """Write selection-scaled VO budget note; fail-open on errors."""
    try:
        from interview_mux.config import merged_config
        from interview_mux.gap_fill_eligibility import (
            count_active_gap_vo_lines,
            min_synthetic_vo_lines,
        )
        from interview_mux.gap_vo_gates import gap_framing_enabled
        from interview_mux.hosted_vo_authority import identify_hosted_vo_floor
        from interview_mux.write_staging import active_stage_id

        sk = stage_key or active_stage_id() or "selection_order_sanitize"
        if not gap_framing_enabled(ctx):
            return None
        try:
            identify_hosted_vo_floor(ctx, persist=True)
        except Exception:
            pass
        ordered_n = 0
        if ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                ordered_n = len(
                    [s for s in (sel.get("ordered_segment_ids") or []) if s]
                )
        if ordered_n <= 0:
            return None
        gf = ((merged_config().get("analysis") or {}).get("gap_framing") or {})
        min_r = float(gf.get("min_vo_insert_ratio") or 0.0)
        tgt_r = float(gf.get("target_vo_insert_ratio") or 0.08)
        vo_min = int(math.ceil(ordered_n * min_r)) if min_r > 0 else 0
        vo_ideal = max(vo_min, int(math.ceil(ordered_n * tgt_r)))
        floor = min_synthetic_vo_lines(ctx)
        active = count_active_gap_vo_lines(ctx)
        doc = {
            "version": 1,
            "source": sk,
            "ordered_n": ordered_n,
            "vo_line_budget": {
                "min": vo_min,
                "ideal": vo_ideal,
                "max": max(vo_ideal, vo_min),
                "scale_basis": "selection",
            },
            "hosted_floor": floor,
            "active_lines": active,
            "floor_met": active >= floor,
        }
        ctx.write_json(
            REBUDGET_REL,
            doc,
            skip_handoff=True,
            stage_key=sk,
        )
        ctx.log(
            f"gap_vo rebudget after selection: ordered_n={ordered_n} "
            f"ideal={vo_ideal} active={active} floor={floor}",
            level="info",
            stage=sk,
            action_id="gap_vo.rebudget_after_selection",
            detail=doc,
        )
        return doc
    except Exception as exc:
        try:
            from interview_mux.write_staging import active_stage_id

            sk = stage_key or active_stage_id() or "selection_order_sanitize"
            ctx.log(
                f"gap_vo rebudget after selection skipped: {exc}",
                level="warning",
                stage=sk,
            )
        except Exception:
            pass
        return None
