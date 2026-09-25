"""Delivery-phase guardrails — seed completeness, Phase A–E, wasted-work ledger.

G1–G10 / C1–C3 / E1 / D1–D2 live here so schedule, dispatch, and commit share
one predicate. See docs/cross-cutting/delivery-phases.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.v2.config import DELIVERY_ORDER, SHIP_AFTER_MASTER

CHECKPOINT_REL = "operator/delivery_checkpoint.json"
WASTED_WORK_REL = "operator/wasted_work.json"
DELIVERY_RESIDUALS_REL = "operator/delivery_residuals.json"
LISTEN_DELIGHT_WAIVER_REL = "operator/escalations/listen_delight_audit.json"

# Soft seal rewrite: only when markers lag usable artifacts (never hard producer holes).
PHASE_A_MARKER_LAG_REASONS: frozenset[str] = frozenset(
    {
        "edl_incomplete",
        "assembly_missing",
        "listen_delight_incomplete",
    }
)

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
# Execute/dispatch honor this set. Filter also defers SHIP_AFTER_MASTER (HX-1 2A).
MIX_EPOCH_RUN_BLOCK: frozenset[str] = frozenset(
    {"mix", "junction_snip_qa", "master_finalize"}
)
MIX_EPOCH_CONSUMERS: frozenset[str] = frozenset(
    {*MIX_EPOCH_RUN_BLOCK, *SHIP_AFTER_MASTER}
)
G3_RECONCILE_CHAIN: tuple[str, ...] = (
    "nugget_layup_compose",
    "gap_report_sanitize",
    "air_contract_sanitize",
    # TH2: Phase A producers that feed VO/EDL (transitions → SDP → adjudicate).
    "transitions",
    "sound_design_plan",
    "vo_line_adjudicate",
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
    if stage == "mix":
        try:
            from interview_mux.mix_junction_seat import (
                demote_hollow_mix_done,
                mix_is_seed_complete,
            )

            demote_hollow_mix_done(ctx)
            return bool(mix_is_seed_complete(ctx))
        except Exception:
            pass
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


def producer_ready(ctx: RunContext, stage: str) -> bool:
    """Ask/enqueue/seal readiness — seed_stage_complete only (no artifact_exists escape).

    Hollow-pass B+ R4: when a done marker exists, disk-mapped primaries must be
    present (all MUST_PRECEDE / schedule producers — not only VO five).
    Gate marker-only stages are exempt via Done Authority GATE_MARKER_ONLY.
    """
    sid = str(stage or "").strip()
    if not seed_stage_complete(ctx, sid):
        return False
    try:
        if not ctx.is_done(sid):
            return True
    except Exception:
        return True
    try:
        from interview_mux.done_authority import GATE_MARKER_ONLY, primary_disk_present

        if sid in GATE_MARKER_ONLY:
            return True
        if not primary_disk_present(ctx, sid):
            return False
    except Exception:
        return False
    try:
        from interview_mux.stage_completion import stage_artifact_incompleteness

        if stage_artifact_incompleteness(ctx, sid) is not None:
            return False
    except Exception:
        return False
    return True


def edl_ready(ctx: RunContext) -> bool:
    """EDL deliverable ready for consumers — seed_stage_complete only (exec_13165)."""
    return seed_stage_complete(ctx, "edl")


# Consumer → producers that must be seed-complete before the consumer may be asked.
# Sole order exception: junction_recut_precedes_mix (not encoded as mix→junction here).
# EDL consumer gate is separate (EDL_CONSUMERS) — attached-plan WS2.
MUST_PRECEDE: dict[str, tuple[str, ...]] = {
    # Pre-ranking fuse chain (G6 / exec_13174): never resume past unfinished arc/hitch/fuse.
    "chapter_close_hitch": ("narrative_arc_plan",),
    "connector_fuse_pass_pre_ranking": ("narrative_arc_plan", "chapter_close_hitch"),
    "full_master_ranking": ("connector_fuse_pass_pre_ranking",),
    "selection_order_sanitize": (
        "full_master_ranking",
        "connector_fuse_pass_pre_ranking",
    ),
    # Sanitize / seat chain (expanded WS2 — not attached-plan EDL list).
    "air_script_compose": ("selection_order_sanitize", "full_master_ranking"),
    "nugget_layup_compose": ("information_package_plan", "nugget_corpus_mine"),
    "gap_report_sanitize": ("nugget_layup_compose",),
    "refinement_agenda": ("gap_report_sanitize",),
    "gap_framing_recompose": ("gap_report_sanitize",),
    "selection_framing_apply": ("gap_framing_recompose",),
    "air_script_seams": ("selection_framing_apply",),
    "air_contract_sanitize": ("air_script_seams",),
    "transitions": ("air_contract_sanitize", "nugget_layup_compose"),
    "sound_design_plan": ("transitions",),
    # DP-LAYUP-ADJ A: VO seal chain lists upstream producers so leapfrog pins
    # resolve to the earliest hole (not only the immediate predecessor).
    "vo_line_adjudicate": (
        "nugget_layup_compose",
        "transitions",
        "sound_design_plan",
    ),
    "vo_synthesize": (
        "nugget_layup_compose",
        "transitions",
        "sound_design_plan",
        "vo_line_adjudicate",
    ),
    "sound_design_vo_finalize": ("vo_synthesize",),
    "edl_narrative_audit": ("vo_synthesize", "sound_design_vo_finalize"),
    "edl": ("edl_narrative_audit", "vo_synthesize"),
    "assembly_preview": ("edl",),
    "listen_delight_audit": ("edl", "assembly_preview"),
    "music_palette_compose": (
        "edl",
        "listen_delight_audit",
        "nugget_layup_compose",
        "vo_line_adjudicate",
    ),
    "sfx_prompt_craft": ("music_palette_compose", "sound_design_plan"),
    "mmaudio_sfx": ("sfx_prompt_craft",),
    # Always-HAU: beds are not producers of mix — music admit is seated-only
    # via next_delivery_seat / may_admit_music (exec_13170 follow-through).
    "mix": ("edl",),
    "junction_snip_qa": ("edl",),  # mix optional when junction_recut_precedes_mix
    "master_finalize": ("edl",),
}

# Heal Clinic leapfrog B+: single HAU exception table (speech-first mix beds).
# Consumers listed here may skip MUSIC_BEFORE_MIX producers under hold_speech_first_mix.
HAU_SPEECH_FIRST_EXCEPTIONS: frozenset[str] = frozenset({"mix"})

# Stages that must not enqueue while edl is not seed-complete.
EDL_CONSUMERS: frozenset[str] = frozenset(
    {
        "assembly_preview",
        "listen_delight_audit",
        *MUSIC_REQUIRES_ASSEMBLY,
        "mix",
        "junction_snip_qa",
        "master_finalize",
        *SHIP_AFTER_MASTER,
    }
)


def earliest_incomplete_must_precede(ctx: RunContext, consumer: str) -> str:
    """Earliest incomplete producer for a consumer (empty if all ready)."""
    sid = str(consumer or "").strip()
    producers = MUST_PRECEDE.get(sid, ())
    # HAU optional_beds: speech-first mix seats assembly before MusicGen/MMAudio.
    # Skip beds producers so filter([mix]) does not reinject mmaudio thrash.
    if sid in HAU_SPEECH_FIRST_EXCEPTIONS:
        try:
            from interview_mux.mix_junction_seat import hold_speech_first_mix

            if hold_speech_first_mix(ctx, sid):
                bed = set(MUSIC_BEFORE_MIX)
                producers = tuple(p for p in producers if p not in bed)
        except Exception:
            pass
    for prod in producers:
        if not producer_ready(ctx, prod):
            return prod
    return ""


# DP-LAYUP-ADJ: VO seal consumers always clamp; downstream pins clamp only when
# a VO-chain hole is open (never yank music→narrative when VO is already sealed).
VO_ORDER_CLAMP_STAGES: frozenset[str] = frozenset(
    {
        "vo_synthesize",
        "vo_line_adjudicate",
        "sound_design_vo_finalize",
    }
)
VO_CHAIN_DOWNSTREAM_PINS: frozenset[str] = frozenset(
    {
        "edl",
        "edl_narrative_audit",
        "assembly_preview",
        "listen_delight_audit",
        "listen_delight",
        "music_palette_compose",
        "sfx_prompt_craft",
        "mmaudio_sfx",
        "mix",
        "junction_snip_qa",
        "master_finalize",
        "master_transcript_build",
        "episode_cover_generate",
        "podcast_publish",
    }
)


def clamp_resume_through_order(ctx: RunContext, stage: str) -> str:
    """DP-LAYUP-ADJ A + footgun #1: never resume past an incomplete MUST_PRECEDE / G8 hole.

    - VO clamp stages always walk to the earliest VO-chain / G8 hole.
    - Downstream pins (edl/music/mix/ship) clamp **only** when a VO-chain hole is
      open — so music does not get yanked to edl_narrative when VO is sealed.
    """
    sid = str(stage or "").strip()
    if not sid:
        return sid

    # G6: ranking/sanitize must not leapfrog unfinished arc → hitch → pre_ranking.
    # Do not clamp when the pin *is* hitch/pre_ranking (HS-4 oscillation specialty).
    if sid in {"full_master_ranking", "selection_order_sanitize"}:
        hole = earliest_incomplete_must_precede(ctx, sid)
        if hole:
            return hole
        if sid == "selection_order_sanitize":
            hole = earliest_incomplete_must_precede(ctx, "full_master_ranking")
            if hole:
                return hole
            hole = earliest_incomplete_must_precede(ctx, "connector_fuse_pass_pre_ranking")
            if hole:
                return hole

    # High-gap unframed wins over layup→IPP walk for VO pins (exec_13170).
    if sid in VO_ORDER_CLAMP_STAGES:
        try:
            from interview_mux.stage_completion import (
                _high_gap_unframed_incompleteness,
                high_gap_heal_resume_stage,
            )

            if _high_gap_unframed_incompleteness(ctx, "gap_framing_compose"):
                return high_gap_heal_resume_stage(ctx)
        except Exception:
            pass

    def _walk_vo_consumer(start: str) -> str:
        seen: set[str] = set()
        cur = start
        for _ in range(24):
            if not cur or cur in seen:
                break
            seen.add(cur)
            hole = earliest_incomplete_must_precede(ctx, cur)
            if hole:
                cur = hole
                continue
            if cur in VO_ORDER_CLAMP_STAGES:
                try:
                    block = vo_synthesize_stability_block(ctx, allow_rewrite=False)
                except Exception:
                    block = None
                if block:
                    mapped = resolve_vo_synth_seed_resume(block, ctx) or str(block)
                    mapped = str(mapped or "").strip()
                    if mapped and mapped != cur and mapped not in seen:
                        try:
                            from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

                            if mapped in ANALYSIS_ORDER or mapped in DELIVERY_ORDER:
                                cur = mapped
                                continue
                        except Exception:
                            if mapped in {
                                "nugget_layup_compose",
                                "transitions",
                                "sound_design_plan",
                                "vo_line_adjudicate",
                                "vo_synthesize",
                            }:
                                cur = mapped
                                continue
            break
        return cur

    if sid in VO_ORDER_CLAMP_STAGES:
        return _walk_vo_consumer(sid)

    # P3: layup resume must not leapfrog incomplete seed-front (NAP / corpus / IPP).
    if sid == "nugget_layup_compose":
        hole = earliest_incomplete_must_precede(ctx, sid)
        if hole:
            return hole
        # Also refuse when narrative_arc_plan (seed-front) is incomplete even if
        # not listed as a direct MUST_PRECEDE producer of layup.
        try:
            from interview_mux.llm_flow_hardening import _earliest_incomplete_seed_stage

            earliest = _earliest_incomplete_seed_stage(ctx, sid)
            if earliest and earliest != sid:
                return earliest
        except Exception:
            pass
        return sid

    if sid in VO_CHAIN_DOWNSTREAM_PINS:
        # Footgun #1: only MUST_PRECEDE VO-chain holes — not G8 file/stale probes
        # (those would yank music→transitions and reopen premature_cap thrash).
        vo_hole = earliest_incomplete_must_precede(ctx, "vo_synthesize")
        if vo_hole:
            return _walk_vo_consumer("vo_synthesize")
        return sid

    return sid


def _inject_edl_producer(ctx: RunContext, out: list[str]) -> None:
    """Prefer narrative audit then edl when edl is not seed-complete."""
    try:
        from interview_mux.edl_narrative_remutate import narrative_audit_blocks_edl

        need_audit = narrative_audit_blocks_edl(ctx) or not ctx.artifact_exists(
            "master/edl_narrative_audit.json"
        )
        if need_audit and not seed_stage_complete(ctx, "edl_narrative_audit"):
            if "edl_narrative_audit" not in out:
                out.append("edl_narrative_audit")
            return
    except Exception:
        pass
    if "edl" not in out:
        out.append("edl")


def defer_until_producers_ready(
    ctx: RunContext, sid: str, out: list[str], deferred: list[str]
) -> bool:
    """If sid's MUST_PRECEDE producers are incomplete, reinject earliest and defer.

    Returns True when the consumer was deferred (caller should continue).
    """
    sid = str(sid or "").strip()
    if not sid:
        return False
    # EDL consumer gate (structural ordering).
    if sid in EDL_CONSUMERS and not edl_ready(ctx):
        # When G1 is open, do not inject edl into candidates — G1_CONSUMERS defer
        # owns the pin (vo_synthesize / adjudicate). Injecting edl would bypass G1.
        if not _g1_open(ctx):
            _inject_edl_producer(ctx, out)
        deferred.append(sid)
        return True
    hole = earliest_incomplete_must_precede(ctx, sid)
    if hole and hole != sid:
        if hole not in out and hole not in deferred:
            out.append(hole)
        deferred.append(sid)
        return True
    # Leapfrog B+: Admit Constitution schedule gate (clamp + checklist).
    try:
        from interview_mux.heal_pin_authority import admit_schedule

        ok, alt, _reason = admit_schedule(ctx, sid)
        if not ok:
            prefer = str(alt or "").strip()
            # Never reinject the deferred consumer as its own "hole".
            if (
                prefer
                and prefer != sid
                and prefer not in out
                and prefer not in deferred
            ):
                out.append(prefer)
            deferred.append(sid)
            return True
    except Exception:
        pass
    return False


def assembly_wav_present(ctx: RunContext) -> bool:
    """True when some assembly audio exists (preview or final).

    HAU: music admit must use ``mix_junction_seat.may_admit_music`` (seated or
    preview_music gate) — this helper remains the broad "any WAV" check for
    Phase A / delight only, never spend.
    """
    return ctx.artifact_exists("master/assembly.wav") or ctx.artifact_exists(
        "master/assembly_preview.wav"
    )


def music_assembly_ready(ctx: RunContext) -> bool:
    """Whether music/SFX stages may spend — HAU seat authority ``may_admit_music``."""
    try:
        from interview_mux.mix_junction_seat import may_admit_music

        return bool(may_admit_music(ctx))
    except Exception:
        return False


def listen_delight_waived_unattended(ctx: RunContext) -> bool:
    """Telemetry-only unattended waiver — not quality / ship clearance (A-04 / SYN-DELIGHT-01)."""
    if not ctx.artifact_exists(LISTEN_DELIGHT_WAIVER_REL):
        return False
    try:
        doc = ctx.read_json(LISTEN_DELIGHT_WAIVER_REL)
    except Exception:
        return False
    if not isinstance(doc, dict):
        return False
    return str(doc.get("status") or "") == "waived_unattended"


def listen_delight_quality_waived(ctx: RunContext) -> bool:
    """Explicit quality waiver — may clear music/ship delight floor (not bare telemetry)."""
    if ctx.artifact_exists(LISTEN_DELIGHT_WAIVER_REL):
        try:
            doc = ctx.read_json(LISTEN_DELIGHT_WAIVER_REL)
        except Exception:
            doc = None
        if isinstance(doc, dict) and str(doc.get("status") or "") in {
            "quality_waived",
            "waived_quality",
        }:
            return True
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    except Exception:
        meta = {}
    try:
        from interview_mux.e2e_soft import e2e_quality_waivers_enabled

        if e2e_quality_waivers_enabled(meta=meta if isinstance(meta, dict) else None):
            return True
    except Exception:
        pass
    return False


def listen_delight_cleared_for_progress(ctx: RunContext) -> bool:
    """Three-state delight clearance for music/ship: seed_complete or quality_waived only.

    ``waived_unattended`` is telemetry and must not green delivery_stable_for_music,
    ship_path_ready, or PMQ publish_allowed by itself (A-04 Done-when).
    """
    if seed_stage_complete(ctx, "listen_delight_audit"):
        return True
    return listen_delight_quality_waived(ctx)


def ensure_listen_delight_waiver_unattended(ctx: RunContext) -> bool:
    """Automation driver: write waived_unattended telemetry after an audit attempt.

    Does **not** clear music/ship delight floors — callers must use
    ``listen_delight_cleared_for_progress`` (seed_complete | quality_waived).
    """
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
        "reason": "full-auto telemetry after audit attempt (not quality clearance)",
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


def _g1_record_open(ctx: RunContext) -> list[str]:
    """Missing G1 lines that still need operator *record* takes.

    ``delivery=synthesize`` holes are closed by ``vo_synthesize`` itself — treating
    them as a stability prereq creates a g1_vo_open ↔ vo_synthesize deadlock
    (forensics exec_10066 identical×N seed_order_prereq).

    C-01: prefer ``operator/vo_line_owners.json`` when present.
    """
    try:
        from interview_mux.delivery_invariants import (
            OWNER_RECORD,
            VO_LINE_OWNERS_REL,
        )

        if ctx.artifact_exists(VO_LINE_OWNERS_REL):
            doc = ctx.read_json(VO_LINE_OWNERS_REL)
            owners = (doc or {}).get("owners") if isinstance(doc, dict) else {}
            if isinstance(owners, dict) and owners:
                return [lid for lid, own in owners.items() if own == OWNER_RECORD]
    except Exception:
        pass
    missing = _g1_open(ctx)
    if not missing:
        return []
    by_delivery: dict[str, str] = {}
    try:
        if ctx.artifact_exists("understanding/gap_report.json"):
            gap = ctx.read_json("understanding/gap_report.json") or {}
            for row in gap.get("interviewer_lines") or []:
                if not isinstance(row, dict):
                    continue
                lid = str(row.get("line_id") or "").strip()
                if lid:
                    by_delivery[lid] = str(row.get("delivery") or "synthesize").strip().lower()
    except Exception:
        return list(missing)
    return [lid for lid in missing if by_delivery.get(lid, "synthesize") == "record"]


def _layup_escalation_blocking(ctx: RunContext) -> bool:
    # Cluster C: reconcile derived escalations from FloorIdentity first.
    try:
        from interview_mux.hosted_vo_authority import (
            floor_snapshot,
            reconcile_escalations,
        )

        snap = floor_snapshot(ctx, persist=True)
        reconcile_escalations(ctx, snap)
        if snap.identity.status in {"MET", "PARTIAL", "WAIVED", "UNWARRANTED"}:
            return False
        if snap.have >= 1:
            return False
    except Exception:
        pass
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
    if status not in {"open", "blocking", "needs_operator"}:
        return False
    # Stale hosted_vo_floor_unsatisfiable must not block Chatterbox after seats
    # were reminted (exec_13183: escalation active=0 while gap has synthesize
    # orientation — vo_synthesize_stability_block → layup thrash forever).
    reason = str(doc.get("reason") or "").lower()
    if "hosted_vo_floor" in reason or "unsatisfiable" in reason:
        try:
            from interview_mux.gap_fill_eligibility import count_active_gap_vo_lines

            if count_active_gap_vo_lines(ctx) >= 1:
                try:
                    doc = dict(doc)
                    doc["status"] = "cleared"
                    doc["cleared_reason"] = "active_synth_seats_present"
                    from datetime import datetime, timezone

                    doc["cleared_at"] = datetime.now(timezone.utc).isoformat()
                    ctx.write_json(rel, doc, skip_handoff=True)
                except Exception:
                    pass
                return False
        except Exception:
            pass
    return True


def delivery_stable_for_music(ctx: RunContext) -> tuple[bool, str]:
    """G5: Phase C music block may start only when this returns (True, '').

    SYN-DELIGHT-01: ``waived_unattended`` telemetry alone is NOT delight-OK.
    Music may proceed only with seed_complete listen_delight or an explicit
    quality waiver (e2e_quality_waivers / quality_waived stamp).
    """
    if not seed_stage_complete(ctx, "nugget_layup_compose"):
        return False, "layup_incomplete"
    if _g1_open(ctx):
        return False, "g1_open"
    if not seed_stage_complete(ctx, "vo_line_adjudicate"):
        return False, "vo_adjudicate_incomplete"
    if not seed_stage_complete(ctx, "edl"):
        return False, "edl_incomplete"
    if not seed_stage_complete(ctx, "assembly_preview") and not assembly_wav_present(ctx):
        return False, "assembly_missing"
    # HAU federal: music spend requires seated heard-assembly (or preview_music).
    try:
        from interview_mux.mix_junction_seat import music_admit_block_reason

        blocked = music_admit_block_reason(ctx)
        if blocked:
            return False, blocked
    except Exception:
        return False, "assembly_not_ready_for_music"
    # A-04: mint telemetry waiver for observability; clearance is seed|quality only.
    if not listen_delight_cleared_for_progress(ctx):
        ensure_listen_delight_waiver_unattended(ctx)
    if not listen_delight_cleared_for_progress(ctx):
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
    """Canonical predicate: Phase A stable + music chain sealed + SDP WAV parity.

    When ``delivery_epoch.music_complete_at`` is already stamped and SDP asset
    WAVs are still on disk, trust the stamp even if MUSIC_BEFORE_MIX
    ``.stage_done`` markers were later cleared (orphan/heal thrash). Re-burning
    MusicGen because adjudicate went hollow is forbidden.

    MU8: refuse trust / auto-break seal when referenced assets are stubs.
    """
    epoch = read_delivery_epoch(ctx)
    if epoch.get("music_complete_at"):
        try:
            from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

            missing = missing_sdp_asset_wavs(ctx)
            if not missing:
                # Re-seat hollow music markers only when that stage is actually
                # healable (outputs + no incompleteness). Never raw-touch
                # incomplete producers over a stamp alone (expanded WS2 O12).
                # Stamp + audible SDP still completes the epoch so mix does not
                # re-burn MusicGen (anti-thrash); incomplete markers stay unmarked.
                for sid in MUSIC_BEFORE_MIX:
                    if seed_stage_complete(ctx, sid):
                        continue
                    try:
                        from interview_mux.homunculus.agenda import (
                            stage_outputs_present,
                        )
                        from interview_mux.stage_completion import (
                            heal_or_refuse_mark,
                            stage_artifact_incompleteness,
                        )

                        if (
                            stage_outputs_present(ctx, sid)
                            and stage_artifact_incompleteness(ctx, sid) is None
                        ):
                            heal_or_refuse_mark(ctx, sid, force=True)
                    except Exception:
                        pass
                return True
            # Stamp present but stubs/silence still referenced — break seal.
            break_music_epoch_seal(
                ctx, reason="music_complete_at_with_missing:" + ",".join(missing[:4])
            )
            return False
        except Exception:
            pass
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


def mix_epoch_block(ctx: RunContext, stage: str | None = None) -> str | None:
    """B3: mix/master/ship wait until music_epoch_complete (no hollow QA bypass).

    HX-1: while music is incomplete this never returns ``None`` — including when
    Phase A is unsealed / delivery is unstable. Execute and 0.1.0 dispatch honor
    a present token; a no-op let mix/junction/finalize run.

    HAU ``optional_beds_until_remaster``: allow a speech-first **mix** when
    music cannot yet admit (preview/unseated present, no preview_music) so
    federal seated-only music admit does not deadlock. Junction/finalize still
    wait. FG2: speech-first only when ``stage=="mix"`` via
    ``clear_mix_epoch_for_speech_first`` — bare ``mix_epoch_block(ctx)`` must
    not false-clear music for resume routers.

    After music completes, speech-first seats still block junction/finalize until
    ``ensure_speech_first_remaster`` clears (beds remaster land) — token
    ``speech_first_remaster_pending``.
    """
    epoch = read_delivery_epoch(ctx)
    music_done = bool(epoch.get("music_complete_at") and music_epoch_complete(ctx))
    if not music_done and music_epoch_complete(ctx):
        stamp_delivery_epoch(ctx, music_complete_at=_utc_now())
        music_done = True
    sid = str(stage or "").strip()
    if music_done:
        try:
            from interview_mux.mix_junction_seat import ensure_speech_first_remaster

            if ensure_speech_first_remaster(ctx):
                if sid == "mix":
                    return None
                return "speech_first_remaster_pending"
        except Exception:
            pass
        return None
    if sid == "mix":
        try:
            from interview_mux.mix_junction_seat import clear_mix_epoch_for_speech_first

            if clear_mix_epoch_for_speech_first(ctx):
                return None
        except Exception:
            pass
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


def resolve_vo_synth_seed_resume(
    block: str | None, ctx: RunContext | None = None
) -> str | None:
    """Map vo_synthesize stability tokens to a real ANALYSIS/DELIVERY stage id.

    ``g1_vo_open`` uses the unified Wave-1 policy when ``ctx`` is provided
    (record → adjudicate; synth+seeded → synthesize; synth+hollow → adjudicate).
    """
    token = str(block or "").strip()
    if not token:
        return None
    if token == "g1_vo_open" and ctx is not None:
        try:
            from interview_mux.delivery_invariants import resolve_g1_vo_open_resume

            return resolve_g1_vo_open_resume(ctx)
        except Exception:
            pass
    return VO_SYNTH_SEED_SENTINELS.get(token, token)


def seal_adjudicate_stale_when_g1_green(ctx: RunContext) -> bool:
    """Clear false layup-invalidation on adjudication when G1 coverage is already green.

    Re-entering ``vo_line_adjudicate`` rewrites gap text and purges matching WAVs
    (forensics exec_10066). When pickups already resolve, the stale stamp is a
    heal artifact — not a reason to destroy seated audio.
    """
    try:
        missing = _g1_open(ctx)
    except Exception:
        return False
    if missing:
        return False
    rel = "understanding/vo_line_adjudication.json"
    if not ctx.artifact_exists(rel):
        return False
    try:
        doc = ctx.read_json(rel)
    except Exception:
        return False
    if not isinstance(doc, dict):
        return False
    meta = dict(doc.get("_meta") or {})
    if not meta.get("stale"):
        # Still ensure done marker so seed order does not re-enter — via heal,
        # never raw touch when incompleteness is open (expanded WS2 O9).
        if not seed_stage_complete(ctx, "vo_line_adjudicate"):
            try:
                from interview_mux.stage_completion import heal_or_refuse_mark

                heal_or_refuse_mark(ctx, "vo_line_adjudicate", force=True)
            except Exception:
                pass
        # Anti-purge OK when G1 green; music/seal consumers still need seed_complete.
        return not _g1_open(ctx)
    reason = str(meta.get("stale_reason") or "")
    if "nugget_layup_compose" not in reason and "invalidated_by" not in reason.lower():
        return False
    meta.pop("stale", None)
    meta.pop("stale_reason", None)
    meta["sealed_g1_green"] = True
    meta["sealed_g1_green_at"] = _utc_now()
    doc["_meta"] = meta
    try:
        ctx.write_json(rel, doc, skip_handoff=True)
    except Exception:
        return False
    try:
        from interview_mux.stage_completion import heal_or_refuse_mark

        heal_or_refuse_mark(ctx, "vo_line_adjudicate", force=True)
    except Exception:
        pass
    try:
        ctx.log(
            "Sealed vo_line_adjudicate stale — G1 green; refuse re-adjudicate thrash",
            level="warning",
            stage="vo_line_adjudicate",
            detail={"stale_reason_cleared": reason[:160]},
        )
    except Exception:
        pass
    return not _g1_open(ctx)


def vo_synthesize_stability_block(
    ctx: RunContext, *, allow_rewrite: bool = True
) -> str | None:
    """G8: Chatterbox batch waits for layup/transitions stability.

    Operator *record* G1 holes still block (``g1_vo_open``) outside Full-auto.
    Full-auto rewrites those lines to synthesize first (VS-B3). Synthesize-delivery
    G1 holes do not block — this stage is what closes them.

    ``allow_rewrite=False`` — read-only probe (VO ladder / Partial); never mutates
    gap_report via Full-auto record→synth rewrite.

    Returns a blocker token (may be a sentinel such as ``g1_vo_open``). Callers
    that need ``--from-stage`` must run :func:`resolve_vo_synth_seed_resume`.
    """
    if allow_rewrite:
        try:
            from interview_mux.gap_vo_gates import rewrite_full_auto_record_lines_to_synth

            rewrite_full_auto_record_lines_to_synth(ctx)
        except Exception:
            pass
    # High-gap unframed must heal at compose before layup/IPP clamp thrash
    # (exec_13170: vo_synthesize → information_package_plan while seg_007 dirty).
    try:
        from interview_mux.stage_completion import (
            _high_gap_unframed_incompleteness,
            high_gap_heal_resume_stage,
        )

        if _high_gap_unframed_incompleteness(ctx, "gap_framing_compose"):
            return high_gap_heal_resume_stage(ctx)
    except Exception:
        pass
    if _g1_record_open(ctx):
        return "g1_vo_open"
    if _layup_escalation_blocking(ctx):
        return "nugget_layup_compose"
    # C-05: require seed_stage_complete (coverage floors via incompleteness).
    # Wrong path was mastering/nugget_layup_plan.json; SSOT is understanding/….
    # Soft escape that bypassed incompleteness is removed.
    if not seed_stage_complete(ctx, "nugget_layup_compose"):
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
    # DP-LAYUP-ADJ A: G8 stays layup/transitions/stale stability (not full ladder —
    # adjudicate hole is MUST_PRECEDE + clamp_resume_through_order).
    return None


def upstream_stale_blockers(ctx: RunContext, stage: str) -> list[str]:
    """G9 / C3: stale upstream artifacts that must block expensive consumers."""
    blockers: list[str] = []
    if stage not in STALE_PREFLIGHT_CONSUMERS and stage not in MUSIC_REQUIRES_ASSEMBLY:
        return blockers

    def _stale(rel: str) -> bool:
        try:
            from interview_mux.thrash_hardening import artifact_usable

            ok, reason = artifact_usable(ctx, rel, consumer=stage)
            if not ok and reason.startswith("stale"):
                return True
        except Exception:
            pass
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

            # Never block mix on assembly_stale — mix is the remaster that reseats
            # commitment (exec_13167: cannot run mix: stale upstream … thrash).
            if assembly_stale_versus_edl(ctx) and stage in {
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
    from interview_mux.delivery_invariants import committed_master_wav
    from interview_mux.done_authority import honest_finalize_seeded

    if committed_master_wav(ctx) and honest_finalize_seeded(ctx):
        return "E"
    ok, _ = delivery_stable_for_music(ctx)
    if ok or read_checkpoint(ctx):
        if seed_stage_complete(ctx, "mmaudio_sfx") or (
            ctx.artifact_exists("sound_design/mmaudio_qa.json")
            and assembly_wav_present(ctx)
        ):
            if seed_stage_complete(ctx, "mix") or ctx.artifact_exists(
                "master/assembly.wav"
            ):
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
    try:
        from interview_mux.thrash_hardening import (
            ensure_phase_a_seal_deadline,
            music_epoch_sealed_no_delight_rewind,
        )

        ensure_phase_a_seal_deadline(ctx)
        _music_sealed_fn = music_epoch_sealed_no_delight_rewind
    except Exception:
        _music_sealed_fn = None
    g1_missing = _g1_open(ctx)
    vo_block = vo_synthesize_stability_block(ctx)
    # Telemetry waiver may be written, but does not flip delivery_stable alone (A-04).
    if not delivery_stable_for_music(ctx)[0]:
        ensure_listen_delight_waiver_unattended(ctx)
    stable, stable_reason = delivery_stable_for_music(ctx)
    sealed = phase_a_sealed(ctx)
    ship_ready, ship_reason = ship_path_ready(ctx)
    music_sealed = False
    try:
        music_sealed = bool(_music_sealed_fn and _music_sealed_fn(ctx))
    except Exception:
        music_sealed = False
    out: list[str] = []
    deferred: list[str] = []
    for sid in remaining:
        # After music epoch sealed: skip delight/narrative only when already complete.
        if music_sealed and sid in {
            "listen_delight_audit",
            "edl_narrative_audit",
            "assembly_preview",
        }:
            try:
                if seed_stage_complete(ctx, sid):
                    deferred.append(sid)
                    continue
            except Exception:
                pass
            # Hollow/incomplete — keep in candidates so quality can finish.
        # Never enqueue edl while narrative audit is missing or still blocking.
        if sid == "edl":
            try:
                from interview_mux.edl_narrative_remutate import narrative_audit_blocks_edl

                audit_missing = not ctx.artifact_exists("master/edl_narrative_audit.json")
                if audit_missing or narrative_audit_blocks_edl(ctx):
                    # G1 open: do not inject narrative/edl — G1_CONSUMERS defer owns pin.
                    if not g1_missing:
                        if "edl_narrative_audit" not in out and not seed_stage_complete(
                            ctx, "edl_narrative_audit"
                        ):
                            out.append("edl_narrative_audit")
                    deferred.append(sid)
                    continue
            except Exception:
                pass
        # MUST_PRECEDE / EDL consumers: seed-complete producers only (exec_13165).
        # Ship-ready finalize/ship may proceed without re-proving edl (master committed).
        # Junction named as the ship hole may proceed when assembly exists.
        _skip_edl_defer = (
            (ship_ready and sid in {"master_finalize", *SHIP_AFTER_MASTER})
            or (
                sid == "junction_snip_qa"
                and ship_reason == "junction_incomplete"
                and assembly_wav_present(ctx)
            )
        )
        if not _skip_edl_defer and defer_until_producers_ready(ctx, sid, out, deferred):
            continue
        # Only skip junction when it is actually seed-complete. ship_path_ready
        # already requires that, but keep the guard explicit for thrash safety.
        if (
            ship_ready
            and sid == "junction_snip_qa"
            and seed_stage_complete(ctx, "junction_snip_qa")
        ):
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
        if sid in MUSIC_REQUIRES_ASSEMBLY and not music_assembly_ready(ctx):
            try:
                from interview_mux.mix_junction_seat import (
                    music_admit_block_reason,
                    next_delivery_seat,
                )

                reason = music_admit_block_reason(ctx) or "assembly_missing"
                # Always-HAU: keep SSOT pin eligible (F10 — not forever-mix).
                pin = next_delivery_seat(ctx)
                if pin and pin in remaining and pin not in out:
                    out.append(pin)
            except Exception:
                reason = (
                    "assembly_not_seated_for_music"
                    if assembly_wav_present(ctx)
                    else "assembly_missing"
                )
            if _music_defer_log_allowed(ctx, sid, reason):
                record_wasted_work(
                    ctx,
                    event="music_deferred",
                    stage=sid,
                    detail={"reason": reason},
                )
            deferred.append(sid)
            continue
        from interview_mux.delivery_invariants import committed_master_wav

        if sid in SHIP_AFTER_MASTER and not committed_master_wav(ctx):
            deferred.append(sid)
            continue
        if sid in (*PHASE_B_STAGES, *PHASE_C_STAGES, "mix", "junction_snip_qa", "master_finalize") or sid in SHIP_AFTER_MASTER:
            if not sealed:
                # HAU speech-first mix may seat assembly before Phase A stamp
                # lands (exec_13170: filter([mix]) emptied → mmaudio reinject).
                allow_mix = False
                if sid == "mix":
                    try:
                        from interview_mux.mix_junction_seat import (
                            beds_deferred_for_mix,
                            hold_speech_first_mix,
                            next_delivery_seat,
                        )

                        allow_mix = bool(
                            hold_speech_first_mix(ctx, "mix")
                            or beds_deferred_for_mix(ctx)
                            or next_delivery_seat(ctx) == "mix"
                        )
                    except Exception:
                        allow_mix = False
                if not allow_mix:
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
            # C-05 belt: sealed stamp alone is not enough if layup later went hollow.
            if sid in MUSIC_REQUIRES_ASSEMBLY and not seed_stage_complete(
                ctx, "nugget_layup_compose"
            ):
                if _music_defer_log_allowed(ctx, sid, "layup_incomplete"):
                    record_wasted_work(
                        ctx,
                        event="music_deferred",
                        stage=sid,
                        detail={"reason": "layup_incomplete", "predicate": "phase_a_seal"},
                    )
                deferred.append(sid)
                continue
        if sid in MIX_EPOCH_CONSUMERS:
            mix_b = mix_epoch_block(ctx, stage=sid)
            if mix_b:
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
        if sid not in out:
            out.append(sid)
    if deferred and not out:
        # T2: try orphan promote + Phase A seal once before empty fallback.
        try:
            promote_complete_orphan_stage_done(ctx)
            seal_phase_a_if_stable(ctx)
        except Exception:
            pass
        # MU3: music limbo exit (omit or break-seal) when Phase A sealed but beds stuck.
        try:
            resolve_music_limbo_exit(ctx)
        except Exception:
            pass
        # Re-scan remaining after seal heal — full MUST_PRECEDE / filter predicates.
        sealed_now = phase_a_sealed(ctx)
        stable_now, _ = delivery_stable_for_music(ctx)
        if sealed_now or stable_now:
            out2: list[str] = []
            deferred2: list[str] = []
            for sid in remaining:
                if defer_until_producers_ready(ctx, sid, out2, deferred2):
                    continue
                if sid in MUSIC_REQUIRES_ASSEMBLY and not music_assembly_ready(ctx):
                    continue
                if sid in (*PHASE_B_STAGES, *PHASE_C_STAGES) and not phase_a_sealed(ctx):
                    continue
                if sid in MIX_EPOCH_CONSUMERS and mix_epoch_block(ctx, stage=sid):
                    continue
                if g1_missing and sid in G1_CONSUMERS:
                    continue
                out2.append(sid)
            if out2:
                return out2
            # Reinject earliest incomplete producer so walk never empties forever.
            if deferred2:
                for sid in remaining:
                    hole = earliest_incomplete_must_precede(ctx, sid)
                    if hole and hole not in out2:
                        out2.append(hole)
                        return out2
                if not edl_ready(ctx):
                    _inject_edl_producer(ctx, out2)
                    if out2:
                        return out2
            # F10: empty re-scan → Always-HAU seating SSOT (not forever Phase-A).
            if not out2:
                if not edl_ready(ctx):
                    _inject_edl_producer(ctx, out2)
                    if out2:
                        return out2
                try:
                    from interview_mux.mix_junction_seat import next_delivery_seat

                    pin = next_delivery_seat(ctx)
                    if pin and pin in remaining and pin not in out2:
                        out2.append(pin)
                        return out2
                except Exception:
                    pass
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
        if not out and not edl_ready(ctx):
            _inject_edl_producer(ctx, out)
        if not out and phase_a_sealed(ctx):
            # Pin music/mix/finalize ladder only after Phase A is sealed + edl ready.
            post_a = set(MUSIC_BEFORE_MIX) | set(MIX_EPOCH_CONSUMERS) | set(SHIP_AFTER_MASTER)
            if remaining and all(s in post_a for s in remaining):
                try:
                    from interview_mux.thrash_hardening import path_to_master_pin

                    pin = path_to_master_pin(ctx)
                    if pin and pin not in out:
                        # Never pin music/mix while edl incomplete.
                        if pin in EDL_CONSUMERS and not edl_ready(ctx):
                            _inject_edl_producer(ctx, out)
                        else:
                            out.append(pin)
                except Exception:
                    try:
                        from interview_mux.thrash_hardening import (
                            FAIL_CLASS_DELIVERY_BLOCKED,
                            canonical_resume_pin,
                        )

                        pin = canonical_resume_pin(ctx, FAIL_CLASS_DELIVERY_BLOCKED)
                        if pin and pin not in out:
                            out.append(pin)
                    except Exception:
                        pass
    return out


def reconcile_delivery_batch(ctx: RunContext) -> list[str]:
    """G3: unmark hollow producers + reconcile .stage_done at every delivery batch start.

    TH6: promote XOR unmark — snapshot incompleteness once; never promote a stage
    that was just unmarked (or unmark one just promoted) in the same batch.
    """
    try:
        from interview_mux.execution_contract import reconcile_execution_contract

        reconcile_execution_contract(ctx, reason="delivery_batch")
    except Exception:
        pass
    # Snapshot hollow-done candidates before either promote or unmark mutates markers.
    hollow_snapshot: set[str] = set()
    try:
        for sid in G3_RECONCILE_CHAIN:
            # DETECTION_ONLY_IS_DONE: hollow stamp census before promote/unmark XOR.
            if ctx.is_done(sid) and not seed_stage_complete(ctx, sid):
                hollow_snapshot.add(sid)
    except Exception:
        pass
    # Runtime hollow escalate: done ∧ ¬land_honest (forensics writes operator artifact).
    try:
        from interview_mux.hollow_done_guard import escalate_hollow_done

        escalate_hollow_done(
            ctx, stages=tuple(G3_RECONCILE_CHAIN), raise_on_find=False
        )
    except Exception:
        pass
    cleared: list[str] = []
    try:
        from interview_mux.homunculus.agenda import unmark_hollow_delivery_producers

        # Unmark hollow first; promoted set excludes these (XOR).
        cleared.extend(unmark_hollow_delivery_producers(ctx, G3_RECONCILE_CHAIN))
    except Exception:
        pass
    try:
        from interview_mux.stage_completion import reconcile_stage_done_marker

        for sid in G3_RECONCILE_CHAIN:
            if sid in hollow_snapshot or (ctx.is_done(sid) and not seed_stage_complete(ctx, sid)):
                if ctx.is_done(sid) and not seed_stage_complete(ctx, sid):
                    if not reconcile_stage_done_marker(ctx, sid):
                        cleared.append(sid)
                        hollow_snapshot.add(sid)
    except Exception:
        pass
    if cleared:
        ctx.log(
            "delivery reconcile cleared hollow: " + ", ".join(dict.fromkeys(cleared)),
            level="warning",
            stage="delivery",
            detail={"cleared": list(dict.fromkeys(cleared))},
        )
    # Promote orphans only for stages not unmarked this batch (XOR).
    orphans = reconcile_orphan_artifacts(ctx, skip_promote=frozenset(hollow_snapshot | set(cleared)))
    cleared.extend(orphans)
    return list(dict.fromkeys(cleared))



def promote_complete_orphan_stage_done(
    ctx: RunContext,
    stages: tuple[str, ...] | None = None,
    *,
    skip: frozenset[str] | None = None,
) -> list[str]:
    """Inverse of hollow-done: stamp .stage_done when producer artifacts are complete.

    exec_5402 thrash: edl.json + edl_narrative_audit.json present, markers missing →
    Phase A never seals → music deferred → premature_cap rewrites music→narrative.

    TH6: ``skip`` stages (just unmarked this batch) are never promoted (XOR).
    Active remutate stages (listen-delight + edl_narrative) are also skipped —
    leftover artifacts must not restamp markers and noop the remutate
    (forensics exec_10066).
    """
    from interview_mux.delivery_invariants import active_remutate_stages
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
    from interview_mux.stage_completion import stage_artifact_incompleteness

    scope = stages if stages is not None else tuple(G3_RECONCILE_CHAIN)
    skip_set = set(skip or frozenset()) | set(active_remutate_stages(ctx))
    promoted: list[str] = []
    for sid in scope:
        if sid in skip_set:
            continue
        # DETECTION_ONLY_IS_DONE: already stamped (hollow or honest) — do not re-promote.
        if ctx.is_done(sid):
            continue
        # Land Honesty: refuse promote while unpaid remaster / stamp-alone / etc.
        try:
            from interview_mux.done_authority import (
                unpaid_land_blocks_promote,
                unpaid_land_reason,
            )

            if unpaid_land_blocks_promote(ctx, sid):
                try:
                    why = unpaid_land_reason(ctx, sid) or "unpaid_land"
                    ctx.log(
                        f"orphan promote refused unpaid land: {sid} — {why}",
                        level="warning",
                        stage="delivery",
                        detail={
                            "event": "unpaid_land_refuse_promote",
                            "stage": sid,
                            "unpaid_land_reason": why,
                        },
                    )
                except Exception:
                    pass
                continue
        except Exception:
            continue
        rel = STAGE_ARTIFACT_DISK_PATHS.get(sid)
        if not rel:
            # WAV-first producers (assembly_preview/mix) may live only in
            # PROTECTED_DELIVERY_OUTPUTS — still promote when outputs are complete.
            try:
                from interview_mux.homunculus.agenda import (
                    PROTECTED_CORE_STAGES,
                    PROTECTED_DELIVERY_OUTPUTS,
                )

                outs = PROTECTED_DELIVERY_OUTPUTS.get(sid) or PROTECTED_CORE_STAGES.get(
                    sid
                ) or ()
                rel = outs[0] if outs else None
            except Exception:
                rel = None
        if not rel or not ctx.artifact_exists(rel):
            continue
        try:
            from interview_mux.homunculus.agenda import stage_outputs_present

            if not stage_outputs_present(ctx, sid):
                continue
        except Exception:
            continue
        try:
            if stage_artifact_incompleteness(ctx, sid) is not None:
                continue
        except Exception:
            continue
        try:
            from interview_mux.stage_completion import heal_or_refuse_mark

            out = heal_or_refuse_mark(ctx, sid)
            if not out.get("marked"):
                continue
        except Exception:
            continue
        # DETECTION_ONLY_IS_DONE: confirm promote write stuck (not advance/skip).
        if ctx.is_done(sid):
            promoted.append(sid)
    if promoted:
        record_wasted_work(
            ctx,
            event="orphan_stage_done_promoted",
            stage="delivery",
            detail={"stages": promoted[:12]},
        )
        ctx.log(
            "promoted complete orphan stage_done: " + ", ".join(promoted),
            level="info",
            stage="delivery",
            detail={"promoted": promoted},
        )
    return promoted


def reconcile_orphan_artifacts(
    ctx: RunContext,
    *,
    skip_promote: frozenset[str] | None = None,
) -> list[str]:
    """R11c: promote complete orphans; demote incomplete orphans; flag leftovers."""
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

    promoted = promote_complete_orphan_stage_done(ctx, skip=skip_promote)
    demoted: list[str] = []
    try:
        from interview_mux.thrash_hardening import demote_incomplete_orphans

        demoted = demote_incomplete_orphans(ctx)
    except Exception:
        demoted = []
    orphans: list[str] = []
    for sid, rel in STAGE_ARTIFACT_DISK_PATHS.items():
        if sid not in G3_RECONCILE_CHAIN:
            continue
        if sid in (skip_promote or frozenset()):
            continue
        # DETECTION_ONLY_IS_DONE: artifact without stamp = orphan candidate.
        if not (ctx.artifact_exists(rel) and not ctx.is_done(sid)):
            continue
        # Shared-path early writers (e.g. sound_design_palettes → plan.json) are
        # not orphans of the later consumer stage — sticky-halting on them
        # freezes Full-auto before G-Framing (forensics exec_11130).
        # Brief/boundaries: any ALLOW co-producer claim is valid (not only the
        # stage's own id — hitch/fuse/resplit must not orphan detection).
        try:
            if str(rel).endswith(".json"):
                doc = ctx.read_json(rel)
                producer = ""
                if isinstance(doc, dict):
                    producer = str((doc.get("_meta") or {}).get("producer_stage") or "")
                from interview_mux.shared_path_commit import (
                    SHARED_PATH_COMMIT_RELS,
                    producer_claim_ok,
                )

                if str(rel) in SHARED_PATH_COMMIT_RELS:
                    if producer_claim_ok(str(rel), producer) and producer != sid:
                        continue
                # DETECTION_ONLY_IS_DONE: producer stamp presence (orphan filter).
                elif producer and producer != sid and ctx.is_done(producer):
                    continue
        except Exception:
            pass
        orphans.append(sid)
    if orphans or demoted:
        record_wasted_work(
            ctx,
            event="orphan_artifact",
            stage="delivery",
            detail={
                "stages": orphans[:12],
                "promoted": promoted[:12],
                "demoted": demoted[:12],
            },
        )
    return orphans


def music_skip_allowed(ctx: RunContext, stage: str) -> bool:
    """G4: SDP skip only when assembly exists and the stage is actually complete."""
    if stage not in MUSIC_REQUIRES_ASSEMBLY:
        return False
    if not music_assembly_ready(ctx):
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
    try:
        from interview_mux.thrash_hardening import ensure_finalize_inputs_present

        # Restore archives only — do not emit ledger here (would hide missing-ledger pin).
        ensure_finalize_inputs_present(ctx, emit_ledger=False)
    except Exception:
        pass
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
    """Pin for assembly-vs-EDL drift: edl if EDL missing/stale, else remaster mix.

    Never absolute ``edl`` when live EDL is healthy — that was the wrong pin that
    mirrored the stale-transitions/EDL empty-heal class.

    Never pin ``junction_snip_qa`` here: junction is blocked by the same
    ``assembly_stale_versus_edl`` stale-upstream token, so a mix_outputs_seated
    false-positive (mtime seat while commitment diverged) thrashes
    junction↔stale forever (exec_13167). Remaster via mix.
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
    # Prefer thin sanitize pins over broader producers when refuse/unsanitary.
    if (
        "sanitize_refused" in reason
        or "gap_unsanitary" in reason
        or "sanitize" in reason
    ):
        return "gap_report_sanitize"
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

    C-03: ``check_g1_vo`` exception alone must not fail-open to True. Refuse
    rewind when Phase A is sealed **and** positive-evidence probes fail.
    Unsealed + exception may still rewind (progress) when no evidence found.

    Hard seat freeze + assembly: refuse non-catastrophe vo/seams rewind
    (Pillar B ``may_rewind_to_air_script_seams``) after G1/missing-WAV allows.
    """
    g1_check_failed = False
    try:
        from interview_mux.gates import check_g1_vo, g1_vo_was_skipped_optional

        if g1_vo_was_skipped_optional(ctx):
            return False
        if check_g1_vo(ctx):
            return True
    except Exception:
        g1_check_failed = True
    try:
        from interview_mux.vo_contract import seated_vo_missing_ids

        if seated_vo_missing_ids(ctx):
            return True
    except Exception:
        pass
    # B5: hard freeze + assembly refuses further rewind (not G1 / missing WAV).
    try:
        from interview_mux.seat_authority import may_rewind_to_air_script_seams

        if not may_rewind_to_air_script_seams(ctx):
            return False
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
        if missing:
            # Deferred-only holes after pair freeze stay mix last-chance.
            try:
                from interview_mux.transition_vo import (
                    frozen_transition_pair_keys,
                    read_transitions_pair_freeze,
                )

                if read_transitions_pair_freeze(ctx):
                    frozen = frozen_transition_pair_keys(ctx)
                    if frozen and all(m not in frozen for m in missing):
                        missing = []
            except Exception:
                pass
            if missing:
                return True
    except Exception:
        pass
    # C-03: sealed + no positive evidence → refuse (closes fail-open).
    if g1_check_failed and not phase_a_sealed(ctx):
        return True
    return False


def _music_epoch_producer_pin(ctx: RunContext) -> str:
    """Earliest incomplete MUSIC_BEFORE_MIX stage (or last when all seed-complete)."""
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


def premature_cap_hard_pin(
    ctx: RunContext | None, resume: str, *, message: str = ""
) -> str:
    """G7: stay on the incomplete producer; never advance to a consumer."""
    if ctx is None:
        return resume
    # Expensive-stage lease: do not rewrite pin away from active producer.
    # HX-4: mix/junction/finalize leases do not hold the pin while music is
    # still incomplete — pin MUSIC_BEFORE_MIX. Music/VO/transcribe leases stay.
    # After music_epoch_complete, mix-family leases still win (HX-2 seating later).
    try:
        from interview_mux.thrash_hardening import expensive_stage_lease_active

        leased, lease_stage = expensive_stage_lease_active(ctx)
        if leased and lease_stage:
            held = str(lease_stage).strip()
            # Always-HAU: requesting mix / mix lease while music incomplete.
            if not music_epoch_complete(ctx):
                try:
                    from interview_mux.mix_junction_seat import (
                        hold_speech_first_mix,
                        next_delivery_seat,
                    )

                    # F7: never hold a sealed lease pin.
                    if seed_stage_complete(ctx, held):
                        return next_delivery_seat(ctx)
                    # Speech-first mix request beats MusicGen lease (i7e).
                    if hold_speech_first_mix(ctx, resume):
                        return "mix"
                    # HX-4: mix-family lease while music incomplete → music
                    # producer pin (not Phase-A next_delivery_seat).
                    if held in MIX_EPOCH_RUN_BLOCK:
                        if hold_speech_first_mix(ctx, held):
                            return "mix"
                        return _music_epoch_producer_pin(ctx)
                except Exception:
                    pass
                if held in MIX_EPOCH_RUN_BLOCK:
                    return _music_epoch_producer_pin(ctx)
            return held
    except Exception:
        pass
    # Always-HAU: speech-first mix holds; else seating SSOT.
    if resume == "mix" and not music_epoch_complete(ctx):
        try:
            from interview_mux.mix_junction_seat import (
                hold_speech_first_mix,
                next_delivery_seat,
            )

            if hold_speech_first_mix(ctx, resume):
                return "mix"
            return next_delivery_seat(ctx)
        except Exception:
            pass
    # Prefer stable fail-class pins (T4) for known epochs before earliest walk.
    # D-08 / XC-PREMATURE: on heal_navigate exception, return last safe pin for
    # the class — never fall through to the original consumer resume.
    try:
        from interview_mux.thrash_hardening import (
            FAIL_CLASS_FINALIZE,
            FAIL_CLASS_MIX_SEAT,
            FAIL_CLASS_MUSIC_EPOCH,
            FAIL_CLASS_PHASE_A_EDL,
            FAIL_CLASS_VO_G1,
            canonical_resume_pin,
            heal_navigate,
            premature_fail_class,
        )

        cls = premature_fail_class(resume)

        def _safe_heal(intent: str) -> str:
            try:
                return str(
                    heal_navigate(
                        ctx, intent=intent, stage=resume, error=message
                    ).get("from_stage")
                    or ""
                )
            except Exception as exc:
                try:
                    ctx.log(
                        f"premature_cap heal_navigate failed ({intent}): {exc}",
                        level="warning",
                        stage=resume,
                        detail={
                            "event": "premature_cap_heal_exception",
                            "intent": intent,
                            "error": str(exc)[:400],
                        },
                    )
                except Exception:
                    pass
                try:
                    pinned = canonical_resume_pin(ctx, intent, hint=resume or message)
                    if pinned:
                        return pinned
                except Exception as pin_exc:
                    try:
                        ctx.log(
                            f"premature_cap canonical_resume_pin failed ({intent}): {pin_exc}",
                            level="warning",
                            stage=resume,
                            detail={
                                "event": "premature_cap_pin_exception",
                                "intent": intent,
                                "error": str(pin_exc)[:400],
                            },
                        )
                    except Exception:
                        pass
                # Last resort for known class: never return the consumer resume.
                if intent == FAIL_CLASS_MUSIC_EPOCH:
                    return "music_palette_compose"
                if intent == FAIL_CLASS_MIX_SEAT:
                    return "mix"
                if intent == FAIL_CLASS_FINALIZE:
                    return "edl"
                if intent == FAIL_CLASS_VO_G1:
                    return "vo_line_adjudicate"
                if intent == FAIL_CLASS_PHASE_A_EDL:
                    return "edl"
                return resume

        if cls == FAIL_CLASS_MUSIC_EPOCH and resume in MUSIC_BEFORE_MIX:
            return _safe_heal(FAIL_CLASS_MUSIC_EPOCH)
        if cls == FAIL_CLASS_MIX_SEAT:
            return _safe_heal(FAIL_CLASS_MIX_SEAT)
        if cls == FAIL_CLASS_FINALIZE or resume == "master_finalize":
            return _safe_heal(FAIL_CLASS_FINALIZE)
        if cls == FAIL_CLASS_VO_G1 and resume == "vo_synthesize" and _g1_open(ctx):
            return _safe_heal(FAIL_CLASS_VO_G1)
        if cls == FAIL_CLASS_PHASE_A_EDL:
            return _safe_heal(FAIL_CLASS_PHASE_A_EDL)
    except Exception as outer_exc:
        try:
            ctx.log(
                f"premature_cap class pin failed: {outer_exc}",
                level="warning",
                stage=resume,
                detail={"event": "premature_cap_class_exception", "error": str(outer_exc)[:400]},
            )
        except Exception:
            pass
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
        # Priors complete but selection still missing → stay on ranking.
        # Hardcoding topic_coverage_audit here created a pin cycle with
        # PHASE_A_EDL heal on TCA (exec_13167: ranking↔TCA thrash).
        try:
            if not seed_stage_complete(ctx, "full_master_ranking"):
                return "full_master_ranking"
        except Exception:
            pass
        return "topic_coverage_audit"
    # Music-epoch producers: stay in MUSIC_BEFORE_MIX. Never walk back to earlier
    # Phase-A consumers (edl_narrative_audit / edl) via earliest-incomplete — that
    # was the exec_5402 infinite thrash (premature→music ×3 → pin → narrative).
    if resume in MUSIC_BEFORE_MIX:
        try:
            promote_complete_orphan_stage_done(
                ctx,
                (
                    "edl",
                    "edl_narrative_audit",
                    "assembly_preview",
                    "listen_delight_audit",
                ),
            )
            seal_phase_a_if_stable(ctx)
        except Exception:
            pass
        stable, reason = delivery_stable_for_music(ctx)
        if not stable and reason in {
            "layup_incomplete",
            "g1_open",
            "vo_adjudicate_incomplete",
            "layup_escalation_blocking",
        }:
            # True Phase-A producer holes — fall through to earliest-incomplete.
            pass
        elif not stable and reason == "edl_incomplete":
            return "edl"
        elif not stable and reason == "assembly_missing":
            return (
                "assembly_preview"
                if not seed_stage_complete(ctx, "assembly_preview")
                else "edl"
            )
        else:
            # phase_a_unsealed after heal, or already stable → run music.
            return _music_epoch_producer_pin(ctx)
    if resume in MIX_EPOCH_CONSUMERS and not music_epoch_complete(ctx):
        try:
            promote_complete_orphan_stage_done(
                ctx,
                (
                    "edl",
                    "edl_narrative_audit",
                    "assembly_preview",
                    "listen_delight_audit",
                ),
            )
            seal_phase_a_if_stable(ctx)
        except Exception:
            pass
        # Always-HAU: speech-first mix seats assembly before MusicGen.
        if resume == "mix":
            try:
                from interview_mux.mix_junction_seat import hold_speech_first_mix

                if hold_speech_first_mix(ctx, resume):
                    return "mix"
            except Exception:
                pass
        try:
            from interview_mux.mix_junction_seat import next_delivery_seat

            return next_delivery_seat(ctx)
        except Exception:
            pass
        return _music_epoch_producer_pin(ctx)
    # Post-music mix/junction/finalize: single ladder — never narrative audit.
    if resume in {"mix", "junction_snip_qa", "master_finalize"} or (
        resume in MIX_EPOCH_CONSUMERS and music_epoch_complete(ctx)
    ):
        try:
            from interview_mux.thrash_hardening import (
                ensure_finalize_inputs_present,
                path_to_master_pin,
            )

            ensure_finalize_inputs_present(ctx)
            return path_to_master_pin(ctx)
        except Exception:
            pass
    if resume == "vo_synthesize" and _g1_open(ctx):
        if not seed_stage_complete(ctx, "nugget_layup_compose"):
            return "nugget_layup_compose"
        block = vo_synthesize_stability_block(ctx)
        if block == "nugget_layup_compose":
            return "nugget_layup_compose"
        # G1 open with layup present — unified resume (never fake stage g1_vo_open).
        # Synth-only G1 stays on vo_synthesize when stability block is None.
        if block is None:
            from interview_mux.delivery_invariants import resolve_g1_vo_open_resume

            return resolve_g1_vo_open_resume(ctx)
        return resolve_vo_synth_seed_resume(block, ctx) or "vo_line_adjudicate"
    # Phase-A: skip audit-only when assembly audio already present.
    if resume in {"edl", "edl_narrative_audit", "assembly_preview"} and assembly_wav_present(
        ctx
    ):
        try:
            from interview_mux.thrash_hardening import (
                FAIL_CLASS_PHASE_A_EDL,
                canonical_resume_pin,
            )

            return canonical_resume_pin(ctx, FAIL_CLASS_PHASE_A_EDL, hint=resume)
        except Exception:
            pass
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



def resolve_premature_cap_pin(
    ctx: RunContext | None, resume: str, *, message: str = ""
) -> str:
    """Sole string pin for heal/driver/execute — hard_pin + F7 sealed fallthrough.

    Prefer this over bare ``premature_cap_hard_pin`` at driver heal/smart-resume
    sites. JobRunner execute rewrite goes through ``apply_premature_cap_for_execute``.

    Heal Clinic Option E: sideways rewrite only when allowlisted + checklist green.
    """
    target = str(resume or "").strip()
    if ctx is None:
        return target
    pinned = str(premature_cap_hard_pin(ctx, target, message=message) or "").strip() or target
    try:
        if pinned and seed_stage_complete(ctx, pinned):
            from interview_mux.mix_junction_seat import next_delivery_seat

            pinned = str(next_delivery_seat(ctx) or pinned).strip() or pinned
    except Exception:
        pass
    if pinned and pinned != target:
        try:
            from interview_mux.heal_pin_authority import admit_resume, may_rewrite_heal_pin

            ok, _allow_id, _refused = may_rewrite_heal_pin(
                ctx,
                from_stage=target,
                to_stage=pinned,
                error=message or target,
                intent="premature_cap",
            )
            if not ok:
                return target
            # B+: clamp + admit even after allowlist pass
            pinned = admit_resume(
                ctx,
                pinned,
                current=target,
                error=message or target,
                intent="premature_cap",
            )
        except Exception:
            # Fail closed on authority errors: do not sideways-pin.
            return target
    try:
        pinned = clamp_resume_through_order(ctx, pinned)
    except Exception:
        pass
    return pinned


def apply_premature_cap_for_execute(
    ctx: RunContext,
    resume: str,
    *,
    automation: bool,
    message: str = "",
) -> dict[str, Any]:
    """Shared premature_cap contract for JobRunner + full_auto_driver (i6 / F7).

    automation=True → rewrite from_stage onto producer and continue.
    automation=False → ok:False + pinned_to (GUI hard-fail).
    Never lands on a seed-complete pin (falls through to next_delivery_seat).
    """
    target = str(resume or "").strip()
    pinned = resolve_premature_cap_pin(ctx, target, message=message)
    if not pinned or pinned == target:
        return {"ok": True, "from_stage": target, "rewritten": False, "pinned_to": ""}
    reason = (
        f"Producer incomplete — pinned to {pinned} (requested {target})."
    )
    if automation:
        return {
            "ok": True,
            "from_stage": pinned,
            "rewritten": True,
            "pinned_to": pinned,
            "reason": reason,
        }
    return {
        "ok": False,
        "from_stage": target,
        "rewritten": False,
        "pinned_to": pinned,
        "reason": reason,
        "error": reason,
    }


def safe_mix_resume_stage(ctx: RunContext) -> str:
    """Return mix only when music epoch complete and junction residuals clear."""
    try:
        from interview_mux.heal_routing import resume_stage_for_error_class

        view = critical_residual_view(ctx)
        kinds = {str(k or "").strip() for k in (view.kinds or ())}
        if view.count > 0 and (
            "on_a_roll" in kinds
            or "incomplete_cut" in kinds
            or "incomplete_cut_unresolved" in kinds
            or any("junction" in k for k in kinds)
        ):
            return resume_stage_for_error_class(
                "incomplete_cut_unresolved", default="junction_snip_qa"
            )
    except Exception:
        pass
    if music_epoch_complete(ctx):
        # SSOT: leave mix only when fully seated (mtime + commitment).
        try:
            from interview_mux.air_order import mix_seat_resume_stage

            return mix_seat_resume_stage(ctx)
        except Exception:
            return "mix"
    # Always-HAU: speech-first mix seats before MusicGen; else seating SSOT.
    try:
        from interview_mux.mix_junction_seat import (
            hold_speech_first_mix,
            next_delivery_seat,
        )

        if hold_speech_first_mix(ctx, "mix"):
            return "mix"
        return next_delivery_seat(ctx)
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
    """Write operator/delivery_checkpoint.json when G5 stability predicates pass.

    C-05: layup requires ``seed_stage_complete`` only (no file-exists escape).
    Soft rewrite to ``phase_a_unsealed`` is marker-lag reasons only.
    """
    existing = read_checkpoint(ctx)
    # C-05: never seal (or soft-rewrite) without sanitary layup seed complete.
    if not seed_stage_complete(ctx, "nugget_layup_compose"):
        return existing
    # Artifact-led promote before stability check (markers often lag usable files).
    try:
        promote_complete_orphan_stage_done(
            ctx,
            (
                "edl",
                "edl_narrative_audit",
                "assembly_preview",
                "listen_delight_audit",
            ),
        )
    except Exception:
        pass
    ok, reason = delivery_stable_for_music(ctx)
    soft_marker_lag = False
    # Allow sealing when stable except the seal itself is the only missing piece.
    if not ok and reason != "phase_a_unsealed":
        # Soft rewrite only for marker-lag — never layup_incomplete / g1_open / etc.
        if reason not in PHASE_A_MARKER_LAG_REASONS:
            return existing
        try:
            from interview_mux.thrash_hardening import artifact_usable

            edl_ok, _ = artifact_usable(ctx, "master/edl.json", consumer="edl")
            audio_ok = assembly_wav_present(ctx)
            delight_ok = listen_delight_cleared_for_progress(ctx)
            if (
                edl_ok
                and audio_ok
                and delight_ok
                and not _g1_open(ctx)
                and not _layup_escalation_blocking(ctx)
            ):
                reason = "phase_a_unsealed"
                ok = False  # fall through to seal write path below
                soft_marker_lag = True
            else:
                return existing
        except Exception:
            return existing
    if not ok and reason == "phase_a_unsealed":
        # Re-check stability without seal requirement for the write path.
        # Seed-complete preferred; soft marker-lag may use artifact_usable after promote.
        if _g1_open(ctx):
            return existing
        if not seed_stage_complete(ctx, "vo_line_adjudicate"):
            return existing
        if not seed_stage_complete(ctx, "edl"):
            if soft_marker_lag:
                try:
                    from interview_mux.thrash_hardening import artifact_usable

                    edl_ok, _ = artifact_usable(ctx, "master/edl.json", consumer="edl")
                except Exception:
                    edl_ok = False
                if not edl_ok:
                    return existing
            else:
                return existing
        if not seed_stage_complete(ctx, "assembly_preview") and not assembly_wav_present(ctx):
            return existing
        # A-04 / TH4: seed_complete or quality_waived only — not waived_unattended.
        if not listen_delight_cleared_for_progress(ctx):
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
    # b15: Phase A seal dual-locks seats (soft freeze) in the same delivery_epoch
    try:
        from interview_mux.seat_authority import soft_freeze_active, stamp_soft_seat_freeze

        if not soft_freeze_active(ctx):
            stamp_soft_seat_freeze(ctx, reason="phase_a_seal")
    except Exception:
        pass
    record_wasted_work(ctx, event="phase_seal", stage="listen_delight_audit", detail=row)
    return row


def delivery_epoch_locked(ctx: RunContext) -> bool:
    epoch = read_delivery_epoch(ctx)
    if epoch.get("unlocked_at"):
        return False
    if epoch.get("locked"):
        return True
    return bool(epoch.get("phase_a_sealed_at"))


def unlock_delivery_epoch(
    ctx: RunContext, reason: str, *, unlock_seats: bool = False
) -> dict[str, Any]:
    """Unlock Phase A delivery epoch.

    ``unlock_seats=False`` (default) leaves ``vo_seats_freeze`` intact.
    ``unlock_seats=True`` soft+hard clears seat freeze in the same epoch stamp.
    """
    epoch = read_delivery_epoch(ctx)
    epoch["unlocked_at"] = _utc_now()
    epoch["unlock_reason"] = str(reason or "")[:400]
    epoch["locked"] = False
    epoch["updated_at"] = _utc_now()
    epoch["unlock_seats"] = bool(unlock_seats)
    if unlock_seats:
        try:
            from interview_mux.seat_authority import unlock_seat_freeze

            unlock_seat_freeze(
                ctx,
                reason=f"delivery_epoch:{reason}",
                clear_hard=True,
                clear_soft=True,
            )
            # Re-read so _mark does not clobber the seat unlock.
            epoch = read_delivery_epoch(ctx)
            epoch["unlocked_at"] = _utc_now()
            epoch["unlock_reason"] = str(reason or "")[:400]
            epoch["locked"] = False
            epoch["updated_at"] = _utc_now()
            epoch["unlock_seats"] = True
            epoch["seat_unlock_note"] = "vo_seats_freeze cleared with delivery epoch"
        except Exception:
            seats = dict(epoch.get("vo_seats_freeze") or {})
            seats["soft"] = False
            seats["hard"] = False
            seats["unlocked_at"] = _utc_now()
            seats["unlock_reason"] = str(reason or "")[:200]
            epoch["vo_seats_freeze"] = seats
            epoch["seat_unlock_note"] = "vo_seats_freeze cleared in-place"
    else:
        epoch["seat_unlock_note"] = "seats left frozen"

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
    music_just = bool(fields.get("music_complete_at") and not epoch.get("music_complete_at"))
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
    if music_just or fields.get("music_complete_at"):
        try:
            from interview_mux.mix_junction_seat import maybe_remaster_after_music_epoch

            maybe_remaster_after_music_epoch(ctx)
        except Exception:
            pass
    return epoch


def residual_ledger_generation(ctx: RunContext) -> int:
    """Bumpable generation for delivery residuals (EDL/junction/selection commits)."""
    try:
        epoch = read_delivery_epoch(ctx)
        gen = epoch.get("junction_residuals_generation")
        if gen is not None:
            return max(0, int(gen))
    except Exception:
        pass
    return 0


def bump_residual_ledger_generation(ctx: RunContext, *, by: int = 1) -> int:
    """Increment junction_residuals_generation on delivery_epoch."""
    cur = residual_ledger_generation(ctx)
    nxt = cur + max(1, int(by))
    stamp_delivery_epoch(ctx, junction_residuals_generation=nxt)
    return nxt


def record_delivery_residual(
    ctx: RunContext,
    *,
    kind: str,
    severity: str = "critical",
    stage: str = "",
    detail: dict[str, Any] | None = None,
    mirror_junction: bool = True,
    state: str = "open",
    producer_stage: str = "",
) -> dict[str, Any]:
    """B-02/B-03: persist residuals that ship/junction consumers must read.

    Writes ``operator/delivery_residuals.json``. Critical rows also bump
    ``critical_residual_count`` on ``master/junction_snip_qa.json`` when present
    so ``ship_path_ready`` and junction consumers share one view.

    Rows carry ``generation`` + ``state`` (open|remediated|waived|stale).
    Noop heals must not set state=remediated — only live-clean clears.
    """
    sev = str(severity or "critical").strip().lower() or "critical"
    if sev not in {"critical", "soft", "advisory"}:
        sev = "critical"
    kind_s = str(kind or "residual").strip()[:120] or "residual"
    st = str(state or "open").strip().lower() or "open"
    if st not in {"open", "remediated", "waived", "stale"}:
        st = "open"
    gen = residual_ledger_generation(ctx)
    row = {
        "at": _utc_now(),
        "kind": kind_s,
        "severity": sev,
        "stage": str(stage or "")[:80],
        "producer_stage": str(producer_stage or stage or "")[:80],
        "generation": gen,
        "state": st,
        "detail": detail if isinstance(detail, dict) else {},
    }
    doc: dict[str, Any] = {
        "version": 1,
        "residuals": [],
        "critical_count": 0,
        "generation": gen,
    }
    if ctx.artifact_exists(DELIVERY_RESIDUALS_REL):
        try:
            raw = ctx.read_json(DELIVERY_RESIDUALS_REL)
            if isinstance(raw, dict):
                doc = dict(raw)
        except Exception:
            pass
    residuals = [r for r in (doc.get("residuals") or []) if isinstance(r, dict)]
    # Dedup identical kind+stage+severity in the last few events.
    fingerprint = (
        kind_s,
        str(stage or ""),
        sev,
        str((detail or {}).get("pass_id") or (detail or {}).get("sig") or "")[:80],
    )
    for prev in residuals[-8:]:
        prev_fp = (
            str(prev.get("kind") or ""),
            str(prev.get("stage") or ""),
            str(prev.get("severity") or ""),
            str((prev.get("detail") or {}).get("pass_id") or (prev.get("detail") or {}).get("sig") or "")[
                :80
            ],
        )
        if prev_fp == fingerprint:
            return doc
    residuals.append(row)
    doc["version"] = 1
    doc["updated_at"] = _utc_now()
    doc["generation"] = gen
    doc["residuals"] = residuals[-100:]
    doc["critical_count"] = sum(
        1
        for r in doc["residuals"]
        if isinstance(r, dict)
        and str(r.get("severity") or "") == "critical"
        and str(r.get("state") or "open") == "open"
        and int(r.get("generation") or gen) >= gen
    )
    try:
        ctx.write_json(DELIVERY_RESIDUALS_REL, doc, skip_handoff=True)
    except Exception:
        pass
    if sev == "critical" and st == "open" and mirror_junction:
        try:
            _mirror_critical_residual_into_junction(ctx, row)
        except Exception:
            pass
    try:
        record_wasted_work(
            ctx,
            event=f"delivery_residual:{kind_s}",
            stage=stage or "delivery",
            detail={
                "severity": sev,
                "state": st,
                "generation": gen,
                **(detail or {}),
            },
        )
    except Exception:
        pass
    return doc


def critical_delivery_residual_count(ctx: RunContext) -> int:
    """Count critical residuals in the delivery ledger (ship gate input)."""
    if not ctx.artifact_exists(DELIVERY_RESIDUALS_REL):
        return 0
    try:
        doc = ctx.read_json(DELIVERY_RESIDUALS_REL)
    except Exception:
        return 0
    if not isinstance(doc, dict):
        return 0
    try:
        n = int(doc.get("critical_count") or 0)
        if n:
            return n
    except (TypeError, ValueError):
        pass
    return sum(
        1
        for r in (doc.get("residuals") or [])
        if isinstance(r, dict) and str(r.get("severity") or "") == "critical"
    )


@dataclass(frozen=True)
class CriticalResidualView:
    """SSOT view of critical residuals across ledger + junction dialects."""

    count: int
    kinds: tuple[str, ...]
    sources: tuple[str, ...]


def critical_residual_view(ctx: RunContext) -> CriticalResidualView:
    """Union ledger criticals, junction residual_findings, and stamped ints.

    Final count is ``max(ledger, findings, stamped)`` so a stale zero stamp
    cannot hide live findings/ledger (B-02 Wave 9 residual SSOT).

    Ledger rows with ``state`` in {stale, remediated, waived} or
    ``generation`` older than the current epoch generation do not block.
    """
    kinds: list[str] = []
    sources: list[str] = []
    ledger_n = 0
    findings_n = 0
    stamped_n = 0
    cur_gen = residual_ledger_generation(ctx)

    if ctx.artifact_exists(DELIVERY_RESIDUALS_REL):
        try:
            doc = ctx.read_json(DELIVERY_RESIDUALS_REL)
        except Exception:
            doc = None
        if isinstance(doc, dict):
            for row in doc.get("residuals") or []:
                if not isinstance(row, dict):
                    continue
                if str(row.get("severity") or "") != "critical":
                    continue
                st = str(row.get("state") or "open").strip().lower() or "open"
                if st in {"stale", "remediated", "waived"}:
                    continue
                try:
                    row_gen = int(row.get("generation") if row.get("generation") is not None else cur_gen)
                except (TypeError, ValueError):
                    row_gen = cur_gen
                if row_gen < cur_gen:
                    continue
                ledger_n += 1
                kind = str(row.get("kind") or "residual").strip() or "residual"
                if kind not in kinds:
                    kinds.append(kind)
            if ledger_n:
                sources.append("delivery_ledger")

    if ctx.artifact_exists("master/junction_snip_qa.json"):
        try:
            qa = ctx.read_json("master/junction_snip_qa.json")
        except Exception:
            qa = None
        if isinstance(qa, dict):
            # After clear_stale, reconciled reports must not poison via stale stamps.
            if qa.get("stale_incomplete_cut_reconciled") and not qa.get(
                "incomplete_cut_producer_heals_armed"
            ):
                live_kinds: list[str] = []
                for finding in qa.get("residual_findings") or []:
                    if not isinstance(finding, dict):
                        continue
                    if str(finding.get("severity") or "") != "critical":
                        continue
                    if finding.get("stale_incomplete_cut_cleared"):
                        continue
                    findings_n += 1
                    kind = (
                        str(finding.get("kind") or "junction_residual").strip()
                        or "junction_residual"
                    )
                    if kind not in kinds:
                        kinds.append(kind)
                    live_kinds.append(kind)
                if findings_n:
                    sources.append("junction_findings")
                stamped_n = findings_n
            else:
                for finding in qa.get("residual_findings") or []:
                    if not isinstance(finding, dict):
                        continue
                    if str(finding.get("severity") or "") != "critical":
                        continue
                    if finding.get("stale_incomplete_cut_cleared"):
                        continue
                    findings_n += 1
                    kind = (
                        str(finding.get("kind") or "junction_residual").strip()
                        or "junction_residual"
                    )
                    if kind not in kinds:
                        kinds.append(kind)
                if findings_n:
                    sources.append("junction_findings")
                for key in (
                    "critical_residual_count",
                    "critical_count",
                    "critical_residuals",
                ):
                    try:
                        stamped_n = max(stamped_n, int(qa.get(key) or 0))
                    except (TypeError, ValueError):
                        continue
                if stamped_n > 0:
                    sources.append("junction_count")

    count = max(ledger_n, findings_n, stamped_n)
    # Preserve source order without duplicates.
    seen_src: set[str] = set()
    uniq_sources: list[str] = []
    for s in sources:
        if s not in seen_src:
            seen_src.add(s)
            uniq_sources.append(s)
    return CriticalResidualView(
        count=int(count),
        kinds=tuple(kinds),
        sources=tuple(uniq_sources),
    )


def has_critical_residuals(ctx: RunContext) -> bool:
    """True when any residual dialect reports a critical residual."""
    try:
        return critical_residual_view(ctx).count > 0
    except Exception:
        # Callers that need fail-closed (ship) must treat exceptions as blocked.
        # Returning True is safer than False for ship honesty if view blows up.
        return True


def _mirror_critical_residual_into_junction(ctx: RunContext, row: dict[str, Any]) -> None:
    """Surface fuse/junction family residuals on junction_snip_qa when present."""
    rel = "master/junction_snip_qa.json"
    if not ctx.artifact_exists(rel):
        return
    try:
        qa = ctx.read_json(rel)
    except Exception:
        return
    if not isinstance(qa, dict):
        return
    mirrored = [r for r in (qa.get("delivery_residuals") or []) if isinstance(r, dict)]
    kind = str(row.get("kind") or "")
    findings = [f for f in (qa.get("residual_findings") or []) if isinstance(f, dict)]
    finding_row = {
        "kind": kind or "delivery_residual",
        "severity": "critical",
        "stage": str(row.get("stage") or "")[:80],
        "source": "delivery_residual_mirror",
        "detail": row.get("detail") if isinstance(row.get("detail"), dict) else {},
    }

    def _stamp_counts(min_count: int) -> None:
        try:
            crit = int(qa.get("critical_residual_count") or qa.get("critical_count") or 0)
        except (TypeError, ValueError):
            crit = 0
        crit = max(crit, int(min_count), 1)
        qa["critical_residual_count"] = crit
        qa["critical_count"] = crit
        qa["critical_residuals"] = crit

    if any(str(r.get("kind") or "") == kind for r in mirrored):
        if not any(str(f.get("kind") or "") == kind for f in findings):
            findings.append(finding_row)
            qa["residual_findings"] = findings[-80:]
        _stamp_counts(1)
        try:
            ctx.write_json(rel, qa, skip_handoff=True)
        except Exception:
            pass
        return
    mirrored.append(row)
    qa["delivery_residuals"] = mirrored[-40:]
    if not any(str(f.get("kind") or "") == kind for f in findings):
        findings.append(finding_row)
        qa["residual_findings"] = findings[-80:]
    try:
        crit = int(qa.get("critical_residual_count") or qa.get("critical_count") or 0)
    except (TypeError, ValueError):
        crit = 0
    qa["critical_residual_count"] = crit + 1
    qa["critical_count"] = int(qa["critical_residual_count"])
    qa["critical_residuals"] = int(qa["critical_residual_count"])
    try:
        ctx.write_json(rel, qa, skip_handoff=True)
    except Exception:
        pass


def record_wasted_work(
    ctx: RunContext,
    *,
    event: str,
    stage: str = "",
    detail: dict[str, Any] | None = None,
) -> bool:
    """D1: append operator/wasted_work.json event (expensive_start/orphan/avoided/…).

    Returns True when the ledger write landed (including schema_bypass via file_store).
    F-02: never silent — schema ValueError bypasses validation with a stamp; IO errors
    return False (no bare ``except: pass`` on the write path).
    """
    doc: dict[str, Any] = {"version": 1, "events": []}
    if ctx.artifact_exists(WASTED_WORK_REL):
        try:
            raw = ctx.read_json(WASTED_WORK_REL)
            if isinstance(raw, dict):
                doc = raw
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
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
            return True
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
    # TH5: count true waste in-ledger (same write) to avoid nested FileLock.
    halt_event = ""
    try:
        from interview_mux.thrash_hardening import (
            TRUE_WASTE_STICKY_HALT_AFTER,
            wasted_work_counts_toward_sticky_halt,
        )

        if wasted_work_counts_toward_sticky_halt(event, detail if isinstance(detail, dict) else None):
            counts = dict(doc.get("true_waste_counts") or {})
            key = str(event or "").strip().lower() or "waste"
            n = int(counts.get(key) or 0) + 1
            counts[key] = n
            doc["true_waste_counts"] = counts
            if n >= TRUE_WASTE_STICKY_HALT_AFTER:
                doc["true_waste_halt"] = True
                doc["true_waste_halt_event"] = key
                halt_event = key
    except Exception:
        pass
    written = False
    try:
        ctx.write_json(WASTED_WORK_REL, doc, skip_handoff=True)
        written = True
    except ValueError as exc:
        # Schema refused the row — still surface the ledger via raw file_store.
        try:
            from interview_mux.file_store import write_json as fs_write_json

            bypass = dict(doc)
            bypass["schema_bypass"] = True
            bypass["schema_bypass_at"] = _utc_now()
            bypass["schema_bypass_error"] = str(exc)[:240]
            fs_write_json(ctx.path(WASTED_WORK_REL), bypass)
            written = True
        except OSError:
            written = False
    except OSError:
        written = False
    if halt_event:
        # ESR: do not HARD-pause while producer progress / lease is fresh.
        try:
            from interview_mux.execution_status import may_hard_halt, wait_vs_halt

            pin = str(stage or "delivery")[:80] or "delivery"
            if not may_hard_halt(ctx, pin=pin):
                wait_vs_halt(
                    ctx,
                    pin=pin,
                    intent="true_waste_sticky",
                    reason=f"true_waste_sticky:{halt_event}",
                )
                halt_event = ""
        except Exception:
            pass
    if halt_event:
        try:

            def _halt(meta: dict[str, Any]) -> None:
                meta["needs_operator"] = True
                meta["needs_operator_stage"] = str(stage or "delivery")[:80] or "delivery"
                meta["needs_operator_reason"] = f"true_waste_sticky:{halt_event}"

            if ctx.artifact_exists("run_meta.json"):
                ctx.mutate_run_meta(_halt)
            else:
                ctx.write_json(
                    "run_meta.json",
                    {
                        "needs_operator": True,
                        "needs_operator_stage": str(stage or "delivery")[:80] or "delivery",
                        "needs_operator_reason": f"true_waste_sticky:{halt_event}",
                    },
                    skip_handoff=True,
                )
        except OSError:
            pass
    if event == "orphan":

        def _mark(meta: dict[str, Any]) -> None:
            meta.setdefault("delivery_epoch", {})
            if isinstance(meta["delivery_epoch"], dict):
                meta["delivery_epoch"]["orphaned_spend"] = True

        try:
            ctx.mutate_run_meta(_mark)
        except OSError:
            pass
    return written


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
    """Theme/SFX slots required for generation: cues, mix recipe, + reserved bookends.

    Speech-free theme reservations (cold_open / outro, EDL opening_music) are
    always included so lazy E3 cannot skip beds that mix will later demand.
    """
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
                    if isinstance(cue, dict) and cue.get("asset_id") and not cue.get("skip"):
                        ids.add(str(cue.get("asset_id")))
    for rel in ("master/mix_recipe.json", "sound_design/mix_recipe.json", "master/edl.json"):
        if not ctx.artifact_exists(rel):
            continue
        try:
            doc = ctx.read_json(rel)
        except Exception:
            continue
        if isinstance(doc, dict):
            for key in ("asset_ids", "theme_asset_ids", "sfx_asset_ids"):
                for aid in doc.get(key) or []:
                    ids.add(str(aid))
            for clip in doc.get("clips") or doc.get("entries") or []:
                if isinstance(clip, dict) and clip.get("asset_id"):
                    ids.add(str(clip.get("asset_id")))
    try:
        from interview_mux.theme_slot_integrity import reserved_theme_asset_ids

        ids |= reserved_theme_asset_ids(ctx)
    except Exception:
        pass
    return ids


# C1: sources that must not structurally invalidate beyond listed targets.
# VO/transition cascades deliberately exclude MUSIC_BEFORE_MIX (heal ≠ wipe seal).
_VO_EDL_MIX_CASCADE: frozenset[str] = frozenset(
    {
        "vo_line_adjudicate",
        "vo_synthesize",
        "edl_narrative_audit",
        "edl",
        "assembly_preview",
        "mix",
        "junction_snip_qa",
        "master_finalize",
        "listen_delight_audit",
    }
)
_TRANSITION_EDL_MIX_CASCADE: frozenset[str] = frozenset(
    {
        "vo_synthesize",
        "edl_narrative_audit",
        "edl",
        "assembly_preview",
        "mix",
        "junction_snip_qa",
        "master_finalize",
        "listen_delight_audit",
    }
)

INVALIDATION_BLAST_RADIUS: dict[str, frozenset[str]] = {
    "junction_snip_qa": frozenset(
        {"mix", "junction_snip_qa", "master_finalize", "listen_delight_audit"}
    ),
    "nugget_layup_compose": frozenset(
        {
            "transitions",
            "vo_synthesize",
            "edl_narrative_audit",
            "edl",
            "assembly_preview",
            "listen_delight_audit",
            "vo_line_adjudicate",
            "sound_design_vo_finalize",
        }
    ),
    "transitions_write": _TRANSITION_EDL_MIX_CASCADE,
    "transitions": _TRANSITION_EDL_MIX_CASCADE,
    "gap_report_write": _VO_EDL_MIX_CASCADE,
    "gap_report_sanitize": _VO_EDL_MIX_CASCADE,
    "air_contract_sanitize": frozenset(
        {
            "vo_synthesize",
            "edl_narrative_audit",
            "edl",
            "assembly_preview",
        }
    ),
    "sound_design_plan": frozenset(
        {
            "music_palette_compose",
            "sfx_prompt_craft",
            "mmaudio_sfx",
        }
    ),
    "vo_line_adjudicate": frozenset(
        {
            "vo_synthesize",
            "edl_narrative_audit",
            "edl",
            "assembly_preview",
            "mix",
            "junction_snip_qa",
            "master_finalize",
            "listen_delight_audit",
        }
    ),
    "edl": frozenset(
        {
            "edl",
            "assembly_preview",
            "mix",
            "junction_snip_qa",
            "master_finalize",
            "listen_delight_audit",
        }
    ),
    "mmaudio_sfx": frozenset(
        {
            "mmaudio_sfx",
            "mix",
            "junction_snip_qa",
            "master_finalize",
            "listen_delight_audit",
        }
    ),
    "listen_delight_audit": frozenset(
        {"listen_delight_audit", "junction_snip_qa", "master_finalize"}
    ),
    "assembly_seating_stale": frozenset(
        {"edl", "assembly_preview", "mix", "junction_snip_qa", "master_finalize"}
    ),
}


def invalidation_allowed_downstream(source: str, target: str) -> bool:
    """Whether ``source`` may clear/invalidate ``target`` when structural."""
    allowed = INVALIDATION_BLAST_RADIUS.get(source)
    if allowed is None:
        return True
    return target in allowed or target.split("/")[0] in {t.split("/")[0] for t in allowed}


def music_clear_blocked(ctx: RunContext, target: str, *, source: str = "") -> bool:
    """True when clearing ``target`` would wipe a sealed music epoch (heal ≠ waive)."""
    sid = str(target or "").strip()
    if sid not in MUSIC_BEFORE_MIX and sid != "sound_design_plan":
        return False
    epoch = read_delivery_epoch(ctx)
    if epoch.get("music_seal_broken_at"):
        return False
    if epoch.get("music_complete_at") or music_epoch_complete(ctx):
        return True
    src = str(source or "").strip()
    if src in {
        "transitions_write",
        "transitions",
        "gap_report_write",
        "vo_line_adjudicate",
        "edl",
        "nugget_layup_compose",
        "assembly_seating_stale",
        "listen_delight_audit",
        "junction_snip_qa",
    }:
        return sid in MUSIC_BEFORE_MIX or sid == "sound_design_plan"
    return False


def break_music_epoch_seal(ctx: RunContext, reason: str) -> dict[str, Any]:
    """Named unlock to allow MUSIC_BEFORE_MIX unmark / full MusicGen re-entry.

    Delight fail, seating_stale, and VO cascades must not imply seal break.
    """
    reason_s = str(reason or "").strip() or "unspecified"
    stamp_delivery_epoch(
        ctx,
        music_seal_broken_at=_utc_now(),
        music_seal_break_reason=reason_s[:240],
    )
    # Clear completed stamp so mix waiters re-enter music producers.
    try:

        def _clear(meta: dict[str, Any]) -> None:
            epoch = dict(meta.get("delivery_epoch") or {})
            epoch.pop("music_complete_at", None)
            epoch["music_seal_broken_at"] = _utc_now()
            epoch["music_seal_break_reason"] = reason_s[:240]
            epoch["updated_at"] = _utc_now()
            meta["delivery_epoch"] = epoch

        if ctx.artifact_exists("run_meta.json"):
            ctx.mutate_run_meta(_clear)
    except Exception:
        pass
    try:
        record_wasted_work(
            ctx,
            event="music_seal_break",
            stage="mmaudio_sfx",
            detail={"reason": reason_s[:240]},
        )
    except Exception:
        pass
    return {"ok": True, "reason": reason_s}


def resolve_music_limbo_exit(ctx: RunContext) -> dict[str, Any]:
    """MU3: exit music limbo via omit-bed + music_omitted **or** break-seal + pin.

    Limbo = Phase A sealed, music epoch incomplete, fail_closed blocks stubs.
    Prefer honest omit when MU1 omit path is available; otherwise break seal and
    pin the earliest incomplete music producer.
    """
    out: dict[str, Any] = {"resolved": False, "path": "", "pin": ""}
    if not phase_a_sealed(ctx):
        return out
    if music_epoch_complete(ctx):
        out["resolved"] = True
        out["path"] = "already_complete"
        return out
    try:
        from interview_mux.musicgen_runner import fail_closed_on_stub
        from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

        if not fail_closed_on_stub():
            return out
        missing = [str(a) for a in missing_sdp_asset_wavs(ctx) if a]
    except Exception:
        missing = []
    if not missing:
        return out
    # Speech-free bookends: prefer regenerate (pin mmaudio) over silent omit.
    try:
        from interview_mux.theme_slot_integrity import (
            is_speech_free_theme_role,
            speech_free_palette_asset_ids,
        )

        palette_sf = speech_free_palette_asset_ids(ctx)
        speech_free_missing = []
        sdp = {}
        if ctx.artifact_exists("understanding/sound_design_plan.json"):
            try:
                sdp = ctx.read_json("understanding/sound_design_plan.json") or {}
            except Exception:
                sdp = {}
        role_by_id = {
            str(a.get("asset_id")): str(a.get("role") or "")
            for a in (sdp.get("assets") or [])
            if isinstance(a, dict) and a.get("asset_id")
        }
        for aid in missing:
            if aid in palette_sf or is_speech_free_theme_role(role_by_id.get(aid)):
                speech_free_missing.append(aid)
        if speech_free_missing:
            pin = "mmaudio_sfx"
            break_music_epoch_seal(
                ctx, reason=f"music_limbo_bookend:{','.join(speech_free_missing[:4])}"
            )
            try:

                def _pin_bookend(meta: dict[str, Any]) -> None:
                    meta["needs_operator"] = True
                    meta["needs_operator_stage"] = pin
                    meta["needs_operator_reason"] = "music_limbo_speech_free_regen"

                if ctx.artifact_exists("run_meta.json"):
                    ctx.mutate_run_meta(_pin_bookend)
            except Exception:
                pass
            out["resolved"] = True
            out["path"] = "break_seal_bookend"
            out["pin"] = pin
            out["omitted"] = []
            record_wasted_work(
                ctx,
                event="music_limbo_pin_mmaudio",
                stage="mmaudio_sfx",
                detail={"asset_ids": speech_free_missing[:12]},
            )
            return out
    except Exception as exc:
        out["bookend_pin_error"] = str(exc)[:200]
    # Path A: stamp omit ledger for other missing beds + shrink reservations.
    try:
        from interview_mux.musicgen_runner import stamp_music_omitted
        from interview_mux.theme_slot_integrity import shrink_theme_reservations_for_omit

        for aid in missing[:12]:
            stamp_music_omitted(ctx, asset_id=aid, reason="music_limbo_omit")
        shrink = shrink_theme_reservations_for_omit(ctx, missing[:12])
        out["resolved"] = True
        out["path"] = "music_omitted"
        out["omitted"] = missing[:12]
        out["shrink"] = shrink
        record_wasted_work(
            ctx,
            event="music_limbo_omit",
            stage="mmaudio_sfx",
            detail={"asset_ids": missing[:12], "shrink": shrink},
        )
        return out
    except Exception as exc:
        out["omit_error"] = str(exc)[:200]
    # Path B: break seal + pin earliest incomplete music producer.
    pin = "mmaudio_sfx"
    try:
        for sid in MUSIC_BEFORE_MIX:
            if not seed_stage_complete(ctx, sid):
                pin = sid
                break
    except Exception:
        pin = "mmaudio_sfx"
    break_music_epoch_seal(ctx, reason=f"music_limbo_break:{','.join(missing[:4])}")
    try:

        def _pin(meta: dict[str, Any]) -> None:
            meta["needs_operator"] = True
            meta["needs_operator_stage"] = pin
            meta["needs_operator_reason"] = "music_limbo_break_seal"

        if ctx.artifact_exists("run_meta.json"):
            ctx.mutate_run_meta(_pin)
    except Exception:
        pass
    out["resolved"] = True
    out["path"] = "break_seal"
    out["pin"] = pin
    return out


def freeze_air_order(ctx: RunContext, *, reason: str = "edl_commit") -> dict[str, Any]:
    """Stamp air-order freeze after first successful EDL / green preview."""
    epoch = read_delivery_epoch(ctx)
    if epoch.get("air_order_frozen_at"):
        return {"ok": True, "already": True, "frozen_at": epoch.get("air_order_frozen_at")}
    stamp_delivery_epoch(
        ctx,
        air_order_frozen_at=_utc_now(),
        air_order_freeze_reason=str(reason or "edl_commit")[:240],
    )
    return {"ok": True, "frozen": True}


def unlock_air_order_freeze(ctx: RunContext, reason: str) -> dict[str, Any]:
    """Named unlock so optimizer remaster may promote mid-delivery."""
    reason_s = str(reason or "").strip() or "unspecified"

    def _mark(meta: dict[str, Any]) -> None:
        epoch = dict(meta.get("delivery_epoch") or {})
        epoch.pop("air_order_frozen_at", None)
        epoch["air_order_unlocked_at"] = _utc_now()
        epoch["air_order_unlock_reason"] = reason_s[:240]
        epoch["updated_at"] = _utc_now()
        meta["delivery_epoch"] = epoch

    if ctx.artifact_exists("run_meta.json"):
        ctx.mutate_run_meta(_mark)
    return {"ok": True, "reason": reason_s}


def air_order_frozen(ctx: RunContext) -> bool:
    return bool(read_delivery_epoch(ctx).get("air_order_frozen_at"))


def generate_missing_referenced_music_assets(ctx: RunContext) -> list[str]:
    """Generate MusicGen only for referenced ∩ missing WAVs — never full theme regen."""
    from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

    missing = [str(a) for a in missing_sdp_asset_wavs(ctx) if a]
    if not missing:
        return []
    refs = referenced_musicgen_asset_ids(ctx)
    targets = [a for a in missing if not refs or a in refs]
    if not targets:
        return []
    try:
        from interview_mux.stages.sfx_mmaudio import generate_missing_music_assets_only

        return list(generate_missing_music_assets_only(ctx, targets) or [])
    except ImportError:
        try:
            from interview_mux.stages import sfx_mmaudio as _sfx

            if hasattr(_sfx, "_set_regen_asset_ids"):
                _sfx._set_regen_asset_ids(ctx, targets)
        except Exception:
            pass
        return []


def refuse_skip_then_consume(ctx: RunContext, consumer: str) -> str | None:
    """Host refuse when a producer was skipped without compensating artifacts."""
    sid = str(consumer or "").strip()
    if not sid:
        return None
    try:
        from interview_mux.homunculus.agenda import stage_outputs_present, _read_agenda

        doc = _read_agenda(ctx)
        skipped = {str(s) for s in (doc.get("skipped") or [])}
    except Exception:
        return None
    if sid in skipped and not stage_outputs_present(ctx, sid):
        return f"skip_then_consume:{sid}"
    pairs = (
        ("vo_synthesize", "edl"),
        ("vo_line_adjudicate", "vo_synthesize"),
        ("edl", "mix"),
        ("edl", "assembly_preview"),
        ("mmaudio_sfx", "mix"),
        ("transitions", "vo_synthesize"),
        ("nugget_layup_compose", "vo_synthesize"),
    )
    for producer, consumer in pairs:
        if consumer != sid:
            continue
        if producer in skipped and not stage_outputs_present(ctx, producer):
            return f"skip_then_consume:{producer}->{consumer}"
    return None




def ship_path_ready(ctx: RunContext) -> tuple[bool, str]:
    """Late-phase pin: mix sealed, junction seed-complete + commitment, delight ok.

    Missing ``junction_snip_qa.json`` must not look ship-ready — that dropped
    junction from ``filter_delivery_candidates`` and thrashed finalize↔junction
    (forensics exec_10066: pending master.wav + stale autopsy commitment).

    Soft residuals are advisory only; only **critical** residuals block ship-ready.
    Autopsy commitment must match live assembly (size + sha when present).
    """
    if not ctx.artifact_exists("master/assembly.wav"):
        return False, "assembly_missing"
    try:
        from interview_mux.homunculus.agenda import (
            _junction_commitment_matches_assembly,
            assembly_stale_versus_edl,
        )

        if assembly_stale_versus_edl(ctx):
            return False, "assembly_stale_versus_edl"
    except Exception:
        _junction_commitment_matches_assembly = None  # type: ignore[assignment]
    if not seed_stage_complete(ctx, "mix"):
        return False, "mix_incomplete"
    if not seed_stage_complete(ctx, "junction_snip_qa"):
        return False, "junction_incomplete"
    try:
        if _junction_commitment_matches_assembly and not _junction_commitment_matches_assembly(
            ctx
        ):
            return False, "junction_commitment_mismatch"
    except Exception:
        pass
    if not ctx.artifact_exists("master/junction_snip_qa.json"):
        # Defense in depth: autopsy-only seed must not look ship-ready.
        return False, "junction_qa_missing"
    if not listen_delight_cleared_for_progress(ctx):
        return False, "listen_delight_incomplete"
    # B-02 Wave 9: one SSOT for ledger + junction findings + stamped ints.
    # Fail closed on check errors — never fail-open past critical residuals.
    try:
        view = critical_residual_view(ctx)
        if view.count > 0:
            if "delivery_ledger" in view.sources:
                return False, "critical_delivery_residuals"
            return False, "critical_junction_residuals"
    except Exception:
        return False, "critical_residual_check_failed"
    if ctx.artifact_exists("master/post_master_quality.json"):
        # HPUB-1: unreadable envelope fail-closes. e2e_soft may still walk
        # encode/cover/publish when publish_allowed is false (operator 1C).
        # Filter still keys off this result (3A). Dead extra keys unused.
        try:
            from interview_mux.e2e_soft import e2e_soft_enabled

            pmq = ctx.read_json("master/post_master_quality.json")
            if not isinstance(pmq, dict):
                return False, "pmq_not_publishable"
            if pmq.get("publish_allowed") is False and not e2e_soft_enabled():
                return False, "pmq_not_publishable"
        except Exception:
            return False, "pmq_not_publishable"
    # Bare master.wav without commitment is not ship-ready (RSTM committed-master-honesty).
    try:
        from interview_mux.delivery_invariants import committed_master_wav

        if ctx.artifact_exists("master/master.wav") and not committed_master_wav(ctx):
            return False, "master_uncommitted"
    except Exception:
        pass
    return True, ""


def remote_publish_allowed(ctx: RunContext) -> tuple[bool, str]:
    """S3/RSS must not follow the e2e_soft local-walk waiver (HPUB-1)."""
    if not ctx.artifact_exists("master/post_master_quality.json"):
        return False, "pmq_missing"
    try:
        pmq = ctx.read_json("master/post_master_quality.json")
    except Exception:
        return False, "pmq_not_publishable"
    if not isinstance(pmq, dict):
        return False, "pmq_not_publishable"
    if pmq.get("publish_allowed") is not True:
        return False, "pmq_not_publishable"
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

            # DETECTION_ONLY_IS_DONE: fingerprint emission — actual skip is gated
            # by may_skip_as_complete in homunculus/runtime dispatch.
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
