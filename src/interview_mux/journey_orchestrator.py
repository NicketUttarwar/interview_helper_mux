"""Journey snapshot: phase, next_action, blocking, execute hints — single source for GUI and docs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.config import merged_config
from interview_mux.gates import (
    check_disfluency_review_pending,
    check_g1_vo,
    check_profile_gate_pending,
    check_transcript_review_pending,
    get_selected_flow,
)
from interview_mux.journey_log import log_journey
from interview_mux.journey_state import (
    OPERATOR_PHASES,
    compute_milestones,
    compute_operator_phase,
    get_flow_intent,
    read_run_meta,
    stage_operator_phase,
)
from interview_mux.operator_quality import PRECLEAN_CHECKPOINTS
from interview_mux.sonic_context import load_sonic_context
from interview_mux.custom_run_handoff import (
    handoff_between_stages_enabled,
    pending_handoff_stage,
)
from interview_mux.run_context import RunContext

# Canonical operator strings — must match docs/workflows/operator-journey.md appendix.
# Keep scannable; execute_hint.label is the primary CTA when not blocked.
NEXT_ACTION_PREPARE_G0 = "Review STT clips (low confidence first)"
NEXT_ACTION_PREPARE_RUN = "Prepare transcript for review"
NEXT_ACTION_UNDERSTAND_RUN = "Run understanding analysis"
NEXT_ACTION_UNDERSTAND_PROFILE = "Review AI story profile"
NEXT_ACTION_UNDERSTAND_INVESTIGATIONS = "Resolve open questions in Story Board"
NEXT_ACTION_COMPLETE_G1 = "Record pickup lines"
NEXT_ACTION_COMPLETE_G2 = "Confirm output type"
NEXT_ACTION_CREATE_FLOW1 = "Build episode order → preview"
NEXT_ACTION_CREATE_FLOW2 = "Select highlight clips"
NEXT_ACTION_CREATE_FLOW3 = "Generate show description"
NEXT_ACTION_POLISH_PREVIEW = "Listen to preview, then approve sound"
NEXT_ACTION_G1_5_PREVIEW_PICKUP = "Re-record post-preview pickup lines"
NEXT_ACTION_POLISH_CRAFT = "Review and approve SFX prompts"
NEXT_ACTION_POLISH_GENERATE = "Generate SFX assets"
NEXT_ACTION_POLISH_LISTEN = "Complete post-listen QA"
NEXT_ACTION_POLISH_PLACEMENT = "Review placement adjustments"
NEXT_ACTION_POLISH_SFX = "Add sound and mix"
NEXT_ACTION_SHIP_MASTER = "Export master"
NEXT_ACTION_SHIP_DESC = "Export show description"
NEXT_ACTION_DONE = "Deliverable ready — listen or export"

SOUND_LABELS = ("pace_class", "bed_density", "stinger_policy")


def _journey_cfg() -> dict[str, Any]:
    cfg = merged_config()
    row = cfg.get("journey_ui")
    return row if isinstance(row, dict) else {}


def _require_preview_listen() -> bool:
    return bool(_journey_cfg().get("require_preview_listen", False))


def refresh_journey_meta(ctx: RunContext) -> dict[str, Any]:
    """Persist operator_phase and milestones on run_meta."""
    milestones = compute_milestones(ctx)
    phase = compute_operator_phase(ctx, milestones)
    meta = read_run_meta(ctx)
    meta["operator_phase"] = phase
    meta["operator_phase_updated_at"] = datetime.now(timezone.utc).isoformat()
    meta["journey_milestones"] = milestones
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    return meta


def emit_journey_milestone(ctx: RunContext, name: str) -> None:
    meta = read_run_meta(ctx)
    milestones = meta.get("journey_milestones")
    if not isinstance(milestones, dict):
        milestones = {}
    milestones[name] = True
    meta["journey_milestones"] = milestones
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    log_journey(ctx, "milestone", f"Journey milestone: {name}", stage="journey")


def _review_queue_low_confidence_count(ctx: RunContext) -> int:
    if not ctx.artifact_exists("transcript/review_queue.json"):
        return 0
    queue = ctx.read_json("transcript/review_queue.json")
    chunks = queue.get("chunks") or queue.get("clips") or []
    if not isinstance(chunks, list):
        return 0
    return sum(1 for c in chunks if isinstance(c, dict) and (c.get("confidence") or 1) < 0.85)


def _blocking_manifest_propagation_count(ctx: RunContext) -> int:
    if not ctx.artifact_exists("understanding/investigation_queue.json"):
        return 0
    queue = ctx.read_json("understanding/investigation_queue.json")
    items = queue.get("items") or queue.get("investigations") or []
    if not isinstance(items, list):
        return 0
    return sum(
        1
        for it in items
        if isinstance(it, dict)
        and it.get("blocking")
        and str(it.get("kind") or "") == "manifest_propagation"
        and (it.get("status") or "open") in ("open", "pending", "needs")
    )


def _open_investigation_count(ctx: RunContext) -> int:
    if not ctx.artifact_exists("understanding/investigation_queue.json"):
        return 0
    queue = ctx.read_json("understanding/investigation_queue.json")
    items = queue.get("items") or queue.get("investigations") or []
    if not isinstance(items, list):
        return 0
    return sum(
        1
        for it in items
        if isinstance(it, dict) and (it.get("status") or "open") in ("open", "pending", "needs")
    )


def _open_coherence_risk_count(ctx: RunContext) -> int:
    from interview_mux.analysis_memory import load_analysis_state

    state = load_analysis_state(ctx)
    risks = state.get("coherence_risks") or []
    if not isinstance(risks, list):
        return 0
    return sum(1 for r in risks if isinstance(r, dict) and r.get("status", "open") == "open")


def _blocking_coherence_contradiction_count(ctx: RunContext) -> int:
    from interview_mux.analysis_memory import load_analysis_state

    state = load_analysis_state(ctx)
    risks = state.get("coherence_risks") or []
    if not isinstance(risks, list):
        return 0
    return sum(
        1
        for r in risks
        if isinstance(r, dict)
        and r.get("status", "open") == "open"
        and r.get("kind") == "claim_contradiction"
        and r.get("blocking")
    )


def _recommended_preclean(ctx: RunContext, phase: str, milestones: dict[str, bool]) -> str | None:
    from interview_mux.operator_quality import preclean_checkpoint_decision

    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if phase == "prepare" and not ctx.is_done("ingest"):
        if ctx.is_done("audio_preclean"):
            return None
        if preclean_checkpoint_decision(meta, "before_ingest") == "dismiss":
            return None
        return "before_ingest"
    if phase == "complete" and not milestones.get("g1_complete"):
        g1_missing = check_g1_vo(ctx)
        if g1_missing:
            if preclean_checkpoint_decision(meta, "g1_vo_pickup") == "dismiss":
                return None
            return "g1_vo_pickup"
    return None


def _next_pending_stage_ids(ctx: RunContext) -> list[str]:
    from interview_mux.pipeline import ANALYSIS_ORDER, FLOW1_ORDER, FLOW2_ORDER, FLOW3_ORDER
    from interview_mux.gates import get_selected_flow

    order: list[str] = list(ANALYSIS_ORDER)
    flow = get_selected_flow(ctx)
    if flow == "flow1":
        order.extend(FLOW1_ORDER)
    elif flow == "flow2":
        order.extend(FLOW2_ORDER)
    elif flow == "flow3":
        order.extend(FLOW3_ORDER)
    return [sid for sid in order if not ctx.is_done(sid)]


def _blocking(
    ctx: RunContext,
    *,
    job: dict[str, Any] | None,
    milestones: dict[str, bool],
) -> dict[str, Any]:
    blocked = False
    reason: str | None = None
    message = ""
    stage_id: str | None = None
    reuse_candidates_payload: list[dict[str, Any]] | None = None

    if job and job.get("status") in (
        "gate",
        "needs_operator",
        "awaiting_write_approval",
        "needs_clarification",
    ):
        blocked = True
        stage_id = job.get("pending_write_stage") or job.get("stage")
        gate_msg_early = str(job.get("message") or "")
        if job.get("status") == "gate":
            from interview_mux.gate_focus import gate_focus_stage

            focused = gate_focus_stage(gate_msg_early, job_stage=str(stage_id or ""))
            if focused:
                stage_id = focused
        if job.get("status") == "awaiting_write_approval":
            reason = "write_approval"
            message = "Awaiting your review"
        elif job.get("status") == "needs_clarification":
            reason = "artifact_clarification"
            message = str(job.get("message") or "Resolve artifact issues before saving")
        elif job.get("needs_stage_reuse"):
            reason = "stage_reuse"
            message = "Choose reuse or run fresh"
        else:
            gate_msg = str(job.get("message") or "Operator action required")
            if job.get("status") == "gate" and _is_llm_gate_message(gate_msg):
                reason = "llm_gate"
            else:
                reason = str(stage_id or job.get("status"))
            message = gate_msg

    if check_transcript_review_pending(ctx):
        blocked = True
        reason = "transcript_review"
        stage_id = "transcript_review"
        n = _review_queue_low_confidence_count(ctx)
        message = (
            f"Review {n} ranked STT clips" if n else NEXT_ACTION_PREPARE_G0
        )

    if not blocked and check_disfluency_review_pending(ctx):
        blocked = True
        reason = "disfluency_review"
        stage_id = "disfluency_review"
        doc = ctx.read_json("transcript/disfluencies.json")
        pending = sum(
            1
            for e in (doc.get("events") or [])
            if isinstance(e, dict) and e.get("review_status") == "pending"
        )
        message = f"Review {pending} filler event(s)" if pending else "Complete disfluency review"

    g1_missing = check_g1_vo(ctx)
    if g1_missing and ctx.artifact_exists("understanding/gap_report.json"):
        blocked = True
        reason = "g1_vo_pickup"
        stage_id = "g1_vo_pickup"
        message = f"Record {len(g1_missing)} pickup line(s) for gap-fill"

    if not blocked:
        from interview_mux.gates_tbiy import check_g1_5_preview_pickup_pending

        g1_5_pending = check_g1_5_preview_pickup_pending(ctx)
        if g1_5_pending:
            blocked = True
            reason = "g1_5_preview_pickup"
            stage_id = "g1_5_preview_pickup"
            message = f"Re-record {len(g1_5_pending)} post-preview pickup line(s)"

    if not blocked:
        from interview_mux.source_topology import check_pickup_speaker_pending

        if check_pickup_speaker_pending(ctx):
            blocked = True
            reason = "pickup_speaker"
            stage_id = "missing_framing"
            message = "Confirm gap pickup speaker before gap evaluation"

    if not blocked and check_profile_gate_pending(ctx):
        blocked = True
        reason = "analysis_profile"
        stage_id = "analysis_profile"
        message = NEXT_ACTION_UNDERSTAND_PROFILE

    if not blocked and _blocking_manifest_propagation_count(ctx) > 0:
        from interview_mux.full_autopilot import full_autopilot_enabled

        if not full_autopilot_enabled():
            blocked = True
            reason = "downstream_propagation"
            stage_id = stage_id or "segment_classification"
            message = "Downstream stages stale after artifact fix — open propagation wizard"

    if not blocked:
        from interview_mux.full_autopilot import full_autopilot_enabled

        if full_autopilot_enabled():
            from interview_mux.operator_decisions import pending_decision_count

            pending = _next_pending_stage_ids(ctx)
            for sid in pending[:3]:
                count = pending_decision_count(ctx, sid)
                if count > 0:
                    blocked = True
                    reason = "operator_decisions"
                    stage_id = sid
                    message = f"Your input needed ({count} decision{'s' if count != 1 else ''})"
                    break

    if not blocked:
        from interview_mux.progression_spine import (
            first_incomplete_p0_stage,
            p0_stage_remediation,
        )
        from interview_mux.web.stages import operator_linear_stage_ids

        p0 = first_incomplete_p0_stage(ctx)
        if p0:
            pending = _next_pending_stage_ids(ctx)
            if pending:
                flow = get_selected_flow(ctx)
                order = operator_linear_stage_ids(flow)
                try:
                    p0_idx = order.index(p0)
                    pend_idx = order.index(pending[0])
                    if pend_idx > p0_idx:
                        blocked = True
                        reason = "upstream_incomplete"
                        stage_id = p0
                        message = p0_stage_remediation(ctx, p0)
                except ValueError:
                    pass

    if not blocked:
        from interview_mux.stage_execution_reuse import (
            reuse_candidates_if_undecided,
            stage_reuse_offers_enabled,
        )

        if stage_reuse_offers_enabled():
            pending = _next_pending_stage_ids(ctx)
            # Only the next pipeline stage can block on reuse; scanning every
            # pending stage re-reads hundreds of prior executions per poll.
            if pending:
                sid = pending[0]
                candidates = reuse_candidates_if_undecided(ctx, sid)
                if candidates:
                    blocked = True
                    reason = "stage_reuse"
                    stage_id = sid
                    message = "Choose reuse or run fresh"
                    reuse_candidates_payload = [c.to_dict() for c in candidates]

    if not blocked and handoff_between_stages_enabled():
        handoff_sid = pending_handoff_stage(ctx)
        if handoff_sid:
            blocked = True
            reason = "handoff_review"
            stage_id = handoff_sid
            message = "Review AI outputs before continuing"

    flow = get_selected_flow(ctx)
    if (
        not blocked
        and ctx.artifact_exists("analysis_complete.json")
        and not flow
        and not milestones.get("g2_complete")
    ):
        intent = get_flow_intent(ctx)
        if intent:
            message = NEXT_ACTION_COMPLETE_G2
        elif not g1_missing:
            blocked = True
            reason = "g2_flow_select"
            stage_id = "g2_flow_select"
            message = NEXT_ACTION_COMPLETE_G2

    out: dict[str, Any] = {
        "blocked": blocked,
        "reason": reason,
        "message": message,
        "stage_id": stage_id,
    }
    if reuse_candidates_payload:
        out["reuse_candidates"] = reuse_candidates_payload
    return out


def _stage_display_title(stage_id: str) -> str:
    from interview_mux.web.stages import STAGE_BY_ID

    info = STAGE_BY_ID.get(stage_id)
    return info.title if info else stage_id.replace("_", " ")


def _is_llm_gate_message(message: str) -> bool:
    low = message.lower()
    markers = (
        "llm stage gate",
        "primary attempt budget exhausted",
        "arbiter reject budget exhausted",
        "adaptation exhausted",
        "adaptation loop detected",
    )
    return any(m in low for m in markers)


def _gate_headline(stage_id: str, reason: str | None) -> str:
    if stage_id == "transcript_review":
        return "Review speech-to-text clips"
    if stage_id == "disfluency_review":
        return "Review filler clips"
    if stage_id == "g1_vo_pickup":
        return "Record pickup lines"
    if stage_id == "g1_5_preview_pickup":
        return "Re-record post-preview pickup lines"
    if stage_id == "g2_flow_select":
        return "Choose output flow"
    if stage_id == "analysis_profile":
        return "Verify interview profile"
    if reason == "handoff_review":
        return "Review AI outputs"
    return f"{_stage_display_title(stage_id)} needs your input"


def _gate_primary_label(stage_id: str, reason: str | None) -> str:
    if reason == "write_approval":
        return "Save all files & continue"
    if reason == "artifact_clarification":
        return "Apply fixes & re-check"
    if reason == "stage_reuse":
        return "Choose reuse or run fresh"
    if reason == "handoff_review":
        return "Review outputs"
    if reason == "llm_gate":
        return "Re-run stage"
    if stage_id == "transcript_review":
        return "Review STT clips"
    if stage_id == "disfluency_review":
        return "Review filler clips"
    if stage_id == "g1_vo_pickup":
        return "Record pickup lines"
    if stage_id == "g1_5_preview_pickup":
        return "Re-record post-preview lines"
    if stage_id == "g2_flow_select":
        return "Confirm output type"
    if stage_id == "analysis_profile":
        return "Review AI story profile"
    if stage_id == "sfx_prompt_craft":
        return "Review SFX prompts"
    return "Open checkpoint"


def _write_approval_action(
    ctx: RunContext,
    stage_id: str,
    *,
    job: dict[str, Any] | None,
) -> dict[str, Any]:
    from interview_mux.write_staging import list_pending_paths

    paths = None
    if job:
        raw = job.get("pending_write_paths")
        if isinstance(raw, list):
            paths = raw
    if paths is None:
        paths = list_pending_paths(ctx, stage_id)
    fc = len(paths)
    title = _stage_display_title(stage_id)
    return {
        "mode": "needs_you",
        "stage_id": stage_id,
        "substep_id": f"write_approval:{stage_id}",
        "headline": f"Review {title} outputs before saving",
        "subline": (
            f"{fc} staged file{'s' if fc != 1 else ''}"
            if fc
            else "Preview staged outputs, then save to disk."
        ),
        "primary_label": (
            f"Save all {fc} files & continue" if fc > 1 else "Save all files & continue"
        ),
        "modal_auto_open": True,
    }


def _active_operator_action(
    ctx: RunContext,
    *,
    job: dict[str, Any] | None,
    blocking: dict[str, Any],
    milestones: dict[str, bool],
) -> dict[str, Any]:
    """Unified operator focus for GUI — mirrors resolveOperatorAction priority."""
    empty: dict[str, Any] = {
        "mode": None,
        "stage_id": None,
        "substep_id": None,
        "headline": None,
        "subline": None,
        "primary_label": None,
        "modal_auto_open": False,
    }

    if job:
        status = str(job.get("status") or "")
        stage = str(
            job.get("pending_write_stage") or job.get("current_stage") or job.get("stage") or ""
        )
        if status == "interrupted" and stage:
            title = _stage_display_title(stage)
            msg = str(job.get("message") or "The server restarted or the job was interrupted.")
            return {
                "mode": "idle",
                "stage_id": stage,
                "substep_id": None,
                "headline": f"Run interrupted — retry {title}",
                "subline": msg,
                "primary_label": f"Retry {title}",
                "modal_auto_open": False,
            }
        if status in ("running", "running_with_warnings") and stage:
            msg = str(job.get("message") or "in progress").strip().rstrip(".")
            title = _stage_display_title(stage)
            return {
                "mode": "running",
                "stage_id": stage,
                "substep_id": "run",
                "headline": f"Running {title} — {msg}",
                "subline": "Watch the activity log for progress.",
                "primary_label": "Running…",
                "modal_auto_open": False,
            }
        if status == "awaiting_write_approval" and stage:
            return _write_approval_action(ctx, stage, job=job)
        if job.get("needs_stage_reuse") and stage:
            count = len(job.get("reuse_candidates") or [])
            return {
                "mode": "needs_you",
                "stage_id": stage,
                "substep_id": f"stage_reuse:{stage}",
                "headline": "Choose reuse or run fresh",
                "subline": (
                    f"{count} prior run{'s' if count != 1 else ''} with same audio"
                    if count
                    else None
                ),
                "primary_label": "Choose reuse or run fresh",
                "modal_auto_open": True,
            }

    if blocking.get("blocked"):
        reason = blocking.get("reason")
        sid = str(blocking.get("stage_id") or "")
        msg = str(blocking.get("message") or "")
        if reason == "write_approval" and sid:
            return _write_approval_action(ctx, sid, job=job)
        if reason == "stage_reuse" and sid:
            return {
                "mode": "needs_you",
                "stage_id": sid,
                "substep_id": f"stage_reuse:{sid}",
                "headline": "Choose reuse or run fresh",
                "subline": msg if msg != "Choose reuse or run fresh" else None,
                "primary_label": "Choose reuse or run fresh",
                "modal_auto_open": True,
            }
        if reason == "handoff_review" and sid:
            title = _stage_display_title(sid)
            return {
                "mode": "needs_you",
                "stage_id": sid,
                "substep_id": f"handoff:{sid}",
                "headline": f"Review AI outputs from {title}",
                "subline": "Skim generated files, then acknowledge to continue.",
                "primary_label": "Review outputs",
                "modal_auto_open": True,
            }
        if sid:
            headline = _gate_headline(sid, str(reason) if reason else None)
            return {
                "mode": "needs_you",
                "stage_id": sid,
                "substep_id": f"gate:{sid}" if reason else sid,
                "headline": headline,
                "subline": msg if msg and msg != headline else "Complete the checkpoint in the review panel.",
                "primary_label": _gate_primary_label(sid, str(reason) if reason else None),
                "modal_auto_open": True,
            }

    _ = milestones  # reserved for future idle/done hints
    return empty


def execute_hint(
    phase: str,
    flow_intent: str | None,
    selected_flow: str | None,
    milestones: dict[str, bool],
) -> dict[str, Any] | None:
    """Primary CTA for GUI command bar. action=checkpoint opens operator modal."""
    flow = selected_flow or flow_intent or "flow1"

    if phase == "prepare":
        if not milestones.get("g0_complete"):
            return {
                "action": "execute",
                "mode": "analysis",
                "until_stage": "transcript_review_build",
                "label": NEXT_ACTION_PREPARE_RUN,
            }
        return {
            "action": "execute",
            "mode": "analysis",
            "from_stage": (
                "disfluency_extract"
                if not milestones.get("disfluency_complete", True)
                else "source_acoustic_profile"
            ),
            "label": NEXT_ACTION_UNDERSTAND_RUN,
        }

    if phase == "understand":
        return {
            "action": "execute",
            "mode": "analysis",
            "from_stage": "source_acoustic_profile",
            "label": NEXT_ACTION_UNDERSTAND_RUN,
        }

    if phase == "complete":
        if not milestones.get("g1_complete"):
            return {
                "action": "checkpoint",
                "stage_id": "g1_vo_pickup",
                "label": NEXT_ACTION_COMPLETE_G1,
            }
        if not milestones.get("g2_complete"):
            return {
                "action": "checkpoint",
                "stage_id": "g2_flow_select",
                "label": NEXT_ACTION_COMPLETE_G2,
            }
        return None

    if phase == "create":
        if flow == "flow3":
            return {"action": "execute", "mode": "flow3", "label": NEXT_ACTION_CREATE_FLOW3}
        if flow == "flow2":
            return {
                "action": "execute",
                "mode": "flow2",
                "until_stage": "highlight_selection",
                "label": NEXT_ACTION_CREATE_FLOW2,
            }
        return {
            "action": "execute",
            "mode": "flow1",
            "until_stage": "assembly_preview",
            "label": NEXT_ACTION_CREATE_FLOW1,
        }

    if phase == "polish":
        if flow == "flow3":
            return None
        if flow == "flow2":
            if not milestones.get("sfx_approved"):
                return {
                    "action": "checkpoint",
                    "stage_id": "sfx_prompt_craft",
                    "label": NEXT_ACTION_POLISH_CRAFT,
                }
            if not milestones.get("sfx_generated"):
                return {
                    "action": "execute",
                    "mode": "flow2",
                    "from_stage": "mmaudio_sfx_flow2",
                    "label": NEXT_ACTION_POLISH_GENERATE,
                }
            if not milestones.get("sfx_listen_complete"):
                return {
                    "action": "checkpoint",
                    "stage_id": "mmaudio_sfx_flow2",
                    "label": NEXT_ACTION_POLISH_LISTEN,
                }
            return {
                "action": "execute",
                "mode": "flow2",
                "from_stage": "sfx_prompt_craft",
                "label": NEXT_ACTION_POLISH_SFX,
            }
        if milestones.get("preview_ready") and not milestones.get("preview_listened") and _require_preview_listen():
            return {
                "action": "checkpoint",
                "stage_id": "assembly_preview",
                "label": NEXT_ACTION_POLISH_PREVIEW,
            }
        if not milestones.get("g1_5_preview_pickup_complete", True):
            return {
                "action": "checkpoint",
                "stage_id": "g1_5_preview_pickup",
                "label": NEXT_ACTION_G1_5_PREVIEW_PICKUP,
            }
        if not milestones.get("sfx_approved"):
            return {
                "action": "checkpoint",
                "stage_id": "sfx_prompt_craft",
                "label": NEXT_ACTION_POLISH_CRAFT,
            }
        if not milestones.get("sfx_generated"):
            return {
                "action": "execute",
                "mode": "flow1",
                "from_stage": "mmaudio_sfx_flow1",
                "label": NEXT_ACTION_POLISH_GENERATE,
            }
        if not milestones.get("sfx_listen_complete"):
            return {
                "action": "checkpoint",
                "stage_id": "mmaudio_sfx_flow1",
                "label": NEXT_ACTION_POLISH_LISTEN,
            }
        if not milestones.get("placement_qa_ready"):
            return {
                "action": "checkpoint",
                "stage_id": "mix_flow1",
                "label": NEXT_ACTION_POLISH_PLACEMENT,
            }
        return {
            "action": "execute",
            "mode": "flow1",
            "from_stage": "sfx_prompt_craft",
            "label": NEXT_ACTION_POLISH_SFX,
        }

    if phase == "ship":
        if flow == "flow3":
            return {
                "action": "execute",
                "mode": "flow3",
                "from_stage": "export_show_description",
                "label": NEXT_ACTION_SHIP_DESC,
            }
        if flow == "flow2":
            return {
                "action": "execute",
                "mode": "flow2",
                "from_stage": "master_flow2",
                "label": NEXT_ACTION_SHIP_MASTER,
            }
        return {
            "action": "execute",
            "mode": "flow1",
            "from_stage": "master_flow1",
            "label": NEXT_ACTION_SHIP_MASTER,
        }

    return None


def _next_action(
    phase: str,
    flow_intent: str | None,
    milestones: dict[str, bool],
    ctx: RunContext,
) -> str:
    if phase == "prepare":
        if check_transcript_review_pending(ctx):
            return NEXT_ACTION_PREPARE_G0
        return NEXT_ACTION_PREPARE_RUN
    if phase == "understand":
        if check_profile_gate_pending(ctx):
            return NEXT_ACTION_UNDERSTAND_PROFILE
        if _open_investigation_count(ctx) > 0:
            return NEXT_ACTION_UNDERSTAND_INVESTIGATIONS
        return NEXT_ACTION_UNDERSTAND_RUN
    if phase == "complete":
        if not milestones.get("g1_complete"):
            return NEXT_ACTION_COMPLETE_G1
        return NEXT_ACTION_COMPLETE_G2
    if phase == "create":
        if flow_intent == "flow3":
            return NEXT_ACTION_CREATE_FLOW3
        if flow_intent == "flow2":
            return NEXT_ACTION_CREATE_FLOW2
        if (
            flow_intent == "flow1"
            and milestones.get("preview_ready")
            and not milestones.get("preview_listened")
            and _require_preview_listen()
        ):
            return NEXT_ACTION_POLISH_PREVIEW
        return NEXT_ACTION_CREATE_FLOW1
    if phase == "polish":
        if not milestones.get("sfx_approved"):
            return NEXT_ACTION_POLISH_CRAFT
        if not milestones.get("sfx_generated"):
            return NEXT_ACTION_POLISH_GENERATE
        if not milestones.get("sfx_listen_complete"):
            return NEXT_ACTION_POLISH_LISTEN
        if flow_intent == "flow1" and milestones.get("preview_ready") and not milestones.get("preview_listened"):
            if _require_preview_listen():
                return NEXT_ACTION_POLISH_PREVIEW
        from interview_mux.gates_tbiy import check_g1_5_preview_pickup_pending

        if check_g1_5_preview_pickup_pending(ctx):
            return NEXT_ACTION_G1_5_PREVIEW_PICKUP
        if not milestones.get("placement_qa_ready"):
            return NEXT_ACTION_POLISH_PLACEMENT
        return NEXT_ACTION_POLISH_SFX
    if phase == "ship":
        if flow_intent == "flow3":
            return NEXT_ACTION_SHIP_DESC
        return NEXT_ACTION_SHIP_MASTER
    return NEXT_ACTION_DONE


def _deliverable_preview(ctx: RunContext, flow: str | None) -> dict[str, Any]:
    kind = "none"
    paths: dict[str, str] = {}
    qc_passed: bool | None = None
    lufs: float | None = None

    if flow in ("flow1", None) and ctx.artifact_exists("flow_1_master/assembly_preview.wav"):
        paths["preview"] = "flow_1_master/assembly_preview.wav"
        kind = "preview"
    if flow in ("flow1", None) and ctx.artifact_exists("flow_1_master/master.wav"):
        paths["master"] = "flow_1_master/master.wav"
        kind = "master"
    if flow == "flow2" and ctx.artifact_exists("flow_2_highlights/master.wav"):
        paths["master"] = "flow_2_highlights/master.wav"
        kind = "master"
    if flow == "flow3" and ctx.artifact_exists("flow_3_description/show_description.md"):
        paths["description"] = "flow_3_description/show_description.md"
        kind = "description"

    meta = read_run_meta(ctx)
    summaries = meta.get("qc_summaries") or {}
    if isinstance(summaries, dict):
        vm = summaries.get("verify_master") or summaries.get("mix_intelligibility")
        if isinstance(vm, dict):
            qc_passed = vm.get("passed")

    return {
        "kind": kind,
        "paths": paths,
        "qc_passed": qc_passed,
        "lufs": lufs,
    }


def phase_progress(ctx: RunContext, stages: list[dict[str, Any]] | None = None) -> dict[str, dict[str, int]]:
    """Per-phase done/total counts from stage list."""
    progress: dict[str, dict[str, int]] = {p: {"done": 0, "total": 0} for p in OPERATOR_PHASES}
    if not stages:
        return progress
    for s in stages:
        sid = s.get("id") or ""
        if sid in ("g2_flow_select",):
            op = "complete"
        else:
            op = stage_operator_phase(sid)
        if op not in progress:
            continue
        progress[op]["total"] += 1
        if s.get("status") == "done":
            progress[op]["done"] += 1
    return progress


def build_journey_snapshot(
    ctx: RunContext,
    *,
    job: dict[str, Any] | None = None,
    stages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    milestones = compute_milestones(ctx)
    phase = compute_operator_phase(ctx, milestones)
    flow_intent = get_flow_intent(ctx)
    selected_flow = get_selected_flow(ctx)
    blocking = _blocking(ctx, job=job, milestones=milestones)
    hint = execute_hint(phase, flow_intent, selected_flow, milestones)
    active_operator_action = _active_operator_action(
        ctx, job=job, blocking=blocking, milestones=milestones
    )
    if blocking.get("blocked"):
        next_action = blocking["message"]
    elif phase == "understand" and _open_investigation_count(ctx) > 0:
        next_action = NEXT_ACTION_UNDERSTAND_INVESTIGATIONS
    elif hint and hint.get("label"):
        next_action = str(hint["label"])
    else:
        next_action = _next_action(phase, flow_intent, milestones, ctx)
    from interview_mux.custom_run_handoff import handoff_state_for_run

    handoff = handoff_state_for_run(ctx)
    return {
        "phase": phase,
        "milestones": milestones,
        "flow_intent": flow_intent,
        "selected_flow": selected_flow,
        "next_action": next_action,
        "blocking": blocking,
        "active_operator_action": active_operator_action,
        "handoff": handoff,
        "recommended_preclean": _recommended_preclean(ctx, phase, milestones),
        "preclean_checkpoints": sorted(PRECLEAN_CHECKPOINTS),
        "execute_hint": hint,
        "deliverable": _deliverable_preview(ctx, selected_flow or flow_intent),
        "phase_progress": phase_progress(ctx, stages),
        "open_investigations": _open_investigation_count(ctx),
        "open_coherence_risks": _open_coherence_risk_count(ctx),
        "blocking_coherence_contradictions": _blocking_coherence_contradiction_count(ctx),
        "sound_labels": _sound_labels(ctx),
        "phase_guidance": _build_phase_guidance(ctx, stages),
        **_active_substep(ctx, job=job, blocking=blocking, hint=hint),
    }


def _active_substep(
    ctx: RunContext,
    *,
    job: dict[str, Any] | None,
    blocking: dict[str, Any],
    hint: dict[str, Any] | None,
) -> dict[str, str | None]:
    """Operator focus substep for GUI sidebar (mirrors client findActiveSubstep priority)."""
    if blocking.get("blocked"):
        sid = str(blocking.get("stage_id") or "")
        reason = str(blocking.get("reason") or "")
        msg = str(blocking.get("message") or "")
        if reason == "write_approval":
            return {
                "active_substep_id": f"write_approval:{sid}" if sid else "write_approval",
                "active_substep_label": msg or "Save staged outputs",
            }
        if reason == "artifact_clarification":
            return {
                "active_substep_id": f"artifact_clarification:{sid}" if sid else "artifact_clarification",
                "active_substep_label": msg or "Resolve artifact issues",
            }
        if reason == "operator_decisions":
            return {
                "active_substep_id": f"operator_decisions:{sid}" if sid else "operator_decisions",
                "active_substep_label": msg or "Your input needed",
            }
        if reason == "downstream_propagation":
            return {
                "active_substep_id": f"artifact_clarification:{sid}" if sid else "artifact_clarification",
                "active_substep_label": msg or "Resolve downstream propagation",
            }
        if reason == "stage_reuse" and sid:
            return {
                "active_substep_id": f"stage_reuse:{sid}",
                "active_substep_label": msg or "Choose reuse or run fresh",
            }
        if reason == "handoff_review" and sid:
            return {
                "active_substep_id": f"handoff:{sid}",
                "active_substep_label": msg or "Review AI outputs",
            }
        if reason in (
            "transcript_review",
            "disfluency_review",
            "g1_vo_pickup",
            "g2_flow_select",
            "analysis_profile",
            "llm_gate",
        ) and sid:
            return {
                "active_substep_id": f"gate:{sid}",
                "active_substep_label": msg or "Checkpoint required",
            }
        label = f"Your turn: {msg}" if msg else "Your turn"
        return {
            "active_substep_id": f"blocked:{sid}" if sid else "blocked",
            "active_substep_label": label,
        }
    if job:
        status = str(job.get("status") or "")
        stage = str(job.get("pending_write_stage") or job.get("stage") or "")
        if status == "awaiting_write_approval" and stage:
            msg = str(job.get("message") or f"Save outputs for {stage}")
            return {
                "active_substep_id": f"write_approval:{stage}",
                "active_substep_label": msg,
            }
        if status in ("running", "running_with_warnings") and stage:
            title = stage.replace("_", " ")
            return {
                "active_substep_id": "running",
                "active_substep_label": f"Running {title}…",
            }
        if status == "gate" and stage:
            return {
                "active_substep_id": f"gate:{stage}",
                "active_substep_label": str(job.get("message") or "Checkpoint required"),
            }
        if job.get("needs_stage_reuse") and stage:
            return {
                "active_substep_id": f"stage_reuse:{stage}",
                "active_substep_label": "Choose reuse or run fresh",
            }
    if hint and hint.get("label"):
        return {
            "active_substep_id": str(hint.get("stage_id") or hint.get("action") or "hint"),
            "active_substep_label": str(hint["label"]),
        }
    return {"active_substep_id": None, "active_substep_label": None}


def _sound_labels(ctx: RunContext) -> list[str]:
    sonic = load_sonic_context(ctx) or {}
    scenario = sonic.get("scenario") if isinstance(sonic.get("scenario"), dict) else {}
    posture = scenario.get("sound_posture") if isinstance(scenario.get("sound_posture"), dict) else {}
    labels = list(SOUND_LABELS)
    bucket = str(scenario.get("atlas_bucket") or "").strip()
    if bucket:
        labels.append(f"atlas:{bucket}")
    bed = str(posture.get("bed_density") or "").strip()
    if bed:
        labels.append(f"bed:{bed}")
    return labels


def _build_phase_guidance(
    ctx: RunContext,
    stages: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    from interview_mux.stage_guidance import build_phase_guidance

    return build_phase_guidance(ctx, stages)


def set_flow_intent(ctx: RunContext, flow: str) -> None:
    if flow not in ("flow1", "flow2", "flow3"):
        raise ValueError(f"Invalid flow_intent: {flow}")
    meta = read_run_meta(ctx)
    meta["flow_intent"] = flow
    meta["flow_intent_at"] = datetime.now(timezone.utc).isoformat()
    ctx.write_json("run_meta.json", meta)
    log_journey(ctx, "milestone", f"Output intent set: {flow}", stage="g2_flow_select")


def mark_preview_listened(ctx: RunContext) -> None:
    meta = read_run_meta(ctx)
    meta["preview_listened_at"] = datetime.now(timezone.utc).isoformat()
    ms = meta.get("journey_milestones")
    if not isinstance(ms, dict):
        ms = {}
    ms["preview_listened"] = True
    meta["journey_milestones"] = ms
    ctx.write_json("run_meta.json", meta)
    from interview_mux.production_profile import is_tbiy

    if is_tbiy(ctx) and ctx.artifact_exists("understanding/gap_report.json"):
        from interview_mux.gap_report_api import update_line

        report = ctx.read_json("understanding/gap_report.json")
        for ln in report.get("interviewer_lines") or []:
            if not isinstance(ln, dict):
                continue
            if ln.get("delivery") != "record":
                continue
            if str(ln.get("gap_type") or "") in ("reaction_line", "chapter_hook"):
                try:
                    update_line(ctx, str(ln["line_id"]), {"post_preview": True})
                except KeyError:
                    pass
    refresh_journey_meta(ctx)
    log_journey(ctx, "preview", "Assembly preview marked as listened", stage="assembly_preview")
