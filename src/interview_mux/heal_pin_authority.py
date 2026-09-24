"""Admit Constitution — heal pin + leapfrog resume (Heal Clinic E + B+).

Flow: propose → clamp_resume_through_order → wrong_pin E allowlist+checklist
→ ``admit_resume`` / ``admit_schedule``.

Public APIs:
- ``resolve_heal_from_stage`` / ``heal_navigate`` — heal pin (E + clamp + admit)
- ``admit_resume`` — remutate / recovery / driver ``from_stage`` rewrites
- ``admit_schedule`` / ``stage_minimum_run_checklist`` — agenda enqueue gate

Mode-wide SSOT — Partial and Full-auto share the same allowlist + checklist.
Disable only for emergency: ``HEAL_PIN_AUTHORITY=0``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

_STAGE_ORDER: frozenset[str] = frozenset(ANALYSIS_ORDER) | frozenset(DELIVERY_ORDER)

# Operator gates / non-seed resume targets that are legal heal landings.
_HEAL_EXTRA_LANDINGS: frozenset[str] = frozenset(
    {
        "transcript_review",
        "framing_confirm",
        "gap_vo_confirm",
        "preclean_offer",
        "g_publish",
    }
)

_KNOWN_LANDINGS: frozenset[str] = _STAGE_ORDER | _HEAL_EXTRA_LANDINGS

# Narrow allowlist ids (operator-owned via Heal Clinic verdict E).
# Matching is by intent token or error/stage blob substrings — not free prose.
HEAL_PIN_ALLOWLIST_IDS: frozenset[str] = frozenset(
    {
        "g0_pending",
        "voice_reference_pending",
        "high_gap_unframed",
        "fuse_oscillation",
        "vo_audibility_drift",
        "authority_denied",
        "heard_wav_flow",
        "pre_edl_qc_producer",
        "music_epoch",
        "mix_seat",
        "finalize_inputs",
        "phase_a_edl",
        "delivery_blocked",
        "vo_g1",
        "hosted_vo_hollow",
        "incomplete_after_conductor",
        "mastering_shape_llm_hollow",
        "seed_order_prereq",
        "premature_complete",
        "incomplete_cut",
        "producer_pin_table",
        # Structured stage pin via premature_complete:stage:<id>
        "premature_complete_stage",
        # Controlled execute/driver cap (not free-form prose heal)
        "premature_cap",
        # W1 selection / gap sanitize incompleteness (HR-4)
        "w1_sanitize_unsanitary",
        # HR-2: layup/air CTA selection commit refuse pins the writer
        "selection_commit_refused",
        # Host CTA omit recovery must land on layup, not clamp to package plan
        "selection_cta_omit",
    }
)

# Substring → allowlist id (first hit wins; order = specificity).
_BLOB_ALLOWLIST_PATTERNS: tuple[tuple[str, str], ...] = (
    ("g0_pending", "g0_pending"),
    ("transcript review required", "g0_pending"),
    ("transcript review gate", "g0_pending"),
    ("voice_reference_pending", "voice_reference_pending"),
    ("voice reference gate", "voice_reference_pending"),
    ("approve interviewer voice", "voice_reference_pending"),
    ("high_gap_unframed", "high_gap_unframed"),
    ("high gap segment", "high_gap_unframed"),
    ("fuse_oscillation", "fuse_oscillation"),
    ("connector_fuse_oscillation", "fuse_oscillation"),
    ("authority_denied", "authority_denied"),
    ("selection_commit_refused", "selection_commit_refused"),
    ("vo_audibility_drift", "vo_audibility_drift"),
    ("edl_survivor_wipe", "vo_audibility_drift"),
    ("phantom_vo", "vo_audibility_drift"),
    ("opening_orientation_inaudible", "vo_audibility_drift"),
    ("never_touch_zeroed_keep", "vo_audibility_drift"),
    ("heard_wav_flow", "heard_wav_flow"),
    ("pre-edl delivery qc incomplete", "pre_edl_qc_producer"),
    ("e2e_stub", "pre_edl_qc_producer"),
    ("premature_complete", "premature_complete"),
    ("mix_unseated", "mix_seat"),
    ("mix_outputs_seated", "mix_seat"),
    ("music_incomplete", "music_epoch"),
    ("music epoch", "music_epoch"),
    ("incomplete_cut", "incomplete_cut"),
    ("on_a_roll", "incomplete_cut"),
    ("seed_order", "seed_order_prereq"),
    ("seed order", "seed_order_prereq"),
    ("g1_vo", "vo_g1"),
    ("vo_g1", "vo_g1"),
    ("g1_incomplete", "vo_g1"),
    ("hosted_vo", "hosted_vo_hollow"),
    ("no synthesize lines", "hosted_vo_hollow"),
    ("hollow_zero", "hosted_vo_hollow"),
    ("hosted_vo_floor_unmet", "hosted_vo_hollow"),
    # HR-2 before W1: refuse strings embed sanitize_refused:selection in the detail.
    ("selection_commit_refused", "selection_commit_refused"),
    ("selection_cta_omit", "selection_cta_omit"),
    ("host_cta_omit", "selection_cta_omit"),
    ("cta_omit_applied", "selection_cta_omit"),
    ("selection_unsanitary", "w1_sanitize_unsanitary"),
    ("selection still unsanitary", "w1_sanitize_unsanitary"),
    ("sanitize_refused:selection", "w1_sanitize_unsanitary"),
    ("gap still unsanitary", "w1_sanitize_unsanitary"),
    ("sanitize_refused:gap_report", "w1_sanitize_unsanitary"),
)


@dataclass(frozen=True)
class HealPinDecision:
    """Result of authorize / resolve_heal_from_stage."""

    from_stage: str
    intent: str
    mode: str
    allowed: bool
    allowlist_id: str
    refused_reason: str
    rewritten: bool
    proposed_stage: str

    def as_navigate_dict(self) -> dict[str, str]:
        out: dict[str, str] = {
            "from_stage": self.from_stage,
            "intent": self.intent,
            "mode": self.mode,
        }
        if self.refused_reason:
            out["heal_refused"] = self.refused_reason
            out["heal_allowlist_id"] = self.allowlist_id or ""
        return out


def heal_pin_authority_enabled(*, meta: dict[str, Any] | None = None) -> bool:
    env = str(os.environ.get("HEAL_PIN_AUTHORITY", "1") or "1").strip().lower()
    if env in {"0", "false", "no", "off"}:
        return False
    if isinstance(meta, dict) and meta.get("heal_pin_authority") in {False, 0, "0", "false"}:
        return False
    return True


def match_heal_allowlist(
    *,
    error: str = "",
    stage: str = "",
    intent: str = "",
) -> str | None:
    """Return allowlist id if this heal may attempt a pin rewrite; else None."""
    intent_l = str(intent or "").strip().lower()
    if intent_l in HEAL_PIN_ALLOWLIST_IDS:
        return intent_l
    # Canonical fail-class intents
    if intent_l in {
        "music",
        "mix",
        "finalize",
        "master_finalize",
        "phase_a",
        "vo",
    }:
        mapped = {
            "music": "music_epoch",
            "mix": "mix_seat",
            "finalize": "finalize_inputs",
            "master_finalize": "finalize_inputs",
            "phase_a": "phase_a_edl",
            "vo": "vo_g1",
        }[intent_l]
        return mapped

    blob = f"{error} {stage} {intent}".strip().lower()
    if not blob:
        return None

    if re.search(r"premature_complete:stage:[a-z0-9_]+", blob):
        return "premature_complete_stage"

    for needle, allow_id in _BLOB_ALLOWLIST_PATTERNS:
        if needle in blob:
            return allow_id
    return None


def heal_prereq_checklist(
    ctx: RunContext,
    target_stage: str,
    *,
    allowlist_id: str = "",
) -> tuple[bool, str]:
    """Minimum run checklist before a heal may land on ``target_stage``."""
    sid = str(target_stage or "").strip()
    if not sid:
        return False, "empty_target"
    if sid not in _KNOWN_LANDINGS:
        return False, f"unknown_stage:{sid}"

    # Sealed consumers: never heal-land on edl/mix/master_finalize when that
    # consumer is already seed-complete (wrong-pin thrash onto sealed work).
    if sid in {"edl", "mix", "master_finalize"}:
        try:
            from interview_mux.delivery_guardrails import seed_stage_complete

            if seed_stage_complete(ctx, sid):
                return False, f"sealed_consumer:{sid}"
        except Exception:
            pass

    # Specialty / cap paths already chose a producer — only unknown/sealed gates.
    # Full MUST_PRECEDE walk applies to free-form heal_navigate rewrites.
    _loose = {
        "premature_cap",
        "g0_pending",
        "voice_reference_pending",
        "high_gap_unframed",
        "fuse_oscillation",
        "vo_audibility_drift",
        "heard_wav_flow",
        "pre_edl_qc_producer",
        "incomplete_cut",
        "w1_sanitize_unsanitary",
        "selection_commit_refused",
        "selection_cta_omit",
    }
    if str(allowlist_id or "").strip() in _loose:
        return True, "ok"

    try:
        from interview_mux.delivery_guardrails import (
            clamp_resume_through_order,
            earliest_incomplete_must_precede,
        )

        clamped = str(clamp_resume_through_order(ctx, sid) or sid).strip() or sid
        if clamped != sid:
            return False, f"must_precede_hole:{clamped}"
        hole = earliest_incomplete_must_precede(ctx, sid)
        if hole and str(hole).strip() and str(hole).strip() != sid:
            return False, f"upstream_incomplete:{hole}"
    except Exception as exc:
        return False, f"checklist_error:{type(exc).__name__}"

    return True, "ok"


def stage_minimum_run_checklist(ctx: RunContext, stage_id: str) -> tuple[bool, str]:
    """Happy-path gate: may this stage be scheduled without inviting heal thrash?

    Uses the **full** MUST_PRECEDE checklist (never the loose specialty set).
    """
    return heal_prereq_checklist(ctx, stage_id, allowlist_id="")


def admit_resume(
    ctx: RunContext,
    stage: str,
    *,
    current: str = "",
    error: str = "",
    intent: str = "",
) -> str:
    """Admit Constitution (leapfrog B+): clamp, then wrong_pin E if sideways.

    Public API for remutate / recovery / driver ``from_stage`` rewrites.
    """
    raw = str(stage or "").strip()
    if not raw:
        return ""
    allow_id = match_heal_allowlist(error=error, stage=current or raw, intent=intent)
    skip_clamp = allow_id == "w1_sanitize_unsanitary" and raw in {
        "selection_order_sanitize",
        "gap_report_sanitize",
        "full_master_ranking",
    } or (
        allow_id in {"selection_commit_refused", "selection_cta_omit"}
        and raw in {"nugget_layup_compose", "air_script_compose"}
    )
    try:
        from interview_mux.delivery_guardrails import clamp_resume_through_order

        if skip_clamp:
            clamped = raw
        else:
            clamped = str(clamp_resume_through_order(ctx, raw) or raw).strip() or raw
    except Exception:
        clamped = raw

    cur = str(current or "").strip()
    if not cur or clamped == cur:
        return clamped

    ok, _allow_id, _refused = may_rewrite_heal_pin(
        ctx,
        from_stage=cur,
        to_stage=clamped,
        error=error,
        intent=intent,
    )
    if ok:
        return clamped
    # Sideways refused — still collapse *current* if it itself leapfrogs.
    try:
        from interview_mux.delivery_guardrails import clamp_resume_through_order

        cur_clamped = str(clamp_resume_through_order(ctx, cur) or cur).strip() or cur
        return cur_clamped
    except Exception:
        return cur


def admit_schedule(ctx: RunContext, stage_id: str) -> tuple[bool, str, str]:
    """Admit Constitution (schedule): may ``stage_id`` be enqueued?

    Returns ``(ok, stage_or_hole, reason)``. When not ok, ``stage_or_hole`` is the
    producer to prefer (MUST_PRECEDE hole) when available.
    """
    sid = str(stage_id or "").strip()
    if not sid:
        return False, "", "empty_stage"
    try:
        from interview_mux.delivery_guardrails import (
            clamp_resume_through_order,
            earliest_incomplete_must_precede,
        )

        clamped = str(clamp_resume_through_order(ctx, sid) or sid).strip() or sid
        if clamped != sid:
            return False, clamped, f"must_precede_hole:{clamped}"
        hole = earliest_incomplete_must_precede(ctx, sid)
        if hole and str(hole).strip() and str(hole).strip() != sid:
            return False, str(hole).strip(), f"upstream_incomplete:{hole}"
    except Exception as exc:
        return False, sid, f"admit_schedule_error:{type(exc).__name__}"

    ok, reason = stage_minimum_run_checklist(ctx, sid)
    if not ok:
        return False, sid, reason
    return True, sid, "ok"


def may_rewrite_heal_pin(
    ctx: RunContext,
    *,
    from_stage: str,
    to_stage: str,
    error: str = "",
    intent: str = "",
) -> tuple[bool, str, str]:
    """Return (ok, allowlist_id_or_empty, refused_reason_or_empty)."""
    src = str(from_stage or "").strip()
    dst = str(to_stage or "").strip()
    if not dst or dst == src:
        return True, "", ""

    if not heal_pin_authority_enabled():
        return True, "authority_disabled", ""

    allow_id = match_heal_allowlist(error=error, stage=src or dst, intent=intent)
    if not allow_id:
        try:
            from interview_mux.thrash_hardening import premature_fail_class

            # Error text only — never classify using stage ids (mix→mix_seat).
            cls = str(premature_fail_class(str(error or "")) or "").strip()
            if cls in HEAL_PIN_ALLOWLIST_IDS:
                allow_id = cls
        except Exception:
            allow_id = None
    if not allow_id:
        return False, "", "heal_refuse:not_allowlisted"

    ok, reason = heal_prereq_checklist(ctx, dst, allowlist_id=allow_id or "")
    if not ok:
        return False, allow_id, f"heal_refuse:checklist:{reason}"
    return True, allow_id, ""


def authorize_heal_navigate_result(
    ctx: RunContext,
    proposed: dict[str, str],
    *,
    error: str = "",
    stage: str = "",
    intent: str = "",
) -> dict[str, str]:
    """Gate a heal_navigate proposal — refuse-by-default sideways pins."""
    prop = dict(proposed or {})
    proposed_stage = str(prop.get("from_stage") or "").strip()
    stay = str(stage or "").strip()
    intent_out = str(prop.get("intent") or intent or "").strip()
    mode = str(prop.get("mode") or "delivery").strip() or "delivery"

    if not heal_pin_authority_enabled():
        return prop

    # Structured premature / token pins beat incompleteness walks that clamp to
    # early seed stages on empty fixtures (wrong_pin determinism).
    blob_l = f"{error} {intent}".strip().lower()
    if "premature_complete" in blob_l or match_heal_allowlist(
        error=error, stage=stage, intent=intent
    ) in {
        "vo_g1",
        "music_epoch",
        "mix_seat",
        "finalize_inputs",
        "phase_a_edl",
        "delivery_blocked",
        "premature_complete",
        "premature_complete_stage",
    }:
        try:
            from interview_mux.stage_completion import producer_pin_for_token

            tok = str(producer_pin_for_token(error or intent, ctx=ctx) or "").strip()
            if tok and tok in _KNOWN_LANDINGS:
                proposed_stage = tok
                prop["from_stage"] = tok
                if not prop.get("intent"):
                    prop["intent"] = str(intent or "premature_complete")
        except Exception:
            pass

    # Leapfrog B+: always clamp before authority — even for loose allowlist ids.
    # Exception: W1 sanitize pins must land on the sanitize stage itself (HR-4);
    # clamping to incomplete ranking would thrash away from the sanitary writer.
    try:
        from interview_mux.delivery_guardrails import clamp_resume_through_order

        allow_pre = match_heal_allowlist(error=error, stage=stage, intent=intent)
        skip_clamp = allow_pre == "w1_sanitize_unsanitary" and proposed_stage in {
            "selection_order_sanitize",
            "gap_report_sanitize",
            "full_master_ranking",
        } or (
            allow_pre in {"selection_commit_refused", "selection_cta_omit"}
            and proposed_stage in {"nugget_layup_compose", "air_script_compose"}
        )
        if proposed_stage and not skip_clamp:
            clamped = (
                str(clamp_resume_through_order(ctx, proposed_stage) or proposed_stage).strip()
                or proposed_stage
            )
            if clamped != proposed_stage:
                prop["heal_clamped_from"] = proposed_stage
                proposed_stage = clamped
                prop["from_stage"] = clamped
    except Exception:
        pass

    rewritten = bool(proposed_stage and stay and proposed_stage != stay)
    # Also treat empty stay + any pin as a rewrite attempt when error present
    if not stay and proposed_stage and (error or intent):
        rewritten = True

    if not rewritten:
        return prop

    ok, allow_id, refused = may_rewrite_heal_pin(
        ctx,
        from_stage=stay,
        to_stage=proposed_stage,
        error=error,
        # Caller intent only — never trust proposed navigator intent (it invents
        # music_epoch/etc. for unknown errors and would defeat refuse-by-default).
        intent=intent,
    )
    if ok:
        prop["from_stage"] = proposed_stage
        if allow_id:
            prop["heal_allowlist_id"] = allow_id
        return prop

    # Refuse: stay on current stage when it is a known stage id.
    stay_stage = stay if stay in _KNOWN_LANDINGS else ""
    return {
        "from_stage": stay_stage,
        "intent": "heal_refused",
        "mode": "delivery" if stay_stage in DELIVERY_ORDER else "analysis",
        "heal_refused": refused or "heal_refuse:unknown",
        "heal_allowlist_id": allow_id or "",
        "heal_proposed": proposed_stage,
    }


def resolve_heal_from_stage(
    ctx: RunContext,
    *,
    error: str = "",
    stage: str = "",
    intent: str = "",
) -> dict[str, str]:
    """SSOT: propose → authorize (E) with clamp (B+) → admit_resume."""
    from interview_mux.thrash_hardening import _heal_navigate_ungated

    proposed = _heal_navigate_ungated(
        ctx, error=error, stage=stage, intent=intent
    )
    authorized = authorize_heal_navigate_result(
        ctx, proposed, error=error, stage=stage, intent=intent
    )
    # Refuse-stay is Option E contract — do not clamp the refused landing away.
    if str(authorized.get("intent") or "") == "heal_refused":
        return authorized
    # Final admit pass (idempotent clamp + sideways gate vs current stage).
    landed = str(authorized.get("from_stage") or "").strip()
    if landed:
        admitted = admit_resume(
            ctx,
            landed,
            current=str(stage or "").strip(),
            error=error,
            intent=intent,
        )
        if admitted != landed:
            authorized = dict(authorized)
            authorized["from_stage"] = admitted
            authorized["heal_admitted_from"] = landed
    return authorized
