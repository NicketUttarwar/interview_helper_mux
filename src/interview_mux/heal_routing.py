"""Heal routing — never remaster mix for a text/id problem.

One table for the full-auto driver and Homunculus remaster seed. Identical
fingerprints halt after 3; after halt the driver must stop, not keepalive-retry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from interview_mux.run_context import RunContext

HALT_AFTER = 3

FAMILY_MIX_WITHOUT_ASSEMBLY = "mix_without_assembly"
FAMILY_LAYUP_STALE = "layup_stale"
FAMILY_G1_MISSING = "g1_missing"
FAMILY_HITCH_LISTEN_RESTAGE = "hitch_listen_restage"
FAMILY_SELECTION_ORDER_DRIFT = "selection_order_drift"
FAMILY_SPOKEN_COPY = "spoken_copy"
FAMILY_MIX_WAV_SEATED = "mix_wav_seated"

HALT_FAMILIES = frozenset(
    {
        FAMILY_MIX_WITHOUT_ASSEMBLY,
        FAMILY_LAYUP_STALE,
        FAMILY_G1_MISSING,
        FAMILY_HITCH_LISTEN_RESTAGE,
        FAMILY_SELECTION_ORDER_DRIFT,
    }
)


@dataclass(frozen=True)
class HealRoute:
    family: str
    from_stage: str
    action: str = ""
    halt: bool = False
    detail: str = ""


def mix_assembly_seated(ctx: RunContext) -> bool:
    """Final assembly exists and is not stale vs the live EDL."""
    try:
        from interview_mux.air_order import mix_outputs_seated

        return bool(mix_outputs_seated(ctx))
    except Exception:
        asm = ctx.final_path("master", "assembly.wav")
        edl = ctx.final_path("master", "edl.json")
        return asm.is_file() and edl.is_file()


def gap_fill_skipped(ctx: RunContext) -> bool:
    try:
        from interview_mux.gates import g1_vo_was_skipped_optional

        if g1_vo_was_skipped_optional(ctx):
            return True
    except Exception:
        pass
    try:
        if ctx.artifact_exists("run_meta.json"):
            meta = ctx.read_json("run_meta.json")
            if isinstance(meta, dict) and meta.get("gap_fill_skipped"):
                return True
    except Exception:
        pass
    return False


def classify_heal_error(
    err: str,
    ctx: RunContext | None = None,
    *,
    stage: str = "",
) -> HealRoute | None:
    """Map an error fingerprint onto a resume stage. None = not this table."""
    low = str(err or "").lower()
    stage_l = str(stage or "").lower()

    seated = bool(ctx is not None and mix_assembly_seated(ctx))

    if (
        "nugget_layup_plan_stale" in low
        or "stale vs selection" in low
        or "layup plan stale" in low
    ):
        return HealRoute(
            family=FAMILY_LAYUP_STALE,
            from_stage="edl",
            action="adopt_layup",
            detail="adopt then edl — never remine compose",
        )

    if (
        "g1 vo pickup missing" in low
        or "stale_or_missing_pickup" in low
        or (stage_l in {"g1_vo_pickup", "g1_vo", "edl"} and "pickup" in low and "missing" in low)
    ):
        if ctx is not None and gap_fill_skipped(ctx):
            return HealRoute(
                family=FAMILY_G1_MISSING,
                from_stage="edl",
                action="skip_interviewer_g1",
                detail="gap-fill skipped — interviewer G1 is not a block",
            )
        return HealRoute(
            family=FAMILY_G1_MISSING,
            from_stage="vo_synthesize",
            action="synthesize_g1",
            detail="synthesize/wait — never rewind nugget_layup_compose",
        )

    if (
        "spoken_vo_speakable" in low
        or "spoken_repeated_copy" in low
        or "spoken_self_loop" in low
        or "self-loop" in low
        or "self_loop" in low
    ):
        return HealRoute(
            family=FAMILY_SPOKEN_COPY,
            from_stage="transitions",
            action="rewrite_transitions",
            detail="rewrite transitions/edl — not mix",
        )

    if "hitch_listen_restage" in low or "incomplete_cut_restage_hitch" in low:
        return HealRoute(
            family=FAMILY_HITCH_LISTEN_RESTAGE,
            from_stage="chapter_close_hitch",
            action="hitch_listen_restage",
        )

    if (
        "selection_edl_order_drift" in low
        or "speech clip order diverges" in low
        or "ordered_segment_ids drifted" in low
    ):
        return HealRoute(
            family=FAMILY_SELECTION_ORDER_DRIFT,
            from_stage="edl",
            action="rebuild_edl",
        )

    assembly_err = "assembly.wav" in low
    missing_wav = "missing" in low and assembly_err
    if missing_wav or (assembly_err and "finished without" in low):
        if seated:
            return HealRoute(
                family=FAMILY_MIX_WAV_SEATED,
                from_stage="junction_snip_qa",
                action="resume_junction",
                detail="final wav exists and is not stale vs EDL",
            )
        return HealRoute(
            family=FAMILY_MIX_WITHOUT_ASSEMBLY,
            from_stage="mix",
            action="remaster_mix",
            detail="wav missing or older than EDL",
        )
    return None


def apply_heal_route(ctx: RunContext, route: HealRoute) -> dict[str, Any]:
    """Run the cheap product action for a route (adopt, etc.). Never remine."""
    if route.action == "adopt_layup":
        from interview_mux.nugget_layup import adopt_layup_plan_to_selection

        return adopt_layup_plan_to_selection(ctx, persist=True, stage="heal_routing")
    return {"ok": True, "action": route.action}


def record_heal_fingerprint(
    ctx: RunContext,
    route: HealRoute,
    *,
    reason: str,
    stage: str = "",
) -> dict[str, Any]:
    """Record + halt after 3 identical fingerprints the driver must honor."""
    from interview_mux.identical_failures import record_identical_failure

    row = record_identical_failure(
        ctx,
        failed_stage=stage or route.from_stage,
        producer=route.family,
        reason=reason,
        resume_attempted=route.from_stage,
    )
    halted = bool(row.get("halt")) and route.family in HALT_FAMILIES
    return {**row, "halt": halted, "family": route.family}


def heal_is_halted(
    ctx: RunContext,
    route: HealRoute,
    *,
    reason: str,
    stage: str = "",
) -> bool:
    from interview_mux.identical_failures import failure_signature, is_halted

    if route.family not in HALT_FAMILIES:
        return False
    sig = failure_signature(
        failed_stage=stage or route.from_stage,
        producer=route.family,
        reason=reason,
    )
    return is_halted(ctx, sig)
