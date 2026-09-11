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
FAMILY_VO_ADJUDICATE_STALE = "vo_adjudicate_stale"
# B-03: remaster ↔ hitch ↔ fuse share one family ceiling (no osc re-arm).
FAMILY_JUNCTION = "junction_family"

HALT_FAMILIES = frozenset(
    {
        FAMILY_MIX_WITHOUT_ASSEMBLY,
        FAMILY_LAYUP_STALE,
        FAMILY_G1_MISSING,
        FAMILY_HITCH_LISTEN_RESTAGE,
        FAMILY_SELECTION_ORDER_DRIFT,
        FAMILY_VO_ADJUDICATE_STALE,
        # B-03: remaster ↔ hitch ↔ fuse share one ceiling (identical×3 halt).
        FAMILY_JUNCTION,
    }
)


@dataclass(frozen=True)
class HealRoute:
    family: str
    from_stage: str
    action: str = ""
    halt: bool = False
    detail: str = ""


@dataclass(frozen=True)
class PlaybookSpec:
    resume_stage: str
    action: str = ""


PLAYBOOK_REGISTRY: dict[str, PlaybookSpec] = {
    "never_touch_zeroed_keep": PlaybookSpec(
        resume_stage="edl", action="punch_or_omit_rebuild_edl"
    ),
    "vo_audibility_drift": PlaybookSpec(resume_stage="edl", action="rebuild_edl"),
    "opening_orientation_inaudible": PlaybookSpec(
        resume_stage="edl", action="retarget_rebuild_edl"
    ),
    "omit_collateral_vo_strip": PlaybookSpec(
        resume_stage="edl", action="exempt_rebuild_edl"
    ),
    "selection_edl_order_drift": PlaybookSpec(
        resume_stage="edl", action="rebuild_edl"
    ),
    "incomplete_cut_unresolved": PlaybookSpec(
        resume_stage="junction_snip_qa", action="junction_ladder"
    ),
    "pending_write_barrier": PlaybookSpec(
        resume_stage="junction_snip_qa", action="approve_or_rerun_producer"
    ),
    "musicgen_theme_failed": PlaybookSpec(
        resume_stage="music_palette_compose", action="generate_or_omit_bed"
    ),
    "post_master_quality_missing": PlaybookSpec(
        resume_stage="master_finalize", action="run_pmq"
    ),
    "pmq_incomplete_ship_walk": PlaybookSpec(
        # Default pin; recovery_controller overrides from listen_delight_remutate.json
        # (conversation/story → air_script_seams, not mix-only).
        resume_stage="air_script_seams", action="listen_delight_remutate"
    ),
    "layup_stale": PlaybookSpec(
        resume_stage="nugget_layup_compose", action="adopt_layup"
    ),
    "opening_slot_conflict": PlaybookSpec(
        resume_stage="edl", action="opening_slot_repair"
    ),
    "vo_contract_repair": PlaybookSpec(
        resume_stage="vo_line_adjudicate", action="vo_contract_ladder"
    ),
    "vo_seated_coverage": PlaybookSpec(resume_stage="vo_synthesize", action="repair_and_resynth"),
    "missing_g1_pickup": PlaybookSpec(
        resume_stage="vo_synthesize", action="ensure_g1"
    ),
    "assembly_not_rendered_from_current_edl": PlaybookSpec(
        resume_stage="mix", action="clear_mix_junction"
    ),
    "redundant_framing_transitions": PlaybookSpec(
        resume_stage="transitions", action="drop_redundant_framing_rows"
    ),
    "seed_order_prereq": PlaybookSpec(
        resume_stage="vo_synthesize", action="restamp_or_unmark_seed"
    ),
    "vo_ladder_fingerprint_stall": PlaybookSpec(
        resume_stage="vo_synthesize", action="pin_synth_after_ladder_cap"
    ),
}


