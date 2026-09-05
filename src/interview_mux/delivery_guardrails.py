"""Delivery-phase guardrails — seed completeness, Phase A–E, wasted-work ledger.

G1–G10 / C1–C3 / E1 / D1–D2 live here so schedule, dispatch, and commit share
one predicate. See docs/cross-cutting/delivery-phases.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.v2.config import DELIVERY_ORDER, SHIP_AFTER_MASTER

CHECKPOINT_REL = "operator/delivery_checkpoint.json"
WASTED_WORK_REL = "operator/wasted_work.json"
LISTEN_DELIGHT_WAIVER_REL = "operator/escalations/listen_delight_audit.json"

# Phase A = DELIVERY_ORDER prefix through listen_delight_audit (§5.6).
PHASE_A_END = "listen_delight_audit"
PHASE_A_STAGES: tuple[str, ...] = tuple(
    DELIVERY_ORDER[: DELIVERY_ORDER.index(PHASE_A_END) + 1]
)
PHASE_B_STAGES: frozenset[str] = frozenset({"music_palette_compose", "sfx_prompt_craft"})
PHASE_C_STAGES: frozenset[str] = frozenset({"mmaudio_sfx"})
MUSIC_REQUIRES_ASSEMBLY: frozenset[str] = frozenset(
    {"music_palette_compose", "sfx_prompt_craft", "mmaudio_sfx"}
)
MUSIC_BEFORE_MIX: tuple[str, ...] = (
    "music_palette_compose",
    "sfx_prompt_craft",
    "mmaudio_sfx",
)
MIX_EPOCH_CONSUMERS: frozenset[str] = frozenset(
    {"mix", "junction_snip_qa", "master_finalize", *SHIP_AFTER_MASTER}
)
G3_RECONCILE_CHAIN: tuple[str, ...] = (
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
)
# Consumers that must not run while G1 VO is still missing (vo_synthesize stays allowed).
G1_CONSUMERS: frozenset[str] = frozenset(
    {
        "edl_narrative_audit",
        "edl",
        "assembly_preview",
        "listen_delight_audit",
        *MUSIC_REQUIRES_ASSEMBLY,
        "mix",
        "junction_snip_qa",
        "master_finalize",
        *SHIP_AFTER_MASTER,
    }
)
HEAL_ONLY_PRODUCERS: frozenset[str] = frozenset(
    {
        "nugget_layup_compose",
        "vo_line_adjudicate",
        "gap_framing_recompose",
        "gap_framing_compose",
    }
)
STALE_PREFLIGHT_CONSUMERS: frozenset[str] = frozenset(
    {
        "mmaudio_sfx",
        "vo_synthesize",
        "mix",
        "junction_snip_qa",
        "master_finalize",
        "edl",
        "edl_narrative_audit",
        "assembly_preview",
    }
)
# Consumers that require a fresh transitions / gap_report doc (producer pin on stale).
_TRANSITIONS_STALE_CONSUMERS: frozenset[str] = frozenset(
    {
        "vo_synthesize",
        "edl",
        "edl_narrative_audit",
        "assembly_preview",
    }
)
EXPENSIVE_STAGES: frozenset[str] = frozenset(
    {"mmaudio_sfx", "vo_synthesize", "mix", "master_finalize", "transcribe", "audio_preclean"}
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_stage_complete(ctx: RunContext, stage: str) -> bool:
    """G1: is_done ∧ outputs present ∧ no artifact incompleteness."""
    if not ctx.is_done(stage):
        return False
    try:
        from interview_mux.homunculus.agenda import stage_outputs_present

        if not stage_outputs_present(ctx, stage):
            return False
    except Exception:
        return False
    try:
        from interview_mux.stage_completion import stage_artifact_incompleteness

        return stage_artifact_incompleteness(ctx, stage) is None
    except Exception:
        return False


def assembly_wav_present(ctx: RunContext) -> bool:
    return ctx.artifact_exists("master/assembly.wav") or ctx.artifact_exists(
        "master/assembly_preview.wav"
    )


def listen_delight_waived_unattended(ctx: RunContext) -> bool:
    if not ctx.artifact_exists(LISTEN_DELIGHT_WAIVER_REL):
        return False
    try:
        doc = ctx.read_json(LISTEN_DELIGHT_WAIVER_REL)
    except Exception:
        return False
    if not isinstance(doc, dict):
        return False
    return str(doc.get("status") or "") == "waived_unattended"


def ensure_listen_delight_waiver_unattended(ctx: RunContext) -> bool:
    """Automation driver: write waived_unattended after an audit artifact exists but is not complete."""
    from interview_mux.automation_run import automation_driver_run

    if listen_delight_waived_unattended(ctx):
        return True
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    except Exception:
        meta = {}
    if not automation_driver_run(meta if isinstance(meta, dict) else None):
        return False
    if seed_stage_complete(ctx, "listen_delight_audit"):
        return False
    if not ctx.artifact_exists("mastering/listen_delight_audit.json"):
        return False
    payload = {
        "stage": "listen_delight_audit",
        "status": "waived_unattended",
        "reason": "full-auto Phase B/C may proceed after audit attempt (aspiration floors)",
        "at": _utc_now(),
    }
    ctx.write_json(LISTEN_DELIGHT_WAIVER_REL, payload, skip_handoff=True)
    return True


def _g1_open(ctx: RunContext) -> list[str]:
    try:
        from interview_mux.gates import check_g1_vo

        return list(check_g1_vo(ctx) or [])
    except Exception:
        return []


def _layup_escalation_blocking(ctx: RunContext) -> bool:
    rel = "operator/escalations/nugget_layup_compose.json"
    if not ctx.artifact_exists(rel):
        return False
    try:
        doc = ctx.read_json(rel)
    except Exception:
        return False
    if not isinstance(doc, dict):
        return False
    status = str(doc.get("status") or "").lower()
    return status in {"open", "blocking", "needs_operator"}


def delivery_stable_for_music(ctx: RunContext) -> tuple[bool, str]:
    """G5: Phase C music block may start only when this returns (True, '')."""
    if not seed_stage_complete(ctx, "nugget_layup_compose"):
        return False, "layup_incomplete"
    if _g1_open(ctx):
        return False, "g1_open"
    if not seed_stage_complete(ctx, "vo_line_adjudicate"):
        if not ctx.is_done("vo_line_adjudicate") and not ctx.artifact_exists(
            "mastering/vo_line_adjudication.json"
        ):
            return False, "vo_adjudicate_incomplete"
        if not ctx.is_done("vo_line_adjudicate"):
            return False, "vo_adjudicate_incomplete"
    if not seed_stage_complete(ctx, "edl"):
        return False, "edl_incomplete"
    if not seed_stage_complete(ctx, "assembly_preview") and not assembly_wav_present(ctx):
        return False, "assembly_missing"
    delight_ok = seed_stage_complete(ctx, "listen_delight_audit") or listen_delight_waived_unattended(
        ctx
    )
    if not delight_ok:
        if ensure_listen_delight_waiver_unattended(ctx):
            delight_ok = True
    if not delight_ok:
        return False, "listen_delight_incomplete"
    stale = upstream_stale_blockers(ctx, "mmaudio_sfx")
    if stale:
        return False, f"stale_upstream:{stale[0]}"
    if _layup_escalation_blocking(ctx):
        return False, "layup_escalation_blocking"
    epoch = read_delivery_epoch(ctx)
    if not read_checkpoint(ctx) and not epoch.get("phase_a_sealed_at"):
        return False, "phase_a_unsealed"
    return True, ""


def phase_a_sealed(ctx: RunContext) -> bool:
    """True when Phase A checkpoint or delivery_epoch seal exists."""
    if read_checkpoint(ctx):
        return True
    return bool(read_delivery_epoch(ctx).get("phase_a_sealed_at"))


def music_epoch_complete(ctx: RunContext) -> bool:
    """Canonical predicate: Phase A stable + music chain sealed + SDP WAV parity."""
    stable, _ = delivery_stable_for_music(ctx)
    if not stable:
        return False
    for sid in MUSIC_BEFORE_MIX:
        if not seed_stage_complete(ctx, sid):
            return False
    try:
        from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

        if missing_sdp_asset_wavs(ctx):
            return False
    except Exception:
        return False
    return True


def mix_epoch_block(ctx: RunContext) -> str | None:
    """B3: mix/master/ship wait until music_epoch_complete (no hollow QA bypass)."""
    epoch = read_delivery_epoch(ctx)
    if epoch.get("music_complete_at") and music_epoch_complete(ctx):
        return None
    if music_epoch_complete(ctx):
        stamp_delivery_epoch(ctx, music_complete_at=_utc_now())
        return None
    stable, _ = delivery_stable_for_music(ctx)
    if not stable and not phase_a_sealed(ctx):
        return None
    try:
        from interview_mux.homunculus.agenda import assembly_stale_versus_edl

        if assembly_stale_versus_edl(ctx):
            return "assembly_stale_versus_edl"
    except Exception:
        pass
    return "music_incomplete"


# Stability-block tokens that are NOT pipeline stages. Seed-order heal must
# resolve these before --from-stage / execute, or the runner raises
# Unknown from_stage (forensics: g1_vo_open suicide loop).
VO_SYNTH_SEED_SENTINELS: dict[str, str] = {
    "g1_vo_open": "vo_line_adjudicate",
    "transitions_stale_from_layup": "transitions",
    "gap_report_stale_from_layup": "nugget_layup_compose",
    "sound_design_plan_stale": "sound_design_plan",
}


def resolve_vo_synth_seed_resume(block: str | None) -> str | None:
    """Map vo_synthesize stability tokens to a real ANALYSIS/DELIVERY stage id."""
    token = str(block or "").strip()
    if not token:
        return None
    return VO_SYNTH_SEED_SENTINELS.get(token, token)


def vo_synthesize_stability_block(ctx: RunContext) -> str | None:
    """G8: Chatterbox batch waits for layup/transitions stability and closed G1.

    Returns a blocker token (may be a sentinel such as ``g1_vo_open``). Callers
    that need ``--from-stage`` must run :func:`resolve_vo_synth_seed_resume`.
    """
    if _g1_open(ctx):
        return "g1_vo_open"
    if _layup_escalation_blocking(ctx):
        return "nugget_layup_compose"
    if not seed_stage_complete(ctx, "nugget_layup_compose") and not (
        ctx.is_done("nugget_layup_compose")
        and ctx.artifact_exists("mastering/nugget_layup_plan.json")
    ):
        if not ctx.artifact_exists("mastering/nugget_layup_plan.json"):
            return "nugget_layup_compose"
    if not ctx.artifact_exists("master/transitions.json"):
        return "transitions"
    if not seed_stage_complete(ctx, "transitions"):
        return "transitions"
    try:
        trans = ctx.read_json("master/transitions.json")
        meta = trans.get("_meta") if isinstance(trans, dict) else {}
        reason = str((meta or {}).get("stale_reason") or "")
        if "invalidated_by:nugget_layup_compose" in reason:
            return "transitions_stale_from_layup"
    except Exception:
        pass
    try:
        if ctx.artifact_exists("understanding/gap_report.json"):
            gap = ctx.read_json("understanding/gap_report.json")
            meta = gap.get("_meta") if isinstance(gap, dict) else {}
            reason = str((meta or {}).get("stale_reason") or "")
            if "invalidated_by:nugget_layup_compose" in reason:
                return "gap_report_stale_from_layup"
    except Exception:
        pass
    if ctx.artifact_exists("understanding/sound_design_plan.json"):
        try:
            sdp = ctx.read_json("understanding/sound_design_plan.json")
            meta = sdp.get("_meta") if isinstance(sdp, dict) else {}
            if (meta or {}).get("stale"):
                return "sound_design_plan_stale"
        except Exception:
            pass
    return None


def upstream_stale_blockers(ctx: RunContext, stage: str) -> list[str]:
    """G9 / C3: stale upstream artifacts that must block expensive consumers."""
    blockers: list[str] = []
    if stage not in STALE_PREFLIGHT_CONSUMERS and stage not in MUSIC_REQUIRES_ASSEMBLY:
        return blockers

    def _stale(rel: str) -> bool:
        if not ctx.artifact_exists(rel):
            return False
        try:
            doc = ctx.read_json(rel)
        except Exception:
            return False
        if not isinstance(doc, dict):
            return False
        meta = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else {}
        return bool(meta.get("stale"))

    if stage in {"mmaudio_sfx", "mix", "junction_snip_qa", "master_finalize"} | MUSIC_REQUIRES_ASSEMBLY:
        if _stale("understanding/sound_design_plan.json"):
            blockers.append("sound_design_plan")
        try:
            from interview_mux.homunculus.agenda import assembly_stale_versus_edl

            if assembly_stale_versus_edl(ctx) and stage in {
                "mix",
                "junction_snip_qa",
                "master_finalize",
                "mmaudio_sfx",
            }:
                blockers.append("assembly_stale_versus_edl")
        except Exception:
            pass
    if stage in _TRANSITIONS_STALE_CONSUMERS:
        if _stale("master/transitions.json"):
            blockers.append("transitions")
        if _stale("understanding/gap_report.json"):
            blockers.append("gap_report")
    return blockers


def current_delivery_phase(ctx: RunContext) -> str:
    """A|B|C|D|E from checkpoint + remaining work."""
    if ctx.artifact_exists("master/master.wav") and ctx.is_done("master_finalize"):
        return "E"
    ok, _ = delivery_stable_for_music(ctx)
    if ok or read_checkpoint(ctx):
        if seed_stage_complete(ctx, "mmaudio_sfx") or (
            ctx.artifact_exists("sound_design/mmaudio_qa.json")
            and assembly_wav_present(ctx)
        ):
            if ctx.is_done("mix") or ctx.artifact_exists("master/assembly.wav"):
                return "D"
            return "C"
        if seed_stage_complete(ctx, "sfx_prompt_craft") or seed_stage_complete(
            ctx, "music_palette_compose"
        ):
            return "C"
        return "B"
    return "A"


def _music_defer_log_allowed(ctx: RunContext, stage: str, reason: str) -> bool:
    """Cap repetitive music_deferred ledger spam per stage/reason (R1d)."""
    key = f"{stage}:{reason}"
    try:
        if not ctx.artifact_exists("operator/wasted_work.json"):
            return True
        doc = ctx.read_json("operator/wasted_work.json")
        events = doc.get("events") if isinstance(doc, dict) else []
        if not isinstance(events, list):
            return True
        count = 0
        for row in events:
            if not isinstance(row, dict):
                continue
            if row.get("event") != "music_deferred":
                continue
            detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
            detail_reason = str(detail.get("reason") or "")
            if str(row.get("stage") or "") == stage and detail_reason == reason:
                count += 1
        return count < 5
    except Exception:
        return True


def filter_delivery_candidates(ctx: RunContext, remaining: list[str]) -> list[str]:
    """E1 + G2 + G5 + G8: drop stages the conductor must not enqueue yet."""
    if not remaining:
        return remaining
    g1_missing = _g1_open(ctx)
    vo_block = vo_synthesize_stability_block(ctx)
    stable, stable_reason = delivery_stable_for_music(ctx)
    if not stable:
        ensure_listen_delight_waiver_unattended(ctx)
        stable, stable_reason = delivery_stable_for_music(ctx)
    sealed = phase_a_sealed(ctx)
    ship_ready, ship_reason = ship_path_ready(ctx)
    out: list[str] = []
    deferred: list[str] = []
    for sid in remaining:
        if ship_ready and sid == "junction_snip_qa":
            record_wasted_work(
                ctx,
                event="avoided_junction_remaster",
                stage=sid,
                detail={"reason": ship_reason or "ship_path_ready"},
            )
            deferred.append(sid)
            continue
        if ship_ready and sid in {"master_finalize", *SHIP_AFTER_MASTER}:
            out.append(sid)
            continue
        if g1_missing and sid in G1_CONSUMERS:
            deferred.append(sid)
            continue
        if sid == "vo_synthesize" and vo_block:
            deferred.append(sid)
            continue
        if sid in MUSIC_REQUIRES_ASSEMBLY and not assembly_wav_present(ctx):
            reason = "assembly_missing"
            if _music_defer_log_allowed(ctx, sid, reason):
                record_wasted_work(
                    ctx,
                    event="music_deferred",
                    stage=sid,
                    detail={"reason": reason},
                )
            deferred.append(sid)
            continue
        if sid in SHIP_AFTER_MASTER and not ctx.artifact_exists("master/master.wav"):
            deferred.append(sid)
            continue
        if sid in (*PHASE_B_STAGES, *PHASE_C_STAGES, "mix", "junction_snip_qa", "master_finalize") or sid in SHIP_AFTER_MASTER:
            if not sealed:
                if sid in MUSIC_REQUIRES_ASSEMBLY:
                    reason = stable_reason or "phase_a_unsealed"
                    if _music_defer_log_allowed(ctx, sid, reason):
                        record_wasted_work(
                            ctx,
                            event="music_deferred",
                            stage=sid,
                            detail={"reason": reason},
                        )
                deferred.append(sid)
                continue
        if sid in MIX_EPOCH_CONSUMERS:
            if not music_epoch_complete(ctx):
                mix_b = mix_epoch_block(ctx) or "music_incomplete"
                if _music_defer_log_allowed(ctx, sid, mix_b):
                    record_wasted_work(
                        ctx,
                        event="music_deferred",
                        stage=sid,
                        detail={"reason": mix_b, "predicate": "music_epoch_complete"},
                    )
                deferred.append(sid)
                continue
        if sid in STALE_PREFLIGHT_CONSUMERS:
            stale = upstream_stale_blockers(ctx, sid)
            if stale:
                deferred.append(sid)
                continue
        out.append(sid)
    if deferred and not out:
        # Keep Phase A producers so the walk has somewhere to pin.
        for sid in remaining:
            if sid in PHASE_A_STAGES and sid not in G1_CONSUMERS:
                out.append(sid)
            elif g1_missing and sid in {"vo_line_adjudicate", "vo_synthesize", "sound_design_vo_finalize"}:
                if sid == "vo_synthesize" and vo_block:
                    continue
                out.append(sid)
        if not out:
            for sid in remaining:
                if sid in PHASE_A_STAGES:
                    out.append(sid)
                    break
    return out


def reconcile_delivery_batch(ctx: RunContext) -> list[str]:
    """G3: unmark hollow producers + reconcile .stage_done at every delivery batch start."""
    try:
        from interview_mux.execution_contract import reconcile_execution_contract

        reconcile_execution_contract(ctx, reason="delivery_batch")
    except Exception:
        pass
    cleared: list[str] = []
    try:
        from interview_mux.homunculus.agenda import unmark_hollow_delivery_producers

        cleared.extend(unmark_hollow_delivery_producers(ctx, G3_RECONCILE_CHAIN))
    except Exception:
        pass
    try:
        from interview_mux.stage_completion import reconcile_stage_done_marker

        for sid in G3_RECONCILE_CHAIN:
            if ctx.is_done(sid) and not seed_stage_complete(ctx, sid):
                if not reconcile_stage_done_marker(ctx, sid):
                    cleared.append(sid)
    except Exception:
        pass
    if cleared:
        ctx.log(
            "delivery reconcile cleared hollow: " + ", ".join(dict.fromkeys(cleared)),
            level="warning",
            stage="delivery",
            detail={"cleared": list(dict.fromkeys(cleared))},
        )
    cleared.extend(reconcile_orphan_artifacts(ctx))
    return list(dict.fromkeys(cleared))


def reconcile_orphan_artifacts(ctx: RunContext) -> list[str]:
    """R11c: flag artifacts on disk when producer stage_done is missing."""
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

    orphans: list[str] = []
    for sid, rel in STAGE_ARTIFACT_DISK_PATHS.items():
        if sid not in G3_RECONCILE_CHAIN:
            continue
        if ctx.artifact_exists(rel) and not ctx.is_done(sid):
            orphans.append(sid)
    if orphans:
        record_wasted_work(
            ctx,
            event="orphan_artifact",
            stage="delivery",
            detail={"stages": orphans[:12]},
        )
    return orphans


def music_skip_allowed(ctx: RunContext, stage: str) -> bool:
    """G4: SDP skip only when assembly exists and the stage is actually complete."""
    if stage not in MUSIC_REQUIRES_ASSEMBLY:
        return False
    if not assembly_wav_present(ctx):
        return False
    try:
        from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

        if missing_sdp_asset_wavs(ctx):
            return False
    except Exception:
        return False
    try:
        from interview_mux.homunculus.agenda import stage_outputs_present

        if not stage_outputs_present(ctx, stage):
            return False
    except Exception:
        return False
    return True


def selection_order_fingerprints(ctx: RunContext) -> dict[str, str]:
    out = {"selection": "", "order": ""}
    try:
        from interview_mux.order_hash import get_order_lock, ordered_segment_ids_hash

        lock = get_order_lock(ctx) or {}
        if isinstance(lock, dict):
            out["order"] = str(lock.get("order_hash") or lock.get("hash") or "")
        if not out["order"] and ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            ids = list((sel or {}).get("ordered_segment_ids") or [])
            out["order"] = ordered_segment_ids_hash(ids)
            out["selection"] = out["order"]
    except Exception:
        pass
    if not out["selection"]:
        out["selection"] = out["order"]
    return out


def fingerprints_match_checkpoint(ctx: RunContext) -> bool:
    cp = read_checkpoint(ctx)
    if not cp:
        return False
    live = selection_order_fingerprints(ctx)
    return bool(cp.get("order_fingerprint")) and str(cp.get("order_fingerprint")) == str(
        live.get("order") or ""
    )


def invalidation_is_structural(ctx: RunContext, stage: str) -> bool:
    """C1: heal-only producers keep the post-assembly epoch when fingerprints match."""
    if stage not in HEAL_ONLY_PRODUCERS:
        return True
    if not read_checkpoint(ctx) and not assembly_wav_present(ctx):
        return True
    return not fingerprints_match_checkpoint(ctx)


def finalize_input_producer_pin(ctx: RunContext, *, message: str = "") -> str:
    """Map master_finalize blockers to a single producer stage (never mix alone).

    Missing ledger → ``edl`` (ledger writer). Missing seam_autopsy →
    ``junction_snip_qa`` when assembly exists, else ``edl``. Missing EDL → ``edl``.
    """
    low = str(message or "").lower()
    if not ctx.artifact_exists("master/edl.json"):
        try:
            from interview_mux.delivery_recovery import restore_master_artifact

            restore_master_artifact(ctx, "master/edl.json", min_bytes=32)
        except Exception:
            pass
    if not ctx.artifact_exists("master/edl.json") or "edl.json missing" in low:
        return "edl"
    if not ctx.artifact_exists("master/assembly_ledger.json") or (
        "assembly_ledger" in low and "missing" in low
    ):
        return "edl"
    if "assembly_ledger" in low and ("naked" in low or "incomplete" in low):
        return "edl"
    if not ctx.artifact_exists("master/seam_autopsy.json") or (
        "seam_autopsy" in low and "missing" in low
    ):
        if ctx.artifact_exists("master/assembly.wav"):
            return "junction_snip_qa"
        return "edl"
    if "render_ledger" in low and not ctx.artifact_exists("master/render_ledger.json"):
        if ctx.artifact_exists("master/assembly.wav"):
            return "junction_snip_qa"
        return "mix"
    return "master_finalize"


def resolve_assembly_stale_resume(ctx: RunContext) -> str:
    """Pin for assembly-vs-EDL drift: edl if EDL missing/stale, else remaster mix/junction.

    Never absolute ``edl`` when live EDL is healthy — that was the wrong pin that
    mirrored the stale-transitions/EDL empty-heal class.
    """
    if not ctx.artifact_exists("master/edl.json"):
        return "edl"
    try:
        edl = ctx.read_json("master/edl.json")
        meta = edl.get("_meta") if isinstance(edl, dict) else {}
        if isinstance(meta, dict) and meta.get("stale"):
            return "edl"
    except Exception:
        return "edl"
    try:
        from interview_mux.heal_routing import mix_assembly_seated

        if mix_assembly_seated(ctx):
            return "junction_snip_qa"
    except Exception:
        pass
    return "mix"


def resolve_gap_report_stale_producer(ctx: RunContext) -> str:
    """Map stale gap_report to writer by invalidator; default layup (don't skip real rewrites)."""
    reason = ""
    try:
        if ctx.artifact_exists("understanding/gap_report.json"):
            gap = ctx.read_json("understanding/gap_report.json")
            meta = gap.get("_meta") if isinstance(gap, dict) else {}
            reason = str((meta or {}).get("stale_reason") or "").lower()
    except Exception:
        reason = ""
    if "nugget_layup" in reason:
        return "nugget_layup_compose"
    if "gap_framing_recompose" in reason:
        return "gap_framing_recompose"
    if "gap_framing_compose" in reason:
        return "gap_framing_compose"
    if "optimal_questions" in reason:
        return "optimal_questions"
    return "nugget_layup_compose"


def may_rewind_to_vo_synthesize(ctx: RunContext) -> bool:
    """Monotonic delivery: allow vo_synthesize rewind for G1/script/transition holes.

    Assembly + G1 green + deferred transition pairs alone must not unmark
    vo_synthesize. Script↔WAV mismatch (gap or spoken transition) and missing
    seated pickups still may rewind so master finalize can reseat fresh audio.
    """
    try:
        from interview_mux.gates import check_g1_vo, g1_vo_was_skipped_optional

        if g1_vo_was_skipped_optional(ctx):
            return False
        if check_g1_vo(ctx):
            return True
    except Exception:
        return True
    try:
        from interview_mux.vo_contract import seated_vo_missing_ids

        if seated_vo_missing_ids(ctx):
            return True
    except Exception:
        pass
    try:
        from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

        if compact_vo_coverage_stale_or_missing(ctx):
            return True
    except Exception:
        pass
    try:
        from interview_mux.transition_vo import current_transition_pairs_missing

        missing = current_transition_pairs_missing(ctx)
        if not missing:
            return False
        # Deferred-only holes after pair freeze stay mix last-chance.
        try:
            from interview_mux.transition_vo import (
                frozen_transition_pair_keys,
                read_transitions_pair_freeze,
            )

            if read_transitions_pair_freeze(ctx):
                frozen = frozen_transition_pair_keys(ctx)
                if frozen and all(m not in frozen for m in missing):
                    return False
        except Exception:
            pass
        return True
    except Exception:
        pass
    return False


def premature_cap_hard_pin(
    ctx: RunContext | None, resume: str, *, message: str = ""
) -> str:
    """G7: stay on the incomplete producer; never advance to a consumer."""
    if ctx is None:
        return resume
    # Finalize-class holes: pin the producer, never spin on mix/finalize alone.
    if resume == "master_finalize":
        try:
            pinned = finalize_input_producer_pin(ctx, message=message)
            if pinned and pinned != "master_finalize":
                return pinned
        except Exception:
            pass
    # Selection leads EDL. Pinning an incomplete consumer (edl/mix) while
    # master/selection.json is absent is a heal-spin, not a producer pin.
    if not ctx.artifact_exists("master/selection.json"):
        try:
            from interview_mux.llm_flow_hardening import _earliest_incomplete_seed_stage

            target = resume if resume in DELIVERY_ORDER else "edl"
            earliest = _earliest_incomplete_seed_stage(ctx, target)
            if earliest:
                return earliest
        except Exception:
            pass
        return "topic_coverage_audit"
    if resume in MIX_EPOCH_CONSUMERS and not music_epoch_complete(ctx):
        for sid in MUSIC_BEFORE_MIX:
            if not seed_stage_complete(ctx, sid):
                return sid
        try:
            from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

            if missing_sdp_asset_wavs(ctx):
                return "mmaudio_sfx"
        except Exception:
            pass
        return "mmaudio_sfx"
    if resume == "vo_synthesize" and _g1_open(ctx):
        if not seed_stage_complete(ctx, "nugget_layup_compose"):
            return "nugget_layup_compose"
        block = vo_synthesize_stability_block(ctx)
        if block == "nugget_layup_compose":
            return "nugget_layup_compose"
        # G1 open with layup present — pin adjudicate (never fake stage g1_vo_open).
        return resolve_vo_synth_seed_resume(block) or "vo_line_adjudicate"
    try:
        from interview_mux.llm_flow_hardening import _earliest_incomplete_seed_stage

        target = resume if resume in DELIVERY_ORDER else "edl"
        earliest = _earliest_incomplete_seed_stage(ctx, target)
        if earliest:
            return earliest
    except Exception:
        pass
    if resume and not seed_stage_complete(ctx, resume):
        return resume
    for sid in PHASE_A_STAGES:
        if not seed_stage_complete(ctx, sid):
            return sid
    return resume


def safe_mix_resume_stage(ctx: RunContext) -> str:
    """Return mix only when music epoch complete; else earliest music producer."""
    if music_epoch_complete(ctx):
        return "mix"
    block = mix_epoch_block(ctx)
    if block:
        for sid in MUSIC_BEFORE_MIX:
            if not seed_stage_complete(ctx, sid):
                return sid
        # Seed markers present but SDP still lacks WAVs — regenerate assets,
        # do not bounce mix ↔ music_palette_compose forever.
        try:
            from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

            if missing_sdp_asset_wavs(ctx):
                return "mmaudio_sfx"
        except Exception:
            pass
    try:
        from interview_mux.delivery_recovery import resume_theme_generation

        return resume_theme_generation(ctx)
    except Exception:
        return "music_palette_compose"


def read_checkpoint(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(CHECKPOINT_REL):
        return None
    try:
        data = ctx.read_json(CHECKPOINT_REL)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def seal_phase_a_if_stable(ctx: RunContext) -> dict[str, Any] | None:
    """Write operator/delivery_checkpoint.json when G5 stability predicates pass."""
    existing = read_checkpoint(ctx)
    ok, reason = delivery_stable_for_music(ctx)
    # Allow sealing when stable except the seal itself is the only missing piece.
    if not ok and reason != "phase_a_unsealed":
        return existing
    if not ok and reason == "phase_a_unsealed":
        # Re-check stability without seal requirement for the write path.
        if not seed_stage_complete(ctx, "nugget_layup_compose"):
            return existing
        if _g1_open(ctx):
            return existing
        if not seed_stage_complete(ctx, "vo_line_adjudicate"):
            if not ctx.is_done("vo_line_adjudicate") and not ctx.artifact_exists(
                "mastering/vo_line_adjudication.json"
            ):
                return existing
            if not ctx.is_done("vo_line_adjudicate"):
                return existing
        if not seed_stage_complete(ctx, "edl"):
            return existing
        if not seed_stage_complete(ctx, "assembly_preview") and not assembly_wav_present(ctx):
            return existing
        delight_ok = seed_stage_complete(ctx, "listen_delight_audit") or listen_delight_waived_unattended(
            ctx
        )
        if not delight_ok:
            if ensure_listen_delight_waiver_unattended(ctx):
                delight_ok = True
        if not delight_ok:
            return existing
        if upstream_stale_blockers(ctx, "mmaudio_sfx"):
            return existing
        if _layup_escalation_blocking(ctx):
            return existing
    fps = selection_order_fingerprints(ctx)
    g1_ids: list[str] = []
    try:
        from interview_mux.gates import check_g1_vo

        missing = check_g1_vo(ctx)
        if missing:
            return existing
        if ctx.artifact_exists("understanding/gap_report.json"):
            from interview_mux.air_script import seated_vo_line_ids
            from interview_mux.mastering_plan_loader import load_plan_raw

            gap = ctx.read_json("understanding/gap_report.json")
            plan = load_plan_raw(ctx) if ctx.artifact_exists("mastering/mastering_plan.json") else {}
            seated = seated_vo_line_ids(plan)
            for row in (gap.get("interviewer_lines") or []):
                if not isinstance(row, dict):
                    continue
                lid = str(row.get("line_id") or "")
                if not lid or lid not in seated:
                    continue
                if str(row.get("delivery") or "").lower() == "synthesize":
                    g1_ids.append(lid)
            g1_ids = sorted(set(g1_ids))
    except Exception:
        pass
    assembly = "master/assembly_preview.wav" if ctx.artifact_exists(
        "master/assembly_preview.wav"
    ) else ("master/assembly.wav" if ctx.artifact_exists("master/assembly.wav") else "")
    row = {
        "phase": "A_sealed",
        "sealed_at": (existing or {}).get("sealed_at") or _utc_now(),
        "selection_fingerprint": fps.get("selection") or "",
        "order_fingerprint": fps.get("order") or "",
        "g1_line_ids": g1_ids,
        "assembly_path": assembly,
        "listen_delight_waiver": listen_delight_waived_unattended(ctx),
        "reason": reason,
    }
    ctx.write_json(CHECKPOINT_REL, row, skip_handoff=True)
    stamp_delivery_epoch(ctx, phase_a_sealed_at=row["sealed_at"])
    record_wasted_work(ctx, event="phase_seal", stage="listen_delight_audit", detail=row)
    return row


def delivery_epoch_locked(ctx: RunContext) -> bool:
    epoch = read_delivery_epoch(ctx)
    if epoch.get("unlocked_at"):
        return False
    if epoch.get("locked"):
        return True
    return bool(epoch.get("phase_a_sealed_at"))


def unlock_delivery_epoch(ctx: RunContext, reason: str) -> dict[str, Any]:
    epoch = read_delivery_epoch(ctx)
    epoch["unlocked_at"] = _utc_now()
    epoch["unlock_reason"] = str(reason or "")[:400]
    epoch["locked"] = False
    epoch["updated_at"] = _utc_now()

    def _mark(meta: dict[str, Any]) -> None:
        meta["delivery_epoch"] = epoch

    ctx.mutate_run_meta(_mark)
    return epoch


def read_delivery_epoch(ctx: RunContext) -> dict[str, Any]:
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        return {}
    raw = meta.get("delivery_epoch")
    return dict(raw) if isinstance(raw, dict) else {}


def stamp_delivery_epoch(ctx: RunContext, **fields: Any) -> dict[str, Any]:
    epoch = read_delivery_epoch(ctx)
    for key, val in fields.items():
        if val is not None and not epoch.get(key):
            epoch[key] = val
        elif val is not None and key.endswith("_at"):
            epoch[key] = epoch.get(key) or val
        elif val is not None:
            epoch[key] = val
    if fields.get("structural_invalidation"):
        epoch["structural_bump_at"] = _utc_now()
    if epoch.get("phase_a_sealed_at") and not epoch.get("unlocked_at"):
        epoch["locked"] = True
    epoch["updated_at"] = _utc_now()
    if read_checkpoint(ctx):
        epoch["last_stable_checkpoint"] = CHECKPOINT_REL
    elif not epoch.get("last_stable_checkpoint"):
        epoch.pop("last_stable_checkpoint", None)

    def _mark(meta: dict[str, Any]) -> None:
        meta["delivery_epoch"] = epoch

    try:
        ctx.mutate_run_meta(_mark)
    except Exception:
        pass
    return epoch


def record_wasted_work(
    ctx: RunContext,
    *,
    event: str,
    stage: str = "",
    detail: dict[str, Any] | None = None,
) -> None:
    """D1: append operator/wasted_work.json event (expensive_start/orphan/avoided/…)."""
    doc: dict[str, Any] = {"version": 1, "events": []}
    if ctx.artifact_exists(WASTED_WORK_REL):
        try:
            raw = ctx.read_json(WASTED_WORK_REL)
            if isinstance(raw, dict):
                doc = raw
        except Exception:
            pass
    events = list(doc.get("events") or [])
    if event == "music_deferred" and detail:
        reason = str((detail or {}).get("reason") or "")
        dupes = sum(
            1
            for row in events
            if isinstance(row, dict)
            and row.get("event") == "music_deferred"
            and str(row.get("stage") or "") == stage
            and str((row.get("detail") or {}).get("reason") or "") == reason
        )
        if dupes >= 5:
            return
    events.append(
        {
            "at": _utc_now(),
            "event": event,
            "stage": stage,
            "detail": detail or {},
        }
    )
    doc["version"] = 1
    doc["updated_at"] = _utc_now()
    doc["events"] = events[-200:]
    try:
        ctx.write_json(WASTED_WORK_REL, doc, skip_handoff=True)
    except Exception:
        pass
    if event == "orphan":

        def _mark(meta: dict[str, Any]) -> None:
            meta.setdefault("delivery_epoch", {})
            if isinstance(meta["delivery_epoch"], dict):
                meta["delivery_epoch"]["orphaned_spend"] = True

        try:
            ctx.mutate_run_meta(_mark)
        except Exception:
            pass


def maybe_restore_master_bundle(ctx: RunContext, *, stage: str) -> list[str]:
    """C2: restore archived master bundle when heal-only and fingerprints match."""
    if invalidation_is_structural(ctx, stage):
        return []
    try:
        from interview_mux.delivery_recovery import restore_master_bundle

        restored = restore_master_bundle(ctx)
    except Exception:
        restored = []
    if restored:
        record_wasted_work(
            ctx,
            event="restore_bundle",
            stage=stage,
            detail={"restored": list(restored)[:20]},
        )
    return list(restored or [])


def referenced_musicgen_asset_ids(ctx: RunContext) -> set[str]:
    """E3: theme/SFX slots actually referenced by cues or mix recipe."""
    ids: set[str] = set()
    if ctx.artifact_exists("understanding/sound_design_plan.json"):
        try:
            plan = ctx.read_json("understanding/sound_design_plan.json")
        except Exception:
            plan = {}
        if isinstance(plan, dict):
            flow_plans = plan.get("flow_plans") if isinstance(plan.get("flow_plans"), dict) else {}
            for flow in flow_plans.values():
                if not isinstance(flow, dict):
                    continue
                for cue in flow.get("cues") or []:
                    if isinstance(cue, dict) and cue.get("asset_id"):
                        ids.add(str(cue.get("asset_id")))
    for rel in ("master/mix_recipe.json", "sound_design/mix_recipe.json", "master/edl.json"):
        if not ctx.artifact_exists(rel):
            continue
        try:
            doc = ctx.read_json(rel)
        except Exception:
            continue
        blob = str(doc) if not isinstance(doc, dict) else ""
        if isinstance(doc, dict):
            for key in ("asset_ids", "theme_asset_ids", "sfx_asset_ids"):
                for aid in doc.get(key) or []:
                    ids.add(str(aid))
            for clip in doc.get("clips") or doc.get("entries") or []:
                if isinstance(clip, dict) and clip.get("asset_id"):
                    ids.add(str(clip.get("asset_id")))
        if "show_theme" in blob:
            pass
    return ids


# C1: sources that must not structurally invalidate downstream when fingerprint unchanged.
INVALIDATION_BLAST_RADIUS: dict[str, frozenset[str]] = {
    "junction_snip_qa": frozenset(
        {"mix", "junction_snip_qa", "master_finalize", "master/transitions.json"}
    ),
    "nugget_layup_compose": frozenset(
        {
            "vo_synthesize",
            "edl_narrative_audit",
            "edl",
            "assembly_preview",
            "listen_delight_audit",
        }
    ),
}


def invalidation_allowed_downstream(source: str, target: str) -> bool:
    """Whether ``source`` may clear/invalidate ``target`` when structural."""
    allowed = INVALIDATION_BLAST_RADIUS.get(source)
    if allowed is None:
        return True
    return target in allowed or target.split("/")[0] in {t.split("/")[0] for t in allowed}


def delivery_epoch_matches(ctx: RunContext, epoch_at_start: dict[str, Any] | None) -> bool:
    """D2: expensive stages must not run after a structural epoch bump."""
    if not epoch_at_start:
        return True
    live = read_delivery_epoch(ctx)
    for key in ("phase_a_sealed_at", "music_complete_at", "structural_bump_at"):
        if epoch_at_start.get(key) != live.get(key):
            return False
    return True


def read_delivery_epoch_at_dispatch(ctx: RunContext) -> dict[str, Any]:
    return dict(read_delivery_epoch(ctx))


def ship_path_ready(ctx: RunContext) -> tuple[bool, str]:
    """Late-phase pin: mix sealed, assembly fresh, delight ok, no critical junction residuals."""
    if not ctx.artifact_exists("master/assembly.wav"):
        return False, "assembly_missing"
    try:
        from interview_mux.homunculus.agenda import assembly_stale_versus_edl

        if assembly_stale_versus_edl(ctx):
            return False, "assembly_stale_versus_edl"
    except Exception:
        pass
    if not seed_stage_complete(ctx, "mix"):
        return False, "mix_incomplete"
    delight_ok = seed_stage_complete(ctx, "listen_delight_audit") or listen_delight_waived_unattended(
        ctx
    )
    if not delight_ok:
        return False, "listen_delight_incomplete"
    if ctx.artifact_exists("master/junction_snip_qa.json"):
        try:
            doc = ctx.read_json("master/junction_snip_qa.json")
            if isinstance(doc, dict):
                crit = int(doc.get("critical_residual_count") or doc.get("critical_count") or 0)
                if crit > 0:
                    return False, "critical_junction_residuals"
                residuals = doc.get("residuals") or doc.get("critical_residuals") or []
                if isinstance(residuals, list) and residuals:
                    return False, "junction_residuals"
        except Exception:
            pass
    if ctx.artifact_exists("master/post_master_quality.json"):
        try:
            pmq = ctx.read_json("master/post_master_quality.json")
            if isinstance(pmq, dict) and pmq.get("publish_allowed") is False:
                return False, "pmq_not_publishable"
        except Exception:
            pass
    return True, ""


def prepare_fingerprint_blocks_rerun(ctx: RunContext, stage: str) -> str | None:
    """G10: prepare-phase stages re-run only on ingest/G0/probe change."""
    if stage not in {"audio_preclean", "transcribe", "audio_probe_build", "ingest"}:
        return None
    try:
        from interview_mux.homunculus.agenda import G0_LOCKED_RERUN_STAGES, prepare_outputs_present
        from interview_mux.homunculus.packer import g0_closed

        if stage in G0_LOCKED_RERUN_STAGES and g0_closed(ctx) and prepare_outputs_present(ctx, stage):
            return "g0_locked"
        if stage == "audio_probe_build" and g0_closed(ctx) and prepare_outputs_present(ctx, stage):
            return "g0_locked"
    except Exception:
        pass
    if stage == "audio_preclean" and ctx.artifact_exists("ingest/ingest_checksums.json"):
        try:
            from interview_mux.homunculus.agenda import prepare_outputs_present

            if ctx.is_done("audio_preclean") and prepare_outputs_present(ctx, "audio_preclean"):
                return "ingest_unchanged"
        except Exception:
            pass
    try:
        from interview_mux.homunculus.packer import g0_closed
        from interview_mux.homunculus.agenda import prepare_outputs_present

        if stage == "transcribe" and g0_closed(ctx) and prepare_outputs_present(ctx, "transcribe"):
            return "g0_locked"
    except Exception:
        pass
    return None
