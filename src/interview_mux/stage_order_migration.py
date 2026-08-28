"""5A — auto migration when resuming runs started before new homunculus stages."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

# Homunculus 0.1.0+ stages inserted after in-progress runs may have been skipped.
HOMUNCULUS_NEW_STAGES: tuple[str, ...] = (
    "framing_posture_decide",
    "vo_line_adjudicate",
)

# Delivery stages that must not be done before vo_line_adjudicate (5C).
_DELIVERY_AFTER_ADJUDICATE = frozenset(
    {
        "vo_synthesize",
        "edl_narrative_audit",
        "edl",
        "assembly_preview",
        "listen_delight_audit",
        "music_palette_compose",
        "sfx_prompt_craft",
        "mmaudio_sfx",
        "mix",
        "junction_snip_qa",
        "master_finalize",
        "master_transcript_build",
        "episode_meta_build",
        "episode_cover_prompt_craft",
        "podcast_encode_mp3",
        "episode_cover_generate",
        "podcast_publish",
    }
)


def _full_order() -> list[str]:
    return list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)


def _homunculus_resume(ctx: RunContext) -> bool:
    try:
        from interview_mux.homunculus.runtime import is_homunculus_run

        return is_homunculus_run(ctx)
    except Exception:
        return False


def _stage_output_ok(ctx: RunContext, stage: str) -> bool:
    try:
        from interview_mux.homunculus.agenda import stage_outputs_present

        return stage_outputs_present(ctx, stage)
    except Exception:
        from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

        rel = STAGE_ARTIFACT_DISK_PATHS.get(stage)
        if not rel:
            return ctx.is_done(stage)
        return ctx.artifact_exists(rel)


def _any_downstream_done(ctx: RunContext, order: list[str], idx: int) -> bool:
    return any(ctx.is_done(s) for s in order[idx + 1 :])


def detect_stale_new_stage_order(ctx: RunContext) -> str | None:
    """First new-stage slot where downstream is done but this stage never produced output."""
    if not _homunculus_resume(ctx):
        return None
    order = _full_order()
    for stage in HOMUNCULUS_NEW_STAGES:
        if stage not in order:
            continue
        idx = order.index(stage)
        if not _any_downstream_done(ctx, order, idx):
            continue
        if ctx.is_done(stage) and _stage_output_ok(ctx, stage):
            continue
        if not ctx.is_done(stage) or not _stage_output_ok(ctx, stage):
            return stage
    # 5C reorder: synth/audit done without adjudicate.
    if "vo_line_adjudicate" in order:
        adj_idx = order.index("vo_line_adjudicate")
        if not ctx.is_done("vo_line_adjudicate") or not _stage_output_ok(
            ctx, "vo_line_adjudicate"
        ):
            if any(ctx.is_done(s) for s in _DELIVERY_AFTER_ADJUDICATE):
                return "vo_line_adjudicate"
        if _any_downstream_done(ctx, order, adj_idx) and not _stage_output_ok(
            ctx, "vo_line_adjudicate"
        ):
            return "vo_line_adjudicate"
    return None


def migrate_stale_stage_order_on_resume(ctx: RunContext) -> dict[str, Any]:
    """Unmark downstream from the first missing new-stage output. Idempotent."""
    first = detect_stale_new_stage_order(ctx)
    if not first:
        return {"migrated": False, "from_stage": None, "cleared": []}
    order = _full_order()
    if first not in order:
        return {"migrated": False, "from_stage": first, "cleared": []}
    idx = order.index(first)
    cleared: list[str] = []
    try:
        from interview_mux.homunculus.agenda import unmark_stage_only

        for stage in order[idx:]:
            if ctx.is_done(stage):
                unmark_stage_only(ctx, stage)
                cleared.append(stage)
    except Exception:
        for stage in order[idx:]:
            marker = ctx.final_path(".stage_done", stage)
            if marker.is_file():
                marker.unlink(missing_ok=True)
                cleared.append(stage)
    if cleared:
        ctx.log(
            f"5A stage-order migration: unmarked from {first} — "
            + ", ".join(cleared[:8])
            + ("…" if len(cleared) > 8 else ""),
            level="warning",
            stage=first,
            detail={"cleared": cleared, "reason": "stale_new_stage_order"},
        )
    return {"migrated": bool(cleared), "from_stage": first, "cleared": cleared}


__all__ = [
    "HOMUNCULUS_NEW_STAGES",
    "detect_stale_new_stage_order",
    "migrate_stale_stage_order_on_resume",
]
