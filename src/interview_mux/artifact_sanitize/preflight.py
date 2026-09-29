"""Shared sanitary preflight map for LLM + stage-input dual path (F10)."""

from __future__ import annotations

from typing import Any


def _prefix(kind: str, errs: list[str]) -> list[str]:
    return [f"{kind}_unsanitary: {e}" for e in errs[:4] if e]


def _sdp_errors_for_preflight(ctx: Any) -> list[str]:
    """Allow missing SDP on first write; block stale / needs_sanitize."""
    from interview_mux.artifact_sanitize.registry import sdp_sanitary_errors

    errs = sdp_sanitary_errors(ctx)
    if not errs:
        return []
    if all("missing" in e for e in errs):
        return []
    stale = [e for e in errs if "stale" in e or "needs_sanitize" in e or "unsanitary" in e]
    if stale:
        return stale
    # Non-missing structural refuse
    return [e for e in errs if "missing" not in e]


def sanitary_preflight_errors(ctx: Any, stage_id: str) -> list[str]:
    """Return sanitary blockers for ``stage_id`` (empty = pass).

    First-run missing-artifact semantics: do not block compose/craft when the
    producer artifact is absent; only block dirty/stale baselines that exist.
    """
    from interview_mux.artifact_sanitize.config import block_consumers_on_unsanitary

    if not block_consumers_on_unsanitary():
        return []

    sid = str(stage_id or "").strip()
    if not sid:
        return []

    from interview_mux.artifact_sanitize.registry import (
        air_contract_sanitary_errors,
        edl_sanitary_errors,
        gap_sanitary_errors,
        layup_sanitary_errors,
        selection_sanitary_errors,
        transitions_sanitary_errors,
        vo_sanitary_errors,
    )

    out: list[str] = []

    if sid == "nugget_layup_compose":
        out.extend(_prefix("selection", selection_sanitary_errors(ctx)))
        # Never block first compose on missing plan; only hollow / needs_recompose.
        if ctx.artifact_exists("understanding/nugget_layup_plan.json"):
            try:
                plan = ctx.read_json("understanding/nugget_layup_plan.json")
            except Exception:
                plan = None
            meta = plan.get("_meta") if isinstance(plan, dict) else {}
            hollow = bool(isinstance(meta, dict) and meta.get("needs_recompose"))
            if hollow or (
                isinstance(plan, dict)
                and not (plan.get("layups") or [])
                and bool(plan.get("ordered_segment_ids"))
            ):
                out.extend(_prefix("layup", layup_sanitary_errors(ctx)))
        return out

    if sid == "transitions":
        out.extend(_prefix("selection", selection_sanitary_errors(ctx)))
        if ctx.artifact_exists("master/transitions.json"):
            out.extend(_prefix("transitions", transitions_sanitary_errors(ctx)))
        return out

    if sid in {"sound_design_plan", "sound_design_plan_flow2"}:
        out.extend(_prefix("selection", selection_sanitary_errors(ctx)))
        if ctx.artifact_exists("understanding/nugget_layup_plan.json"):
            out.extend(_prefix("layup", layup_sanitary_errors(ctx)))
        if ctx.artifact_exists("master/transitions.json"):
            out.extend(_prefix("transitions", transitions_sanitary_errors(ctx)))
        if ctx.artifact_exists("understanding/sound_design_plan.json"):
            out.extend(_prefix("sdp", _sdp_errors_for_preflight(ctx)))
        return out

    if sid in {"sfx_prompt_craft", "sfx_prompt_refine", "music_palette_compose"}:
        out.extend(_prefix("sdp", _sdp_errors_for_preflight(ctx)))
        return out

    if sid == "edl_narrative_audit":
        if ctx.artifact_exists("master/selection.json"):
            out.extend(_prefix("selection", selection_sanitary_errors(ctx)))
        if ctx.artifact_exists("master/transitions.json"):
            out.extend(_prefix("transitions", transitions_sanitary_errors(ctx)))
        if ctx.artifact_exists("understanding/gap_report.json"):
            out.extend(_prefix("gap", gap_sanitary_errors(ctx)))
        out.extend(_prefix("vo", vo_sanitary_errors(ctx)))
        return out

    if sid == "edl":
        if ctx.artifact_exists("understanding/gap_report.json"):
            out.extend(_prefix("gap", gap_sanitary_errors(ctx)))
        out.extend(_prefix("vo", vo_sanitary_errors(ctx)))
        if ctx.artifact_exists("master/edl.json"):
            # edl rebuilds edl.json from the selection, so the old file drifting
            # from the selection is the reason to run it, not a reason to refuse
            # (exec_052 after the junction retires, ISSUES entry 65).
            out.extend(
                _prefix(
                    "edl",
                    [e for e in edl_sanitary_errors(ctx) if "order_drift" not in str(e)],
                )
            )
        return out

    if sid in {"vo_line_adjudicate", "nugget_intro_compose"}:
        if ctx.artifact_exists("understanding/gap_report.json"):
            out.extend(_prefix("gap", gap_sanitary_errors(ctx)))
        if ctx.artifact_exists("mastering/mastering_plan.json"):
            out.extend(_prefix("air_contract", air_contract_sanitary_errors(ctx)))
        return out

    if sid == "vo_synthesize":
        if ctx.artifact_exists("understanding/gap_report.json"):
            out.extend(_prefix("gap", gap_sanitary_errors(ctx)))
        if ctx.artifact_exists("mastering/mastering_plan.json"):
            out.extend(_prefix("air_contract", air_contract_sanitary_errors(ctx)))
        return out

    if sid in {"podcast_sfx_brief", "full_master_ranking"}:
        if ctx.artifact_exists("master/selection.json"):
            out.extend(_prefix("selection", selection_sanitary_errors(ctx)))
        return out

    return out
