"""Marker-only invalidate cascades after sanitize hash changes (F5)."""

from __future__ import annotations

from typing import Any

# artifact_rel → stage_done markers to clear (never wipe EDL/music wholesale)
_SANITIZE_CASCADE: dict[str, tuple[str, ...]] = {
    "understanding/gap_report.json": (
        "vo_line_adjudicate",
        "vo_synthesize",
        "edl_narrative_audit",
        "edl",
        "assembly_preview",
    ),
    "mastering/mastering_plan.json": (
        "vo_synthesize",
        "edl_narrative_audit",
        "edl",
    ),
    "understanding/omit_ledger.json": (
        "vo_synthesize",
        "edl",
    ),
    "vo_pickup/synthesis_report.json": (
        "edl_narrative_audit",
        "edl",
        "assembly_preview",
    ),
    "mastering/vo_synthesize.json": (
        "edl_narrative_audit",
        "edl",
        "assembly_preview",
    ),
    "master/transitions.json": (
        "sound_design_plan",
        "edl_narrative_audit",
        "edl",
        "assembly_preview",
    ),
    "understanding/nugget_layup_plan.json": (
        "sound_design_plan",
        "transitions",
        "vo_line_adjudicate",
        "vo_synthesize",
        "edl_narrative_audit",
        "edl",
    ),
    "understanding/sound_design_plan.json": (
        "music_palette_compose",
        "sfx_prompt_craft",
        "mmaudio_sfx",
    ),
}

# Map artifact → invalidation blast source key
_BLAST_SOURCE: dict[str, str] = {
    "understanding/gap_report.json": "gap_report_sanitize",
    "mastering/mastering_plan.json": "air_contract_sanitize",
    "understanding/omit_ledger.json": "air_contract_sanitize",
    "vo_pickup/synthesis_report.json": "vo_synthesize",
    "mastering/vo_synthesize.json": "vo_synthesize",
    "master/transitions.json": "transitions_write",
    "understanding/nugget_layup_plan.json": "nugget_layup_compose",
    "understanding/sound_design_plan.json": "sound_design_plan",
}


def _mid_synth_cascade_suppressed(ctx: Any) -> bool:
    """Respect in-flight VO synth / spoken-text cascade suppress flags."""
    if getattr(ctx, "_mid_synth_cascade_suppress", False):
        return True
    if getattr(ctx, "_spoken_text_cascade_depth", 0):
        return True
    consumer = str(getattr(ctx, "_lifecycle_consumer_stage", "") or "")
    if consumer == "vo_synthesize":
        return True
    return False


def maybe_invalidate_after_sanitize(
    ctx: Any,
    artifact_rel: str,
    *,
    before_hash: str = "",
    after_hash: str = "",
    ok: bool = True,
    actions_n: int = 0,
) -> list[str]:
    """Unmark consumer stage_done markers when sanitize content hash changes.

    Marker-only — does not archive/wipe EDL JSON or music assets wholesale.
    """
    from interview_mux.artifact_sanitize.reentry import in_sanitize_reentry

    if not ok:
        return []
    if before_hash and after_hash and before_hash == after_hash and int(actions_n or 0) <= 0:
        return []
    if before_hash and after_hash and before_hash == after_hash:
        return []
    if _mid_synth_cascade_suppressed(ctx):
        return ["skipped:mid_synth_cascade_suppress"]
    # Nested sanitize commits already hold the reentry flag — still allow
    # invalidate from the outermost commit only.
    if in_sanitize_reentry(ctx) and getattr(ctx, "_sanitize_invalidate_nested_ok", False) is not True:
        # Allow when called from inside commit (flag set by caller) — default skip
        # only pure nested reentry without an explicit outer commit.
        pass

    rel = str(artifact_rel or "").replace("\\", "/")
    targets = _SANITIZE_CASCADE.get(rel)
    if not targets:
        return []

    blast_source = _BLAST_SOURCE.get(rel, rel)
    cleared: list[str] = []
    try:
        from interview_mux.delivery_guardrails import (
            invalidation_allowed_downstream,
            music_clear_blocked,
        )
    except Exception:
        invalidation_allowed_downstream = None  # type: ignore[assignment]
        music_clear_blocked = None  # type: ignore[assignment]

    for sid in targets:
        if invalidation_allowed_downstream is not None:
            try:
                if not invalidation_allowed_downstream(blast_source, sid):
                    continue
            except Exception:
                pass
        if music_clear_blocked is not None:
            try:
                if music_clear_blocked(ctx, sid, source=blast_source):
                    cleared.append(f"blocked_music:{sid}")
                    continue
            except Exception:
                pass
        marker = ctx.final_path(".stage_done", sid)
        if marker.is_file():
            try:
                marker.unlink()
                cleared.append(sid)
            except OSError:
                pass

    if cleared:
        try:
            ctx.log(
                f"sanitize invalidate {rel}: unmarked {cleared[:8]}",
                level="info",
                stage="artifact_sanitize",
                detail={
                    "artifact": rel,
                    "before_hash": before_hash,
                    "after_hash": after_hash,
                    "cleared": cleared,
                },
            )
        except Exception:
            pass
        try:
            from interview_mux.artifact_sanitize.audit import write_sanitize_audit
            from interview_mux.artifact_sanitize.types import SanitizeResult

            write_sanitize_audit(
                ctx,
                SanitizeResult(
                    doc={},
                    ok=True,
                    errors=[],
                    artifact_rel=rel,
                    actions=[{"action": "invalidate_markers", "cleared": cleared}],
                    metrics={"cleared": len(cleared)},
                ),
                stage_key="sanitize_invalidate",
                mode="invalidate",
            )
        except Exception:
            pass
    return cleared
