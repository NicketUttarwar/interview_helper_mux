"""Operator gates for gap framing path (G-Framing, G-Delivery, G-VoiceRef)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Literal

from interview_mux.config import merged_config
from interview_mux.conversation_context import role_is_frame
from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
from interview_mux.run_context import RunContext
from interview_mux.source_topology import (
    load_flow_adaptation,
    pickup_eligible_speaker_id,
    pickup_speaker_confirmed,
)

GapVoDelivery = Literal["chatterbox", "record"]


def gap_fill_cfg_block(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = (cfg or merged_config()).get("analysis") or {}
    raw = analysis.get("gap_fill") or {}
    defaults = {
        "enabled": True,
        "default_framing_enabled": True,
        "require_explicit_opt_in": True,
        "auto_accept_defaults": False,
        "succinct_master_default": True,
        "auto_skip_when_ineligible": False,
        "frame_confidence_min": 0.65,
        "hide_gui_stages_when_skipped": True,
    }
    if isinstance(raw, dict):
        return {**defaults, **raw}
    return defaults


def auto_accept_gap_gate_defaults_enabled(cfg: dict[str, Any] | None = None) -> bool:
    """True for unattended / E2E runs that may apply product defaults without a human."""
    env = os.environ.get("INTERVIEW_MUX_AUTO_ACCEPT_GATES", "").strip().lower()
    if env in {"1", "true", "yes", "on"}:
        return True
    return bool(gap_fill_cfg_block(cfg).get("auto_accept_defaults", False))


def _run_meta(ctx: RunContext) -> dict[str, Any]:
    if ctx.artifact_exists("run_meta.json"):
        doc = ctx.read_json("run_meta.json")
        if isinstance(doc, dict):
            return doc
    return {}


def gap_framing_enabled(ctx: RunContext) -> bool:
    if gap_fill_was_skipped(ctx):
        return False
    meta = _run_meta(ctx)
    if "gap_framing_enabled" in meta:
        return bool(meta.get("gap_framing_enabled"))
    adapt = load_flow_adaptation(ctx) or {}
    overrides = adapt.get("operator_overrides") or {}
    if "gap_framing_enabled" in overrides:
        return bool(overrides.get("gap_framing_enabled"))
    return bool(gap_fill_cfg_block().get("default_framing_enabled", True))


def recommended_gap_framing_enabled() -> bool:
    """Product default offered at G-Framing (operator must still confirm unless auto-accept)."""
    return bool(gap_fill_cfg_block().get("default_framing_enabled", True))


def set_gap_framing_enabled(ctx: RunContext, enabled: bool) -> None:
    from interview_mux.gap_fill_eligibility import clear_gap_fill_skip
    from interview_mux.stages.gaps import ensure_gap_fill_skipped

    def patch(meta: dict[str, Any]) -> None:
        meta["gap_framing_enabled"] = enabled
        if enabled:
            meta["gap_fill_mode"] = "active"
            meta.pop("gap_fill_skip_reason", None)
        else:
            meta["gap_fill_mode"] = "skipped"

    ctx.mutate_run_meta(patch)
    adapt = load_flow_adaptation(ctx) or {}
    overrides = dict(adapt.get("operator_overrides") or {})
    overrides["gap_framing_enabled"] = enabled
    if not enabled:
        overrides["gap_fill_skipped"] = True
    else:
        overrides.pop("gap_fill_skipped", None)
    adapt["operator_overrides"] = overrides
    ctx.write_json("understanding/flow_adaptation.json", adapt, skip_handoff=True)
    try:
        from interview_mux.pipeline_mode import persist_pipeline_mode

        if enabled:
            persist_pipeline_mode(
                ctx,
                "framing_full",
                decided_by="operator_g_framing",
                reason_codes=["gap_framing_yes"],
            )
        else:
            persist_pipeline_mode(
                ctx,
                "native_only",
                decided_by="operator_g_framing",
                reason_codes=["gap_framing_no"],
            )
    except Exception:
        pass
    if enabled:
        clear_gap_fill_skip(ctx, reason="operator_enabled_gap_framing")
    else:
        ensure_gap_fill_skipped(
            ctx,
            reason="gap_framing_disabled_by_operator",
            signals={"skip_signal": "gap_framing_no"},
        )


def resolve_gap_vo_delivery(ctx: RunContext) -> GapVoDelivery:
    meta = _run_meta(ctx)
    raw = str(meta.get("gap_vo_delivery") or "").strip().lower()
    if raw in {"chatterbox", "record"}:
        return raw  # type: ignore[return-value]
    from interview_mux.gap_framing import gap_vo_cfg

    default = str(gap_vo_cfg().get("default_delivery", "chatterbox")).lower()
    return "chatterbox" if default == "chatterbox" else "record"


def set_gap_vo_delivery(ctx: RunContext, delivery: str) -> None:
    d = str(delivery or "").strip().lower()
    if d not in {"chatterbox", "record"}:
        raise ValueError("delivery must be chatterbox or record")

    def patch(meta: dict[str, Any]) -> None:
        meta["gap_vo_delivery"] = d

    ctx.mutate_run_meta(patch)


def voice_reference_approved(ctx: RunContext) -> bool:
    meta = _run_meta(ctx)
    if meta.get("voice_reference_approved_at"):
        return True
    speaker_id = pickup_eligible_speaker_id(ctx)
    if not speaker_id:
        return False
    rel = f"understanding/voice_reference/{speaker_id}.json"
    if not ctx.artifact_exists(rel):
        return False
    doc = ctx.read_json(rel)
    return isinstance(doc, dict) and bool(doc.get("approved"))


def check_gap_framing_decision_pending(ctx: RunContext) -> bool:
    """True when operator has not chosen yes/no for gap framing."""
    if gap_fill_was_skipped(ctx):
        return False
    meta = _run_meta(ctx)
    if "gap_framing_enabled" in meta:
        return False
    adapt = load_flow_adaptation(ctx) or {}
    overrides = adapt.get("operator_overrides") or {}
    if "gap_framing_enabled" in overrides:
        return False
    if not ctx.is_done("source_topology_build"):
        return False
    from interview_mux.pipeline import ANALYSIS_ORDER

    idx = ANALYSIS_ORDER.index("missing_framing")
    for sid in ANALYSIS_ORDER[:idx]:
        if not ctx.is_done(sid):
            return False
    return True


def check_gap_delivery_pending(ctx: RunContext) -> bool:
    if not gap_framing_enabled(ctx):
        return False
    if not voice_reference_approved(ctx):
        return False
    meta = _run_meta(ctx)
    return "gap_vo_delivery" not in meta


def check_voice_reference_pending(ctx: RunContext) -> bool:
    if not gap_framing_enabled(ctx):
        return False
    # No pickup-eligible speaker determined yet (topology/adaptation not built) — nothing to
    # approve, mirrors the prerequisite guard in check_pickup_speaker_pending.
    if pickup_eligible_speaker_id(ctx) is None:
        return False
    if not pickup_speaker_confirmed(ctx):
        return True
    return not voice_reference_approved(ctx)


def require_gap_framing_decision_clear(ctx: RunContext) -> None:
    if check_gap_framing_decision_pending(ctx):
        # Full-auto / Homunculus: stamp the decision before SystemExit so the
        # driver is not stuck behind sticky needs_operator while the gate is open.
        try:
            if maybe_auto_accept_gap_gate_defaults(ctx) and not check_gap_framing_decision_pending(
                ctx
            ):
                return
        except Exception:
            pass
        raise SystemExit(
            "Gap framing gate: choose whether to add interviewer framing audio in the GUI "
            f"→ {ctx.path('run_meta.json')}"
        )


def require_gap_path_clear(ctx: RunContext) -> None:
    from interview_mux.source_topology import require_pickup_speaker_clear

    if not gap_framing_enabled(ctx):
        return
    require_pickup_speaker_clear(ctx)
    if check_voice_reference_pending(ctx):
        raise SystemExit(
            "Voice reference gate: approve interviewer voice sample before gap framing LLM stages."
        )
    if check_gap_delivery_pending(ctx):
        raise SystemExit(
            "Gap delivery gate: choose Chatterbox clone or record-as-interviewer before gap framing."
        )
    require_clone_consent_clear(ctx)


def mark_voice_reference_approved(ctx: RunContext, speaker_id: str) -> None:
    from interview_mux.conversation_context import load_conversation_context

    conv = load_conversation_context(ctx)
    sp = conv.speaker_by_id.get(speaker_id) or {}
    role = str(sp.get("role") or "")
    if not role_is_frame(role):
        raise ValueError(f"Speaker {speaker_id} is not a frame role ({role})")
    rel = f"understanding/voice_reference/{speaker_id}.json"
    doc = ctx.read_json(rel) if ctx.artifact_exists(rel) else {"speaker_id": speaker_id}
    if not isinstance(doc, dict):
        doc = {"speaker_id": speaker_id}
    doc["approved"] = True
    doc["approved_at"] = datetime.now(timezone.utc).isoformat()
    ctx.write_json(rel, doc)

    def patch(meta: dict[str, Any]) -> None:
        meta["voice_reference_approved_at"] = doc["approved_at"]

    ctx.mutate_run_meta(patch)


def clone_consent_required(ctx: RunContext) -> bool:
    """Chatterbox delivery synthesizes the pickup voice, so it needs clone consent."""
    if not gap_framing_enabled(ctx):
        return False
    return resolve_gap_vo_delivery(ctx) == "chatterbox"


def check_clone_consent_pending(ctx: RunContext) -> bool:
    from interview_mux.mastering_voice_clone import consent_active, load_consent

    if not clone_consent_required(ctx):
        return False
    if not voice_reference_approved(ctx):
        return False
    return not consent_active(load_consent(ctx))


def require_clone_consent_clear(ctx: RunContext) -> None:
    from interview_mux.mastering_hardening_config import gate_blocks

    if not gate_blocks("voice_clone"):
        return
    if check_clone_consent_pending(ctx):
        raise SystemExit(
            "Voice clone gate: record clone consent and usage scope in the GUI before "
            "synthesizing pickup VO — docs/cross-cutting/mastering-voice-clone-policy.md"
        )


def maybe_auto_accept_gap_gate_defaults(ctx: RunContext) -> bool:
    """Apply product defaults for unattended / E2E / Homunculus auto-resolve Yes."""
    homunculus_auto = False
    try:
        from interview_mux.homunculus.gates import recommended_framing_action
        from interview_mux.homunculus.runtime import has_homunculus_features

        homunculus_auto = (
            has_homunculus_features(ctx) and recommended_framing_action(ctx) == "auto_resolve"
        )
    except Exception:
        homunculus_auto = False
    if not auto_accept_gap_gate_defaults_enabled() and not homunculus_auto:
        return False

    applied = False
    if check_gap_framing_decision_pending(ctx):
        enabled = recommended_gap_framing_enabled()
        try:
            from interview_mux.gap_fill_eligibility import (
                assess_gap_fill_eligibility,
                silent_skip_allowed,
            )

            decision = assess_gap_fill_eligibility(ctx)
            if silent_skip_allowed(decision):
                enabled = False
        except Exception:
            pass
        rec = ""
        try:
            from interview_mux.homunculus.gates import recommended_framing_action

            rec = recommended_framing_action(ctx)
        except Exception:
            rec = ""
        set_gap_framing_enabled(ctx, enabled)
        applied = True
        # Honor the set_gate_decision guard: recommended skip cannot auto_resolve.
        framing_action = "skip" if (not enabled or rec == "skip") else "auto_resolve"
        try:
            from interview_mux.homunculus.gates import try_set_gate_decision

            try_set_gate_decision(ctx, "framing_consent", framing_action)
        except Exception:
            pass
        ctx.log(
            f"Gap framing auto-accepted (defaults): {'enabled' if enabled else 'disabled'}",
            level="action",
            stage="missing_framing",
            detail={
                "kind": "gate",
                "action_id": "auto.gap_framing.accept_defaults",
                "gap_framing_enabled": enabled,
            },
        )

    if not gap_framing_enabled(ctx):
        return applied

    from interview_mux.source_topology import (
        check_pickup_speaker_pending,
        confirm_pickup_speaker,
    )

    if check_pickup_speaker_pending(ctx):
        try:
            from interview_mux.source_topology import resolve_clone_host_speaker_id

            host_id = resolve_clone_host_speaker_id(ctx)
            if host_id:
                confirm_pickup_speaker(ctx, speaker_id=host_id)
            else:
                raise ValueError("no_frame_speaker_for_clone")
            applied = True
            ctx.log(
                "Pickup speaker auto-confirmed (frame / question-density host)",
                level="action",
                stage="missing_framing",
                detail={"kind": "gate", "action_id": "auto.adaptation.pickup_speaker"},
            )
        except Exception as exc:
            ctx.log(
                f"Pickup speaker auto-confirm skipped: {exc}",
                level="warning",
                stage="missing_framing",
            )
            return applied

    if check_voice_reference_pending(ctx):
        from interview_mux.source_topology import (
            clone_host_auto_approve_allowed,
            resolve_clone_host_speaker_id,
        )

        speaker_id = resolve_clone_host_speaker_id(ctx) or pickup_eligible_speaker_id(ctx)
        if speaker_id and clone_host_auto_approve_allowed(ctx, speaker_id):
            try:
                from interview_mux.voice_reference import approve_voice_reference

                approve_voice_reference(ctx, speaker_id)
                applied = True
                ctx.log(
                    f"Voice reference auto-approved for {speaker_id}",
                    level="action",
                    stage="missing_framing",
                    detail={"kind": "gate", "action_id": "auto.voice_reference.approve"},
                )
            except Exception as exc:
                ctx.log(
                    f"Voice reference auto-approve skipped: {exc}",
                    level="warning",
                    stage="missing_framing",
                )
                return applied
        else:
            ctx.log(
                "no_frame_speaker_for_clone — not auto-approving voice reference",
                level="warning",
                stage="missing_framing",
                action_id="auto.voice_reference.blocked",
            )
            return applied

    if check_gap_delivery_pending(ctx):
        from interview_mux.gap_framing import gap_vo_cfg

        default = str(gap_vo_cfg().get("default_delivery", "chatterbox")).lower()
        delivery: GapVoDelivery = "chatterbox" if default == "chatterbox" else "record"
        set_gap_vo_delivery(ctx, delivery)
        applied = True
        ctx.log(
            f"Gap VO delivery auto-accepted: {delivery}",
            level="action",
            stage="missing_framing",
            detail={"kind": "gate", "action_id": "auto.gap_delivery.accept_defaults"},
        )

    if check_clone_consent_pending(ctx):
        speaker_id = pickup_eligible_speaker_id(ctx)
        if speaker_id:
            try:
                from interview_mux.mastering_voice_clone import VALID_SCOPES, grant_consent

                grant_consent(
                    ctx,
                    speaker_id=speaker_id,
                    scopes=list(VALID_SCOPES),
                    granted_by="auto_accept_defaults",
                    disclosure="none",
                )
                applied = True
                ctx.log(
                    f"Voice clone consent auto-granted for {speaker_id}",
                    level="action",
                    stage="missing_framing",
                    detail={"kind": "gate", "action_id": "auto.voice_clone.consent"},
                )
            except Exception as exc:
                ctx.log(
                    f"Voice clone consent auto-grant skipped: {exc}",
                    level="warning",
                    stage="missing_framing",
                )

    return applied


def global_gap_runtime_fields() -> dict[str, Any]:
    """Machine-global gap/VO runtime probes — cached; safe to call rarely."""
    from interview_mux.synthesis_fallback import chatterbox_runtime_available

    return {
        "chatterbox_runtime_available": chatterbox_runtime_available(),
        "auto_accept_defaults": auto_accept_gap_gate_defaults_enabled(),
    }


def gap_gate_payload_for_run(ctx: RunContext) -> dict[str, Any]:
    """Per-run gap gate fields (no subprocess probes)."""
    from interview_mux.mastering_voice_clone import consent_payload
    from interview_mux.synthesis_fallback import synthesis_fallback_notice

    llm_recommended: str | None = None
    llm_rationale: str | None = None
    if ctx.artifact_exists("understanding/framing_posture_decision.json"):
        try:
            doc = ctx.read_json("understanding/framing_posture_decision.json")
            if isinstance(doc, dict):
                llm_recommended = str(doc.get("recommended_framing") or "") or None
                llm_rationale = str(doc.get("rationale") or doc.get("summary") or "") or None
        except Exception:
            pass

    pipeline_mode: dict[str, Any] | None = None
    try:
        from interview_mux.pipeline_mode import resolve_effective_mode

        pipeline_mode = resolve_effective_mode(ctx)
    except Exception:
        pipeline_mode = None

    return {
        **consent_payload(ctx),
        "clone_consent_required": clone_consent_required(ctx),
        "clone_consent_pending": check_clone_consent_pending(ctx),
        "gap_framing_enabled": gap_framing_enabled(ctx),
        "gap_framing_decision_pending": check_gap_framing_decision_pending(ctx),
        "recommended_gap_framing_enabled": recommended_gap_framing_enabled(),
        "llm_recommended_framing": llm_recommended,
        "llm_framing_rationale": llm_rationale,
        "pipeline_mode": pipeline_mode,
        "gap_vo_delivery": resolve_gap_vo_delivery(ctx) if gap_framing_enabled(ctx) else None,
        "gap_delivery_pending": check_gap_delivery_pending(ctx),
        "voice_reference_pending": check_voice_reference_pending(ctx),
        "voice_reference_approved": voice_reference_approved(ctx),
        "pickup_speaker_confirmed": pickup_speaker_confirmed(ctx),
        "pickup_eligible_speaker_id": pickup_eligible_speaker_id(ctx),
        "synthesis_fallback_notice": synthesis_fallback_notice(ctx),
    }


def gap_gate_payload(ctx: RunContext) -> dict[str, Any]:
    """Full gap gate payload for dedicated gap-framing API routes."""
    return {**gap_gate_payload_for_run(ctx), **global_gap_runtime_fields()}