def mix_assembly_seated(ctx: RunContext) -> bool:
    """Final assembly exists and is not stale vs the live EDL."""
    try:
        if ctx.artifact_exists("run_meta.json"):
            meta = ctx.read_json("run_meta.json")
            if isinstance(meta, dict) and meta.get("assembly_seating_stale"):
                return False
    except Exception:
        pass
    try:
        from interview_mux.thrash_hardening import artifact_usable

        ok, _ = artifact_usable(ctx, "master/assembly.wav", consumer="mix")
        if not ok:
            return False
    except Exception:
        pass
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
            from_stage="nugget_layup_compose",
            action="adopt_layup",
            detail="adopt to selection then resume layup — never remine compose unless adopt fails",
        )

    if (
        "vo_line_adjudication" in low
        or "adjudicate_before_synth" in low
        or "stale_script_hash" in low
        or ("wav_stale" in low and ("adjudicate" in low or stage_l == "edl_narrative_audit"))
        or (stage_l in {"vo_synthesize", "edl_narrative_audit", "edl"} and "adjudicate" in low)
    ):
        return HealRoute(
            family=FAMILY_VO_ADJUDICATE_STALE,
            from_stage="vo_line_adjudicate",
            action="rerun_adjudicate_synth",
            detail="adjudicate then synthesize — script/WAV drift before audit",
        )

    if (
        "g1 vo pickup missing" in low
        or "stale_or_missing_pickup" in low
        or "g1_vo_open" in low
        or "complete g1_vo_open" in low
        or "seated_bind_stale" in low
        or "synthesize wav stale/missing" in low
        or (stage_l in {"g1_vo_pickup", "g1_vo", "g1_vo_open", "edl"} and "pickup" in low and "missing" in low)
    ):
        if ctx is not None and gap_fill_skipped(ctx):
            return HealRoute(
                family=FAMILY_G1_MISSING,
                from_stage="edl",
                action="skip_interviewer_g1",
                detail="gap-fill skipped — interviewer G1 is not a block",
            )
        # g1_vo_open with adjudicate seeded → synthesize only (no rewrite thrash).
        # seated_bind_stale / post-synth resolve false-fail → synthesize only
        # (never rewind nugget_layup_compose — exec_10066).
        from_stage = "vo_line_adjudicate"
        detail = "adjudicate then synthesize — never rewind nugget_layup_compose"
        synth_only = (
            "seated_bind_stale" in low or "synthesize wav stale/missing" in low
        )
        if ctx is not None and (
            synth_only or "g1_vo_open" in low or "complete g1_vo_open" in low
        ):
            try:
                from interview_mux.delivery_invariants import resolve_g1_vo_open_resume

                from_stage = resolve_g1_vo_open_resume(ctx)
                detail = (
                    "g1_vo_open with adjudicate seeded — synthesize_g1 only, "
                    "do not re-adjudicate"
                    if from_stage == "vo_synthesize"
                    else "unified g1_vo_open resume — adjudicate then synthesize"
                )
            except Exception:
                try:
                    from interview_mux.delivery_guardrails import seed_stage_complete

                    adjudicate_seeded = seed_stage_complete(ctx, "vo_line_adjudicate") or (
                        ctx.is_done("vo_line_adjudicate")
                        and ctx.artifact_exists("understanding/gap_report.json")
                    )
                    if synth_only or adjudicate_seeded:
                        from_stage = "vo_synthesize"
                        detail = (
                            "seated/G1 synth hole — synthesize only, "
                            "do not re-adjudicate or re-layup"
                            if synth_only
                            else (
                                "g1_vo_open with adjudicate seeded — synthesize_g1 only, "
                                "do not re-adjudicate"
                            )
                        )
                except Exception:
                    if synth_only:
                        from_stage = "vo_synthesize"
                        detail = "seated/G1 synth hole — synthesize only"
        return HealRoute(
            family=FAMILY_G1_MISSING,
            from_stage=from_stage,
            action="synthesize_g1",
            detail=detail,
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
            # B-03: hitch shares FAMILY_JUNCTION with remaster/fuse (legacy alias kept).
            family=FAMILY_JUNCTION,
            from_stage="chapter_close_hitch",
            action="hitch_listen_restage",
            detail="junction_family:hitch_listen_restage",
        )

    if (
        "fuse_oscillation" in low
        or "oscillation_halt" in low
        or "connector_fuse_oscillation" in low
        or "junction_remaster_budget" in low
        or "junction_oscillation" in low
        or "junction_budget_exhaust" in low
    ):
        from_stage = "junction_snip_qa"
        action = "resume_junction"
        if "fuse" in low or "connector_fuse" in low:
            from_stage = "connector_fuse_pass" if "connector" in low or "fuse" in low else from_stage
            # Prefer fuse stage when the fingerprint is fuse-local.
            if "fuse" in low:
                from_stage = "edl"  # fuse is mid-EDL; resume producer not remaster-mix
                action = "fuse_residual"
        return HealRoute(
            family=FAMILY_JUNCTION,
            from_stage=from_stage,
            action=action,
            detail="junction_family:fuse_or_remaster_oscillation",
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
