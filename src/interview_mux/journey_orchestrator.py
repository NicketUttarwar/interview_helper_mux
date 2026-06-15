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
    handoff_review_message,
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

    if job and job.get("status") in ("gate", "needs_operator"):
        blocked = True
        message = str(job.get("message") or "Operator action required")
        stage_id = job.get("stage")
        if job.get("needs_stage_reuse"):
            reason = "stage_reuse"
        else:
            reason = str(stage_id or job.get("status"))

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

    if not blocked and check_profile_gate_pending(ctx):
        blocked = True
        reason = "analysis_profile"
        stage_id = "analysis_profile"
        message = NEXT_ACTION_UNDERSTAND_PROFILE

    if not blocked:
        from interview_mux.stage_execution_reuse import (
            reuse_candidates_if_undecided,
            stage_reuse_offers_enabled,
        )
        from interview_mux.web.stages import STAGE_BY_ID

        if stage_reuse_offers_enabled():
            for sid in _next_pending_stage_ids(ctx):
                candidates = reuse_candidates_if_undecided(ctx, sid)
                if candidates:
                    blocked = True
                    reason = "stage_reuse"
                    stage_id = sid
                    info = STAGE_BY_ID.get(sid)
                    title = info.title if info else sid
                    src = candidates[0].run_id
                    message = (
                        f"{title} can reuse outputs from {src}. "
                        "Choose reuse or run fresh before continuing."
                    )
                    break

    if not blocked and handoff_between_stages_enabled():
        handoff_sid = pending_handoff_stage(ctx)
        if handoff_sid:
            blocked = True
            reason = "handoff_review"
            stage_id = handoff_sid
            message = handoff_review_message(ctx, handoff_sid)

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

    return {
        "blocked": blocked,
        "reason": reason,
        "message": message,
        "stage_id": stage_id,
    }


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
    if blocking.get("blocked"):
        next_action = blocking["message"]
    elif hint and hint.get("label"):
        next_action = str(hint["label"])
    else:
        next_action = _next_action(phase, flow_intent, milestones, ctx)
    return {
        "phase": phase,
        "milestones": milestones,
        "flow_intent": flow_intent,
        "selected_flow": selected_flow,
        "next_action": next_action,
        "blocking": blocking,
        "recommended_preclean": _recommended_preclean(ctx, phase, milestones),
        "preclean_checkpoints": sorted(PRECLEAN_CHECKPOINTS),
        "execute_hint": hint,
        "deliverable": _deliverable_preview(ctx, selected_flow or flow_intent),
        "phase_progress": phase_progress(ctx, stages),
        "open_investigations": _open_investigation_count(ctx),
        "sound_labels": _sound_labels(ctx),
        "phase_guidance": _build_phase_guidance(ctx, stages),
    }


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
    refresh_journey_meta(ctx)
    log_journey(ctx, "preview", "Assembly preview marked as listened", stage="assembly_preview")
