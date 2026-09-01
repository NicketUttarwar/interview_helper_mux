"""Canonical operator-gate semantics for GUI, journey, and homunculus."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from interview_mux.run_context import RunContext

GateSeverity = Literal["hard_block", "optional", "automation_pending", "advisory"]
GateStageStatus = Literal["action_required", "pending", "done", "automation_pending", "locked"]


@dataclass(frozen=True)
class GateAutomation:
    owner: str = ""
    active: bool = False
    action: str = ""
    state: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v}


@dataclass(frozen=True)
class GateOperatorView:
    gate_id: str
    open: bool = False
    severity: GateSeverity = "advisory"
    operator_must_act: bool = False
    stage_status: GateStageStatus = "pending"
    blocks_journey: bool = False
    blocks_delivery_sidebar: bool = False
    ui_mode: str = ""
    message: str = ""
    automation: GateAutomation = field(default_factory=GateAutomation)

    def to_dict(self) -> dict[str, Any]:
        out = {
            "gate_id": self.gate_id,
            "open": self.open,
            "severity": self.severity,
            "operator_must_act": self.operator_must_act,
            "stage_status": self.stage_status,
            "blocks_journey": self.blocks_journey,
            "blocks_delivery_sidebar": self.blocks_delivery_sidebar,
            "ui_mode": self.ui_mode,
            "message": self.message,
        }
        auto = self.automation.to_dict()
        if auto:
            out["automation"] = auto
        return out


def _run_meta(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists("run_meta.json"):
        return {}
    raw = ctx.read_json("run_meta.json")
    return raw if isinstance(raw, dict) else {}


def _driver_active(meta: dict[str, Any]) -> bool:
    from interview_mux.automation_run import automation_driver_run

    if not automation_driver_run(meta):
        return False
    if meta.get("partial_auto_complete"):
        return False
    if meta.get("partial_auto_driver_active"):
        return True
    if meta.get("full_auto"):
        return True
    return automation_driver_run(meta)


def _needs_operator_on(meta: dict[str, Any], gate_id: str) -> bool:
    if not meta.get("needs_operator"):
        return False
    stage = str(meta.get("needs_operator_stage") or "").lower()
    gid = gate_id.lower()
    if stage == gid:
        return True
    aliases = {
        "g1_vo_pickup": ("g1", "g1_vo", "vo_pickup"),
        "transcript_review": ("transcript_review_build", "g0"),
        "missing_framing": ("gap_framing", "framing"),
    }
    return stage in aliases.get(gid, ())


def _all_missing_are_synthesize(ctx: RunContext, missing: list[str]) -> bool:
    if not missing or not ctx.artifact_exists("understanding/gap_report.json"):
        return False
    report = ctx.read_json("understanding/gap_report.json")
    by_id: dict[str, dict[str, Any]] = {}
    for line in report.get("interviewer_lines") or []:
        if isinstance(line, dict) and line.get("line_id"):
            by_id[str(line["line_id"])] = line
    for lid in missing:
        line = by_id.get(lid)
        if not line or str(line.get("delivery") or "").lower() != "synthesize":
            return False
    return True


def resolve_transcript_review_gate(ctx: RunContext, meta: dict[str, Any]) -> GateOperatorView:
    from interview_mux.gates import check_transcript_review_pending

    pending = check_transcript_review_pending(ctx)
    if not pending:
        return GateOperatorView(
            gate_id="transcript_review",
            open=False,
            stage_status="done",
        )
    return GateOperatorView(
        gate_id="transcript_review",
        open=True,
        severity="hard_block",
        operator_must_act=True,
        stage_status="action_required",
        blocks_journey=True,
        blocks_delivery_sidebar=True,
        ui_mode="transcript_review",
        message="G0 transcript review pending — correct STT before continuing.",
    )


def resolve_g1_vo_gate(
    ctx: RunContext,
    job: dict[str, Any] | None,
    meta: dict[str, Any],
) -> GateOperatorView:
    from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
    from interview_mux.gates import check_g1_vo
    from interview_mux.v2.config import v2_g1_optional

    _ = job
    if gap_fill_was_skipped(ctx):
        return GateOperatorView(gate_id="g1_vo_pickup", open=False, stage_status="done")

    missing = check_g1_vo(ctx)
    if not missing:
        return GateOperatorView(gate_id="g1_vo_pickup", open=False, stage_status="done")

    optional = v2_g1_optional()
    driver_active = _driver_active(meta)
    all_synthesize = _all_missing_are_synthesize(ctx, missing)

    chatterbox = False
    voice_ref_ok = False
    synth_fallback = False
    try:
        from interview_mux.gap_vo_gates import (
            gap_framing_enabled,
            resolve_gap_vo_delivery,
            voice_reference_approved,
        )
        from interview_mux.synthesis_fallback import synthesis_fallback_notice

        if gap_framing_enabled(ctx):
            chatterbox = resolve_gap_vo_delivery(ctx) == "chatterbox"
            voice_ref_ok = voice_reference_approved(ctx)
        synth_fallback = bool(synthesis_fallback_notice(ctx))
    except Exception:
        pass

    g1_auto_state = str(meta.get("g1_automation_state") or "")

    if synth_fallback or _needs_operator_on(meta, "g1_vo_pickup"):
        return GateOperatorView(
            gate_id="g1_vo_pickup",
            open=True,
            severity="hard_block",
            operator_must_act=True,
            stage_status="action_required",
            blocks_journey=True,
            blocks_delivery_sidebar=True,
            ui_mode="record",
            message=f"G1 VO pickup needs operator action ({len(missing)} line(s) missing).",
        )

    if (
        optional
        and driver_active
        and all_synthesize
        and chatterbox
        and voice_ref_ok
    ):
        return GateOperatorView(
            gate_id="g1_vo_pickup",
            open=True,
            severity="automation_pending",
            operator_must_act=False,
            stage_status="automation_pending",
            blocks_journey=False,
            blocks_delivery_sidebar=False,
            ui_mode="synthesize_pending",
            message=f"Synthesizing {len(missing)} gap VO line(s) (Chatterbox) — no action needed.",
            automation=GateAutomation(
                owner="driver",
                active=True,
                action="synthesize_all",
                state=g1_auto_state or "pending",
            ),
        )

    if optional:
        return GateOperatorView(
            gate_id="g1_vo_pickup",
            open=True,
            severity="optional",
            operator_must_act=False,
            stage_status="pending",
            blocks_journey=False,
            blocks_delivery_sidebar=False,
            ui_mode="optional_skip",
            message=f"Optional: {len(missing)} gap VO line(s) — record, synthesize, or skip.",
        )

    return GateOperatorView(
        gate_id="g1_vo_pickup",
        open=True,
        severity="hard_block",
        operator_must_act=True,
        stage_status="action_required",
        blocks_journey=True,
        blocks_delivery_sidebar=True,
        ui_mode="record",
        message=f"G1 VO pickup missing for {len(missing)} line(s).",
    )


def resolve_framing_gate(ctx: RunContext, meta: dict[str, Any]) -> GateOperatorView:
    from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
    from interview_mux.gap_vo_gates import (
        check_gap_delivery_pending,
        check_gap_framing_decision_pending,
        check_voice_reference_pending,
        gap_framing_enabled,
    )
    from interview_mux.source_topology import check_pickup_speaker_pending

    if gap_fill_was_skipped(ctx) or not gap_framing_enabled(ctx):
        return GateOperatorView(gate_id="missing_framing", open=False, stage_status="done")

    framing_pending = check_gap_framing_decision_pending(ctx)
    speaker_pending = check_pickup_speaker_pending(ctx)
    voice_pending = check_voice_reference_pending(ctx)
    delivery_pending = check_gap_delivery_pending(ctx)

    if not any((framing_pending, speaker_pending, voice_pending, delivery_pending)):
        if ctx.is_done("missing_framing"):
            return GateOperatorView(gate_id="missing_framing", open=False, stage_status="done")
        return GateOperatorView(gate_id="missing_framing", open=False, stage_status="pending")

    driver_active = _driver_active(meta)
    auto_defaults = bool(meta.get("auto_accept_defaults"))
    if driver_active and (framing_pending or speaker_pending or voice_pending or delivery_pending):
        if not _needs_operator_on(meta, "missing_framing"):
            return GateOperatorView(
                gate_id="missing_framing",
                open=True,
                severity="automation_pending",
                operator_must_act=False,
                stage_status="automation_pending",
                blocks_journey=False,
                ui_mode="framing_automation",
                message="Gap framing gates resolving automatically.",
                automation=GateAutomation(
                    owner="driver",
                    active=True,
                    action="accept_gap_defaults" if auto_defaults else "resolve_framing",
                    state="pending",
                ),
            )

    if framing_pending:
        return GateOperatorView(
            gate_id="missing_framing",
            open=True,
            severity="hard_block",
            operator_must_act=True,
            stage_status="action_required",
            blocks_journey=True,
            ui_mode="framing_choice",
            message="Gap framing decision pending — choose Yes or No.",
        )

    if speaker_pending:
        return GateOperatorView(
            gate_id="missing_framing",
            open=True,
            severity="hard_block",
            operator_must_act=True,
            stage_status="action_required",
            blocks_journey=True,
            ui_mode="pickup_speaker",
            message="Confirm gap pickup speaker.",
        )

    if voice_pending or delivery_pending:
        return GateOperatorView(
            gate_id="missing_framing",
            open=True,
            severity="hard_block",
            operator_must_act=True,
            stage_status="action_required",
            blocks_journey=True,
            ui_mode="voice_ref_or_delivery",
            message="Approve voice reference or select gap delivery path.",
        )

    return GateOperatorView(gate_id="missing_framing", open=False, stage_status="pending")


def build_operator_gates(
    ctx: RunContext,
    job: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    meta = meta if isinstance(meta, dict) else _run_meta(ctx)
    gates = {
        "transcript_review": resolve_transcript_review_gate(ctx, meta),
        "g1_vo_pickup": resolve_g1_vo_gate(ctx, job, meta),
        "missing_framing": resolve_framing_gate(ctx, meta),
    }
    return {gid: view.to_dict() for gid, view in gates.items()}


def g1_journey_clear(ctx: RunContext, meta: dict[str, Any] | None = None) -> bool:
    """True when G1 must not block operator journey (optional or automation-owned)."""
    meta = meta if isinstance(meta, dict) else _run_meta(ctx)
    view = resolve_g1_vo_gate(ctx, None, meta)
    return not view.blocks_journey


def g1_stage_status(ctx: RunContext, meta: dict[str, Any] | None = None) -> GateStageStatus:
    meta = meta if isinstance(meta, dict) else _run_meta(ctx)
    return resolve_g1_vo_gate(ctx, None, meta).stage_status


def framing_stage_status(ctx: RunContext, meta: dict[str, Any] | None = None) -> GateStageStatus:
    meta = meta if isinstance(meta, dict) else _run_meta(ctx)
    return resolve_framing_gate(ctx, meta).stage_status
