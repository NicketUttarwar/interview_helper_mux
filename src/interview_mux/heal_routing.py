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
    max_cycles: int = 3
    escalate_after: int = HALT_AFTER
    blocking_checkpoint: str = ""


PLAYBOOK_REGISTRY: dict[str, PlaybookSpec] = {
    "never_touch_zeroed_keep": PlaybookSpec(
        resume_stage="edl", action="punch_or_omit_rebuild_edl"
    ),
    "vo_audibility_drift": PlaybookSpec(resume_stage="edl", action="rebuild_edl"),
    "opening_orientation_inaudible": PlaybookSpec(
        resume_stage="edl", action="retarget_rebuild_edl"
    ),
    # The EDL seats every required line that has a WAV (ISSUES 184), so an
    # unseated required line means its WAV is missing: re-speak it and let the
    # walk rebuild the EDL. The old "exempt_rebuild_edl" action was a label no
    # code implemented; resuming edl reached the same suppress every time.
    "omit_collateral_vo_strip": PlaybookSpec(
        resume_stage="vo_synthesize", action="resynthesize_rebuild_edl"
    ),
    "selection_edl_order_drift": PlaybookSpec(
        resume_stage="edl", action="rebuild_edl"
    ),
    "incomplete_cut_unresolved": PlaybookSpec(
        resume_stage="junction_snip_qa",
        action="junction_ladder",
        blocking_checkpoint="pre_mix",
    ),
    "critical_junction_residual": PlaybookSpec(
        resume_stage="junction_snip_qa",
        action="junction_ladder",
        blocking_checkpoint="pre_mix",
    ),
    "seam_autopsy_blocking": PlaybookSpec(
        resume_stage="junction_snip_qa",
        action="junction_ladder",
        blocking_checkpoint="pre_mix",
    ),
    # Paperwork-only: stale applied stamps vs EDL — reconcile, do not ladder.
    "junction_claim_inventory_stale": PlaybookSpec(
        resume_stage="mix",
        action="claim_reconcile",
        blocking_checkpoint="pre_mix",
    ),
    "claimed_repairs_missing_from_edl": PlaybookSpec(
        resume_stage="mix",
        action="claim_reconcile",
        blocking_checkpoint="pre_mix",
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
    "vo_seated_coverage": PlaybookSpec(
        resume_stage="vo_synthesize", action="repair_and_resynth"
    ),
    "missing_g1_pickup": PlaybookSpec(
        resume_stage="vo_synthesize", action="ensure_g1"
    ),
    "g1_vo_incomplete": PlaybookSpec(
        resume_stage="vo_synthesize", action="ensure_g1"
    ),
    "mmaudio_incomplete": PlaybookSpec(
        resume_stage="mmaudio_sfx", action="regenerate_referenced_wavs"
    ),
    "sdp_theme_wavs_missing": PlaybookSpec(
        resume_stage="mmaudio_sfx", action="generate_sdp_theme_wavs"
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
    "g0_pending": PlaybookSpec(
        resume_stage="transcript_review", action="operator_g0"
    ),
    "research_shape_core_thin": PlaybookSpec(
        resume_stage="mastering_research_rollup", action="rerun_research_rollup"
    ),
    "voice_reference_pending": PlaybookSpec(
        resume_stage="missing_framing", action="operator_voice_ref"
    ),
    "high_gap_unframed": PlaybookSpec(
        # No-ctx default is analysis-era compose. Live pin (layup when it owns)
        # is high_gap_heal_resume_stage / classify_heal_error / recovery.
        resume_stage="gap_framing_compose",
        action="fill_or_demote_high_gaps",
    ),
    "fuse_oscillation": PlaybookSpec(
        # No-ctx default is connector_fuse_pass. Live pin (pre_ranking) is
        # fuse_oscillation_heal_resume_stage / classify_heal_error.
        resume_stage="connector_fuse_pass",
        action="fuse_residual",
    ),
    "connector_fuse_oscillation": PlaybookSpec(
        resume_stage="connector_fuse_pass",
        action="fuse_residual",
    ),
}


def resume_stage_for_error_class(
    error_class: str,
    *,
    default: str = "",
) -> str:
    """Single SSOT resume pin from PLAYBOOK_REGISTRY."""
    spec = PLAYBOOK_REGISTRY.get(str(error_class or "").strip())
    if spec is not None:
        return str(spec.resume_stage or default or "")
    return str(default or "")


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
        # HX-2: files-exist is not seated. Junction autopsy (HX-3) stays later.
        return False


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

    if ctx is not None and (
        "hosted_vo_floor" in low
        or "hollow_zero" in low
        or "no synthesize lines" in low
        or "hosted_vo_floor_unmet" in low
        or "hosted_vo_floor_unsatisfiable" in low
    ):
        from interview_mux.hosted_vo_authority import resume_producer

        pin = (
            resume_producer(ctx, stage_id=stage or None)
            or "gap_framing_compose"
        )
        return HealRoute(
            family="hosted_vo_floor",
            from_stage=pin,
            action="remint_producer",
            detail=(
                "hosted_vo_floor / hollow mint / no synthesize lines — "
                f"pin {pin}, never edl_narrative_audit"
            ),
        )

    if "authority_denied" in low:
        from interview_mux.artifact_ownership import (
            _suggested_owner_for_deny,
            parse_authority_denied_resume,
        )

        pin = parse_authority_denied_resume(err, ctx=ctx, denied_stage=stage)
        if not pin:
            pin = _suggested_owner_for_deny(ctx, "", stage=stage) if ctx else ""
        if not pin:
            pin = "listen_delight_audit" if "listen_delight" in low else (stage or "edl")
        # Never re-pin the denied writer when an ALLOW owner is known.
        denied_writer = ""
        try:
            parts = str(err or "").split(":")
            # authority_denied:verb:path:writer:epoch:suggested
            if len(parts) >= 4:
                denied_writer = parts[3].strip()
        except Exception:
            denied_writer = ""
        if pin and denied_writer and pin == denied_writer and "listen_delight" in low:
            pin = "listen_delight_audit"
        return HealRoute(
            family="authority_denied",
            from_stage=pin,
            action="resume_allow_owner",
            detail=(
                f"authority_denied — pin ALLOW owner {pin}, "
                f"never denied writer {denied_writer or stage_l or '?'}"
            ),
        )

    seated = bool(ctx is not None and mix_assembly_seated(ctx))

    if (
        "g0_pending" in low
        or "transcript review required" in low
        or "transcript review gate" in low
        or "g0 transcript review pending" in low
    ):
        from interview_mux.stage_completion import g0_heal_resume_stage

        return HealRoute(
            family="g0_pending",
            from_stage=g0_heal_resume_stage(ctx),
            action="operator_g0",
            detail="G0 open — pin transcript_review when the queue exists; build only if missing",
        )

    if "shape-core" in low or "research dossier" in low or "research shape-core" in low:
        return HealRoute(
            family="research_shape_core_thin",
            from_stage="mastering_research_rollup",
            action="rerun_research_rollup",
            detail="shape-core thin — pin mastering_research_rollup, never edl or the Shape/gap consumer",
        )

    if (
        "voice_reference_pending" in low
        or "voice reference gate" in low
        or "approve interviewer voice" in low
    ):
        return HealRoute(
            family="voice_reference_pending",
            from_stage="missing_framing",
            action="operator_voice_ref",
            detail="G-VoiceRef open — pin missing_framing, never topic_coverage_audit",
        )

    if "high_gap_unframed" in low or (
        "high gap segment" in low and "no interviewer line" in low
    ):
        from interview_mux.stage_completion import high_gap_heal_resume_stage

        pin = high_gap_heal_resume_stage(ctx)
        return HealRoute(
            family="high_gap_unframed",
            from_stage=pin,
            action="fill_or_demote_high_gaps",
            detail=(
                "high_gap_unframed — pin nugget_layup_compose when layup owns, "
                "else gap_framing_compose"
            ),
        )

    if (
        "vo_audibility_drift" in low
        or "opening_orientation_inaudible" in low
        or "never_touch_zeroed_keep" in low
        or "phantom_vo" in low
        or "edl_survivor_wipe" in low
    ):
        from interview_mux.stage_completion import edl_heal_resume_stage

        pin = edl_heal_resume_stage(ctx)
        if "edl_survivor_wipe" in low:
            family = "vo_audibility_drift"
            detail = (
                "edl_survivor_wipe — layup/required WAV without EDL seat; "
                "rebuild edl (do not remint / do not pin narrative audit)"
            )
        elif "audibility" in low or "phantom_vo" in low:
            family = "vo_audibility_drift"
            detail = "HE-2: unsanitary VO/bind pins vo_synthesize; sanitary may resume edl"
        elif "orientation" in low:
            family = "opening_orientation_inaudible"
            detail = "HE-2: unsanitary VO/bind pins vo_synthesize; sanitary may resume edl"
        else:
            family = "never_touch_zeroed_keep"
            detail = "HE-2: unsanitary VO/bind pins vo_synthesize; sanitary may resume edl"
        return HealRoute(
            family=family,
            from_stage=pin,
            action="rebuild_edl" if pin == "edl" else "repair_and_resynth",
            detail=detail,
        )

    if "gap_unsanitary" in low or (
        stage_l in {"gap_framing_recompose", "selection_framing_apply"}
        and "unsanitary" in low
    ):
        from interview_mux.stage_completion import pass2_gap_heal_resume_stage

        pin = pass2_gap_heal_resume_stage(ctx, error=err, stage=stage)
        if pin:
            return HealRoute(
                family="gap_unsanitary",
                from_stage=pin,
                action="rerun_pass2_writer",
                detail="HF-5: Pass-2 re-dirtied gap pins the writer, never W1 under freeze",
            )

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

    # End-C: incomplete / stub bridge → mint transitions, never soft-pass EDL.
    if (
        "bridge_completeness" in low
        or "bridge_incomplete" in low
        or "bridge incomplete" in low
        or "reorder join" in low
        or ("reorder seam" in low and "missing" in low)
        or "stub bridge" in low
        or "canned/repeated stub" in low
    ):
        return HealRoute(
            family="bridge_incomplete",
            from_stage="transitions",
            action="mint_pair_glue",
            detail="End-C: incomplete reorder glue pins transitions, never soft-complete EDL",
        )

    # End-C: framing / forward-cue quality → layup or compose writer, never EDL.
    if (
        "missing_forward_cue" in low
        or "forward-cue" in low
        or "forward cue" in low
        or "framing_before_impact" in low
        or "lacks preceding framing vo" in low
        or ("framing vo" in low and "preceding" in low)
        or ("impact segment" in low and "framing" in low)
    ):
        from interview_mux.stage_completion import high_gap_heal_resume_stage

        pin = high_gap_heal_resume_stage(ctx)
        return HealRoute(
            family="framing_quality",
            from_stage=pin,
            action="rewrite_framing",
            detail=(
                "End-C: framing/forward-cue pins nugget_layup_compose when layup owns, "
                "else gap_framing_compose — never EDL"
            ),
        )

    # F4 / HV-2 / HE-3: spoken glue / seated VO WAV missing → synthesize first, never EDL/mix.
    if (
        "gap vo lines missing wav" in low
        or "transition pairs missing wav" in low
        or "transition pairs still missing wav" in low
        or "current transition pairs missing wav" in low
        or "vo coverage not rendered" in low
        or "heard_wav_flow" in low
        or ("seated synthesize" in low and "missing wav" in low)
        or (
            "missing source_path" in low
            and (
                "assembly_preview" in low
                or "vo_pickup" in low
                or "transition" in low
            )
        )
    ):
        return HealRoute(
            family=FAMILY_G1_MISSING,
            from_stage="vo_synthesize",
            action="synthesize_g1",
            detail="bridge/VO WAV missing — synthesize first, never rebuild EDL or remaster mix",
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

    # The three structural post-master checks (ISSUES 185): each resumes the
    # stage that can produce the missing thing, instead of escalating with no
    # playbook at master_finalize.
    if "post-master quality failed" in low or "post_master_quality_failed" in low:
        if "audible_script_hash_agreement" in low:
            return HealRoute(
                family="pmq_structural",
                from_stage="vo_synthesize",
                action="resynthesize_rebuild_edl",
                detail="WAV hash disagrees with its script — re-speak, rebuild EDL and mix",
            )
        if "seam_commitment" in low:
            return HealRoute(
                family="pmq_structural",
                from_stage="junction_snip_qa",
                action="recommit_seams",
                detail="seam autopsy not committed — rerun junction to commit and remaster",
            )
        if "master_exists_nonempty" in low:
            return HealRoute(
                family="pmq_structural",
                from_stage="mix",
                action="remix",
                detail="master missing or empty — re-render mix",
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

    if "hitch_layup_adopt_failed" in low:
        return HealRoute(
            family="hitch_layup_adopt_failed",
            from_stage="nugget_layup_compose",
            action="adopt_layup",
            detail="HR-1: hitch adopt failed — pin nugget_layup_compose, never hitch-complete",
        )

    if "selection_commit_refused" in low:
        from interview_mux.stage_completion import parse_resume_stage_from_reason

        pin = parse_resume_stage_from_reason(err)
        if pin not in {"air_script_compose", "nugget_layup_compose"}:
            pin = (
                "nugget_layup_compose"
                if "nugget_layup" in low
                else "air_script_compose"
            )
        return HealRoute(
            family="selection_commit_refused",
            from_stage=pin,
            action="commit_selection",
            detail="HR-2: selection commit refused — pin the writer, never W1/edl",
        )

    if "hitch_listen_restage" in low or "incomplete_cut_restage_hitch" in low:
        return HealRoute(
            # B-03: hitch shares FAMILY_JUNCTION with remaster/fuse (legacy alias kept).
            family=FAMILY_JUNCTION,
            from_stage="chapter_close_hitch",
            action="hitch_listen_restage",
            detail="junction_family:hitch_listen_restage",
        )

    # Commitment diverge mislabeled as incomplete_cut must remaster via mix
    # (exec_13167 pre_mix: incomplete_cut_unresolved — assembly_not_rendered…).
    if "assembly_not_rendered_from_current_edl" in low or "air_order generation mismatch" in low:
        return HealRoute(
            family="assembly_not_rendered_from_current_edl",
            from_stage="mix",
            action="clear_mix_junction",
            detail="assembly_not_rendered — remaster mix (not junction incomplete-cut)",
        )

    # Paperwork-only claim inventory (exec_023) — not the incomplete-cut ladder.
    if (
        "junction_claim_inventory_stale" in low
        or "claimed_repairs_missing_from_edl" in low
        or "seam_autopsy_claim_inventory" in low
    ):
        return HealRoute(
            family="junction_claim_inventory_stale",
            from_stage="mix",
            action="claim_reconcile",
            detail="claim inventory stale — reconcile applied stamps (not junction ladder)",
        )

    if (
        "incomplete_cut_unresolved" in low
        or "critical_incomplete_cut" in low
        or "seam_autopsy_blocking" in low
        or (
            "publishability blocked" in low
            and "pre_mix" in low
            and (
                "incomplete_cut" in low
                or "critical_residuals" in low
                or "on_a_roll" in low
                or "seam_autopsy" in low
            )
            and "claimed_repairs_missing_from_edl" not in low
            and "junction_claim_inventory_stale" not in low
        )
        or (
            stage_l in {"mix", "junction_snip_qa", "master_finalize"}
            and "critical_residuals" in low
            and "on_a_roll" in low
        )
    ):
        return HealRoute(
            family=FAMILY_JUNCTION,
            from_stage="junction_snip_qa",
            action="junction_ladder",
            detail="incomplete_cut_unresolved — junction before mix",
        )

    fuse_named = (
        "fuse_oscillation" in low
        or "connector_fuse_oscillation" in low
        or (
            "oscillation_halt" in low
            and ("fuse" in low or "connector_fuse" in low)
            and "junction" not in low
        )
    )
    if fuse_named:
        from interview_mux.stage_completion import fuse_oscillation_heal_resume_stage

        pin = fuse_oscillation_heal_resume_stage(ctx, error=err, stage=stage)
        return HealRoute(
            family=FAMILY_JUNCTION,
            from_stage=pin,
            action="fuse_residual",
            detail="fuse_oscillation — pin fuse writer, never edl",
        )

    if (
        "junction_remaster_budget" in low
        or "junction_oscillation" in low
        or "junction_budget_exhaust" in low
        or "oscillation_halt" in low
    ):
        return HealRoute(
            family=FAMILY_JUNCTION,
            from_stage="junction_snip_qa",
            action="resume_junction",
            detail="junction_family:remaster_oscillation",
        )

    if (
        "selection_edl_order_drift" in low
        or "speech clip order diverges" in low
        or "ordered_segment_ids drifted" in low
        or "speech clips do not match" in low
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


# --- subtraction shim (p3-subtract batch 1) ---------------------------------
# Route application deleted; contract `requires` edges decide the resume point.
def apply_heal_route(*_args, **_kwargs):
    raise NotImplementedError(
        "apply_heal_route removed by p3-subtract; see subtraction-holes.md"
    )
