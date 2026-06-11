"""Per-stage and per-phase operator guidance for the GUI — mirrors operator-stage-checklists."""

from __future__ import annotations

from typing import Any

from interview_mux.gates import (
    check_analysis_artifacts_gate_pending,
    check_disfluency_review_pending,
    check_g1_vo,
    check_profile_gate_pending,
    check_transcript_review_pending,
    get_selected_flow,
    is_operator_profile_verified,
)
from interview_mux.journey_state import OPERATOR_PHASES, stage_operator_phase
from interview_mux.pipeline import ANALYSIS_ORDER, FLOW1_ORDER, FLOW2_ORDER, FLOW3_ORDER
from interview_mux.run_context import RunContext
from interview_mux.web.stages import STAGE_BY_ID

# Stages blocked until G0 transcript review clears (matches pipeline.require_transcript_review_clear).
_G0_EXCEPTIONS = frozenset(
    {"audio_preclean", "ingest", "transcribe", "transcript_review_build", "disfluency_extract"}
)
G0_LOCKED_ANALYSIS_STAGES = frozenset(s for s in ANALYSIS_ORDER if s not in _G0_EXCEPTIONS)

_DISFLUENCY_EXCEPTIONS = frozenset(_G0_EXCEPTIONS)
DISFLUENCY_LOCKED_ANALYSIS_STAGES = frozenset(
    s for s in ANALYSIS_ORDER if s not in _DISFLUENCY_EXCEPTIONS
)

LLM_HANDOFF_STAGES = frozenset(
    {
        "speaker_roles",
        "content_context",
        "boundary_detection",
        "segment_classification",
        "content_brief_reanchor",
        "sound_design_palettes",
        "missing_framing",
        "optimal_questions",
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "transitions",
        "sound_design_plan_flow1",
        "sound_design_plan_flow2",
        "highlight_selection",
        "edl_narrative_audit",
        "podcast_show_description",
    }
)

PHASE_DISPLAY: dict[str, str] = {
    "start": "Start",
    "prepare": "Prepare",
    "understand": "Analyze",
    "complete": "Complete",
    "create": "Build",
    "polish": "Sound",
    "ship": "Export",
}

PHASE_GOALS: dict[str, str] = {
    "start": "Pick source audio and optionally set your output type.",
    "prepare": "Transcribe the interview and fix speech-to-text errors before AI analysis.",
    "understand": "Let AI analyze the interview, then review themes and story profile.",
    "complete": "Record missing voice lines and confirm your deliverable choice.",
    "create": "Generate episode order, highlights, or show description.",
    "polish": "Add sound design and mix the final audio.",
    "ship": "Download your master WAV or show description.",
}

# Static unlock text per stage id — required for parity tests.
STAGE_UNLOCKS: dict[str, str] = {
    "audio_preclean": "Ingest (uses isolated WAV if pre-clean accepted)",
    "ingest": "Transcribe — normalized source audio",
    "transcribe": "STT review prep — word-level transcript",
    "transcript_review_build": "Transcript review (G0) — ranked clip queue",
    "disfluency_extract": "Disfluency review (G0.5) — filler event catalog",
    "disfluency_review": "Source acoustic profile and downstream analysis",
    "transcript_review": "Disfluency extract (when enabled) or source acoustic profile",
    "source_acoustic_profile": "Speaker roles and sonic pacing for mix/SFX",
    "speaker_roles": "Content understanding",
    "content_context": "Segment boundaries",
    "boundary_detection": "Segment classification",
    "segment_classification": "Content brief re-anchor",
    "content_brief_reanchor": "Sound design palettes",
    "sound_design_palettes": "Gap evaluation",
    "missing_framing": "Interviewer script and gap report",
    "optimal_questions": "Complete phase — G1 VO pickup if record lines exist",
    "analysis_profile": "Flow 1 extended Build stages (topic coverage and later)",
    "g1_vo_pickup": "Confirm output (G2)",
    "vo_ingest": "Timeline VO merge on next pipeline run",
    "g2_flow_select": "Build, Sound, and Export stages for your chosen flow",
    "topic_coverage_audit": "Narrative arc plan",
    "narrative_arc_plan": "Segment ordering (full master ranking)",
    "full_master_ranking": "Transitions between segments",
    "transitions": "Flow 1 sound design plan",
    "sound_design_plan_flow1": "VO bridge finalize",
    "sound_design_vo_finalize": "EDL narrative audit",
    "edl_narrative_audit": "Edit decision list (EDL)",
    "edl_flow1": "Assembly preview (speech + VO, no SFX)",
    "assembly_preview": "Sound phase — listen before ElevenLabs spend",
    "elevenlabs_prompt_craft": "ElevenLabs SFX generation",
    "elevenlabs_sfx_flow1": "Mix assembly",
    "elevenlabs_sfx_flow2": "Mix assembly",
    "mix_flow1": "Master export",
    "mix_flow2": "Master export",
    "master_flow1": "Deliverable ready — listen or export",
    "master_flow2": "Deliverable ready — listen or export",
    "highlight_selection": "Flow 2 sound design plan",
    "sound_design_plan_flow2": "Sound phase — prompt craft and SFX",
    "podcast_show_description": "Export show description blurb",
    "export_show_description": "Ship phase — markdown export",
    "mux_flow1": "Same as Mix assembly",
    "mux_flow2": "Same as Mix assembly",
    "podcast_sfx_brief": "(legacy — use SDP path)",
    "sfx_brief": "(legacy — use SDP path)",
}

# Prior stage in pipeline order (for prerequisite messaging).
_PRIOR_STAGE: dict[str, str | None] = {}
for _order in (ANALYSIS_ORDER, FLOW1_ORDER, FLOW2_ORDER, FLOW3_ORDER):
    for _i, _sid in enumerate(_order):
        _PRIOR_STAGE[_sid] = _order[_i - 1] if _i > 0 else None

# Artifact path labels for common prerequisites.
_ARTIFACT_LABELS: dict[str, str] = {
    "ingest/normalized.wav": "Normalized source audio",
    "transcript/full.json": "Full transcript",
    "transcript/review_queue.json": "STT review queue",
    "understanding/gap_report.json": "Gap report with pickup lines",
    "understanding/analysis_state.json": "Analysis profile populated",
    "run_meta.json": "Run metadata with selected flow",
}


def guidance_required_stage_ids() -> frozenset[str]:
    """Every stage that must have guidance (STAGE_BY_ID + gates)."""
    return frozenset(STAGE_BY_ID.keys())


def _guidance_item(
    item_id: str,
    label: str,
    status: str,
    *,
    stage_id: str | None = None,
    action: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"id": item_id, "label": label, "status": status}
    if stage_id:
        row["stage_id"] = stage_id
    if action:
        row["action"] = action
    if kind:
        row["kind"] = kind
    return row


def _artifact_checks(ctx: RunContext, stage_id: str) -> list[dict[str, Any]]:
    info = STAGE_BY_ID.get(stage_id)
    if not info:
        return []
    checks: list[dict[str, Any]] = []
    for path in info.artifacts:
        if not path or path.endswith("/"):
            continue
        label = _ARTIFACT_LABELS.get(path, path.split("/")[-1].replace("_", " "))
        status = "done" if ctx.artifact_exists(path) else "waiting"
        checks.append({"path": path, "label": label, "status": status})
    return checks


def _latest_stage_attempt(ctx: RunContext, stage_id: str) -> dict[str, Any] | None:
    base = ctx.path("understanding", "stage_runs", stage_id)
    if not base.is_dir():
        return None
    attempts = sorted(base.glob("attempt_*.json"))
    if not attempts:
        return None
    rel = f"understanding/stage_runs/{stage_id}/{attempts[-1].name}"
    try:
        doc = ctx.read_json(rel)
        return doc if isinstance(doc, dict) else None
    except Exception:
        return None


def _llm_hardening_guidance_items(ctx: RunContext, stage_id: str) -> list[dict[str, Any]]:
    """Actionable bullets for budget exhaustion, lint failures, and placement QA."""
    from interview_mux.attempt_budget import max_primary_attempts, primary_attempt_count

    items: list[dict[str, Any]] = []
    if stage_id in LLM_HANDOFF_STAGES:
        cap = max_primary_attempts()
        count = primary_attempt_count(ctx, stage_id)
        if count >= cap:
            items.append(
                _guidance_item(
                    "llm_budget",
                    f"Primary attempt budget exhausted ({count}/{cap}) — review stage_runs before retry",
                    "todo",
                )
            )
        attempt = _latest_stage_attempt(ctx, stage_id)
        if attempt:
            lint = attempt.get("deterministic_lint_errors") or []
            if lint:
                summary = str(lint[0])[:100]
                items.append(
                    _guidance_item(
                        "llm_lint",
                        f"Latest attempt failed lint: {summary}",
                        "todo",
                    )
                )
    if ctx.artifact_exists("understanding/investigation_queue.json"):
        queue = ctx.read_json("understanding/investigation_queue.json")
        inv_items = queue.get("items") or queue.get("investigations") or []
        cross_inv = [
            it
            for it in inv_items
            if isinstance(it, dict)
            and (it.get("status") or "open") in ("open", "pending", "needs")
            and it.get("kind") == "cross_artifact_invalid"
            and (not it.get("target") or it.get("target", {}).get("stage") == stage_id)
        ]
        if cross_inv and stage_id in LLM_HANDOFF_STAGES:
            items.append(
                _guidance_item(
                    "cross_validate",
                    "Cross-artifact validation flagged issues — review investigation queue",
                    "todo",
                    action="story_board",
                    kind="story_board",
                )
            )
    if stage_id in ("mix_flow1", "mix_flow2") and ctx.artifact_exists("sound_design/placement_adjustments.json"):
        items.append(
            _guidance_item(
                "placement_qa",
                "Review sound_design/placement_adjustments.json before export",
                "todo",
            )
        )
    return items


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


def _g0_items(transcript_review_pending: bool) -> list[dict[str, Any]]:
    if not transcript_review_pending:
        return [
            _guidance_item(
                "g0",
                "Complete transcript review (G0)",
                "done",
                stage_id="transcript_review",
                action="checkpoint",
            )
        ]
    return [
        _guidance_item(
            "g0",
            "Complete transcript review (G0)",
            "todo",
            stage_id="transcript_review",
            action="checkpoint",
            kind="checkpoint",
        )
    ]


def _prior_stage_items(
    ctx: RunContext,
    stage_id: str,
    *,
    transcript_review_pending: bool,
) -> list[dict[str, Any]]:
    if stage_id in G0_LOCKED_ANALYSIS_STAGES and transcript_review_pending:
        return _g0_items(True)
    prior = _PRIOR_STAGE.get(stage_id)
    if not prior:
        return []
    if ctx.is_done(prior):
        return [
            _guidance_item(
                f"prior_{prior}",
                f"Complete {STAGE_BY_ID[prior].title if prior in STAGE_BY_ID else prior}",
                "done",
                stage_id=prior,
            )
        ]
    return [
        _guidance_item(
            f"prior_{prior}",
            f"Complete {STAGE_BY_ID[prior].title if prior in STAGE_BY_ID else prior} first",
            "todo",
            stage_id=prior,
            action="run",
            kind="run",
        )
    ]


def _flow_prereqs(
    ctx: RunContext,
    stage_id: str,
    flow: str | None,
    g1_missing: list[str],
    profile_gate_pending: bool,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    info = STAGE_BY_ID.get(stage_id)
    if not info or info.phase not in ("flow1", "flow2", "flow3"):
        return items
    if g1_missing:
        items.append(
            _guidance_item(
                "g1",
                f"Record {len(g1_missing)} pickup line(s) (G1)",
                "todo",
                stage_id="g1_vo_pickup",
                action="checkpoint",
                kind="checkpoint",
            )
        )
    elif not ctx.artifact_exists("analysis_complete.json"):
        items.append(
            _guidance_item(
                "analysis",
                "Complete understanding analysis first",
                "todo",
                stage_id="optimal_questions",
                kind="run",
            )
        )
    if not flow:
        items.append(
            _guidance_item(
                "g2",
                "Confirm output type at G2",
                "todo",
                stage_id="g2_flow_select",
                action="checkpoint",
                kind="checkpoint",
            )
        )
    if profile_gate_pending and info.phase == "flow1":
        items.append(
            _guidance_item(
                "profile",
                "Mark interview profile verified",
                "todo",
                stage_id="analysis_profile",
                action="checkpoint",
                kind="profile",
            )
        )
    return items


def _analysis_artifacts_gate_prereqs(ctx: RunContext) -> list[dict[str, Any]]:
    """Flow-hardening gate: analysis artifacts must be complete before flows."""
    if not check_analysis_artifacts_gate_pending(ctx):
        return [
            _guidance_item(
                "analysis_artifacts",
                "Analysis artifacts complete (flow hardening)",
                "done",
                kind="run",
            )
        ]
    blockers: list[str] = []
    if ctx.artifact_exists("understanding/analysis_state.json"):
        completion = (ctx.read_json("understanding/analysis_state.json") or {}).get("completion") or {}
        raw = completion.get("blockers") or []
        if isinstance(raw, list):
            blockers = [str(b) for b in raw[:2]]
    hint = f": {', '.join(blockers)}" if blockers else ""
    return [
        _guidance_item(
            "analysis_artifacts",
            f"Analysis artifacts complete (flow hardening){hint}",
            "todo",
            stage_id="optimal_questions",
            kind="run",
        )
    ]


def _llm_upstream_prereq_items(ctx: RunContext, stage_id: str) -> list[dict[str, Any]]:
    """When hardening is on, surface incomplete upstream LLM producer artifacts."""
    from interview_mux.artifact_completeness import artifact_status
    from interview_mux.llm_flow_hardening import LLM_UPSTREAM_STAGE, flow_hardening_enabled, producer_artifact_path

    if not flow_hardening_enabled() or stage_id not in LLM_HANDOFF_STAGES:
        return []
    upstream = LLM_UPSTREAM_STAGE.get(stage_id)
    if not upstream:
        return []
    rel = producer_artifact_path(upstream)
    if not rel:
        return []
    if artifact_status(rel, ctx) == "complete":
        return []
    return [
        _guidance_item(
            "upstream_artifact",
            f"Re-run upstream stage {upstream} or Fill gaps ({rel})",
            "todo",
            stage_id=upstream,
            kind="run",
        )
    ]


def _stage_actions(
    stage_id: str,
    status: str,
    *,
    transcript_review_pending: bool,
    prerequisites: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    blocked = any(p.get("status") == "todo" for p in prerequisites)

    if stage_id == "transcript_review":
        if status == "action_required":
            actions.append(
                _guidance_item(
                    "review_clips",
                    "Review ranked STT clips and complete review",
                    "todo",
                    action="checkpoint",
                    kind="checkpoint",
                )
            )
        elif status == "done":
            actions.append(
                _guidance_item("review_clips", "Transcript review complete", "done")
            )
        return actions

    if stage_id == "analysis_profile":
        if status == "action_required":
            actions.append(
                _guidance_item(
                    "verify_profile",
                    "Review Story Board, then Mark profile verified",
                    "todo",
                    action="checkpoint",
                    kind="profile",
                )
            )
        elif status == "done":
            actions.append(_guidance_item("verify_profile", "Profile verified", "done"))
        return actions

    if stage_id == "g1_vo_pickup":
        if status == "action_required":
            actions.append(
                _guidance_item(
                    "record_vo",
                    "Record or upload every pickup line",
                    "todo",
                    action="checkpoint",
                    kind="checkpoint",
                )
            )
        elif status == "done":
            actions.append(_guidance_item("record_vo", "All pickup lines recorded", "done"))
        return actions

    if stage_id == "g2_flow_select":
        if status in ("action_required", "pending"):
            actions.append(
                _guidance_item(
                    "pick_flow",
                    "Select full master, highlights, or show description",
                    "todo" if status == "action_required" else "waiting",
                    action="checkpoint",
                    kind="checkpoint",
                )
            )
        elif status == "done":
            actions.append(_guidance_item("pick_flow", "Output type confirmed", "done"))
        return actions

    if stage_id == "audio_preclean":
        if status == "pending" and not blocked:
            actions.append(
                _guidance_item(
                    "preclean",
                    "Accept or dismiss optional pre-clean, then run",
                    "todo",
                    kind="preclean",
                )
            )
            actions.append(
                _guidance_item("run", "Run this step", "todo", action="run", kind="run")
            )
        return actions

    if stage_id in ("assembly_preview",) and status == "done":
        actions.append(
            _guidance_item(
                "listen_preview",
                "Listen to assembly preview before sound spend",
                "todo",
                kind="listen",
            )
        )
        return actions

    if stage_id in ("elevenlabs_prompt_craft",) and status in ("pending", "done"):
        actions.append(
            _guidance_item(
                "approve_prompts",
                "Review and approve ElevenLabs prompts (G1.5 if enabled)",
                "todo" if status != "done" else "waiting",
                stage_id="elevenlabs_prompt_craft",
                kind="prompt_review",
            )
        )
        if status == "pending" and not blocked:
            actions.append(
                _guidance_item("run", "Run this step", "todo", action="run", kind="run")
            )
        return actions

    if stage_id in ("elevenlabs_sfx_flow1", "elevenlabs_sfx_flow2"):
        if status == "pending" and not blocked:
            actions.append(
                _guidance_item("run", "Run this step", "todo", action="run", kind="run")
            )
        if status == "done":
            actions.append(
                _guidance_item(
                    "listen_sfx",
                    "Listen to SFX outputs and pass sound check",
                    "todo",
                    kind="listen",
                )
            )
        return actions

    if stage_id in LLM_HANDOFF_STAGES:
        if status == "pending" and not blocked:
            actions.append(
                _guidance_item("run", "Run this step", "todo", action="run", kind="run")
            )
        elif status == "done":
            actions.append(
                _guidance_item(
                    "handoff",
                    "Acknowledge AI-generated outputs",
                    "todo",
                    kind="handoff",
                )
            )
        return actions

    # Default automated stage
    if status == "locked":
        if not actions:
            actions.append(
                _guidance_item(
                    "run",
                    "Complete prerequisites above to unlock",
                    "waiting",
                    kind="run",
                )
            )
    elif status == "action_required":
        actions.append(
            _guidance_item(
                "operator",
                "Complete the required operator steps",
                "todo",
                action="checkpoint",
                kind="checkpoint",
            )
        )
    elif status == "pending":
        if blocked:
            actions.append(
                _guidance_item(
                    "run",
                    "Run this step (locked until prerequisites met)",
                    "waiting",
                    kind="run",
                )
            )
        else:
            actions.append(
                _guidance_item("run", "Run this step", "todo", action="run", kind="run")
            )
    elif status == "done":
        actions.append(_guidance_item("run", "Step complete", "done", kind="run"))

    return actions


def build_stage_guidance(
    ctx: RunContext,
    stage_id: str,
    *,
    status: str,
    flow: str | None = None,
    g1_missing: list[str] | None = None,
    transcript_review_pending: bool | None = None,
    profile_gate_pending: bool | None = None,
    profile_verified: bool | None = None,
) -> dict[str, Any]:
    """Build guidance payload for one stage."""
    if stage_id not in STAGE_UNLOCKS:
        raise KeyError(f"Missing STAGE_UNLOCKS entry for {stage_id}")

    tr_pending = (
        transcript_review_pending
        if transcript_review_pending is not None
        else check_transcript_review_pending(ctx)
    )
    g1 = g1_missing if g1_missing is not None else check_g1_vo(ctx)
    flow_sel = flow if flow is not None else get_selected_flow(ctx)
    profile_pending = (
        profile_gate_pending
        if profile_gate_pending is not None
        else check_profile_gate_pending(ctx)
    )

    op_phase = stage_operator_phase(stage_id)
    phase_label = PHASE_DISPLAY.get(op_phase, op_phase.title())

    prerequisites: list[dict[str, Any]] = []

    if stage_id == "ingest":
        has_audio = bool(ctx.read_json("run_meta.json").get("input_audio_path")) if ctx.artifact_exists(
            "run_meta.json"
        ) else False
        prerequisites.append(
            _guidance_item(
                "source_audio",
                "Source audio selected for this run",
                "done" if has_audio else "todo",
                kind="start",
            )
        )
    elif stage_id == "transcribe":
        prerequisites.append(
            _guidance_item(
                "ingest_wav",
                "ingest/normalized.wav on disk",
                "done" if ctx.artifact_exists("ingest/normalized.wav") else "todo",
                stage_id="ingest",
            )
        )
    elif stage_id == "transcript_review_build":
        prerequisites.append(
            _guidance_item(
                "transcript",
                "transcript/full.json from transcribe",
                "done" if ctx.artifact_exists("transcript/full.json") else "todo",
                stage_id="transcribe",
            )
        )
    elif stage_id == "transcript_review":
        prerequisites.append(
            _guidance_item(
                "review_queue",
                "STT review queue built",
                "done" if ctx.artifact_exists("transcript/review_queue.json") else "todo",
                stage_id="transcript_review_build",
            )
        )
    elif stage_id in G0_LOCKED_ANALYSIS_STAGES:
        prerequisites.extend(_g0_items(tr_pending))
        if stage_id == "source_acoustic_profile":
            prerequisites.append(
                _guidance_item(
                    "ingest_wav",
                    "Ingest + transcript available",
                    "done"
                    if ctx.artifact_exists("ingest/normalized.wav")
                    and ctx.artifact_exists("transcript/full.json")
                    else "todo",
                )
            )
        else:
            prerequisites.extend(_prior_stage_items(ctx, stage_id, transcript_review_pending=tr_pending))
    elif stage_id == "analysis_profile":
        prerequisites.append(
            _guidance_item(
                "understanding_done",
                "Understanding analysis artifacts populated",
                "done" if ctx.artifact_exists("understanding/content_brief.json") else "todo",
                stage_id="optimal_questions",
            )
        )
        prerequisites.extend(_analysis_artifacts_gate_prereqs(ctx))
    elif stage_id == "g1_vo_pickup":
        prerequisites.append(
            _guidance_item(
                "gap_report",
                "Gap report with pickup lines",
                "done" if ctx.artifact_exists("understanding/gap_report.json") else "todo",
                stage_id="optimal_questions",
            )
        )
    elif stage_id == "g2_flow_select":
        if g1:
            prerequisites.append(
                _guidance_item(
                    "g1",
                    f"Record {len(g1)} pickup line(s) (G1)",
                    "todo",
                    stage_id="g1_vo_pickup",
                    action="checkpoint",
                )
            )
        else:
            prerequisites.append(
                _guidance_item("g1", "VO pickup complete (or not required)", "done")
            )
    else:
        prerequisites.extend(_prior_stage_items(ctx, stage_id, transcript_review_pending=tr_pending))
        prerequisites.extend(
            _flow_prereqs(ctx, stage_id, flow_sel, g1, profile_pending)
        )

    info = STAGE_BY_ID.get(stage_id)
    if info and info.phase in ("flow1", "flow2", "flow3"):
        prerequisites.extend(_analysis_artifacts_gate_prereqs(ctx))
    if stage_id in LLM_HANDOFF_STAGES:
        prerequisites.extend(_llm_upstream_prereq_items(ctx, stage_id))

    inv_count = _open_investigation_count(ctx)
    prerequisites.extend(_llm_hardening_guidance_items(ctx, stage_id))
    if stage_id == "content_context" and inv_count > 0:
        prerequisites.append(
            _guidance_item(
                "investigations",
                f"Resolve {inv_count} open question(s) in Story Board",
                "todo",
                action="story_board",
                kind="story_board",
            )
        )

    actions = _stage_actions(
        stage_id,
        status,
        transcript_review_pending=tr_pending,
        prerequisites=prerequisites,
    )

    return {
        "phase_label": phase_label,
        "prerequisites": prerequisites,
        "actions": actions,
        "unlocks": STAGE_UNLOCKS[stage_id],
        "artifact_checks": _artifact_checks(ctx, stage_id),
    }


def build_phase_guidance(
    ctx: RunContext,
    stages: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Aggregate phase-level guidance from stage list."""
    result: dict[str, Any] = {"start": {"goal": PHASE_GOALS["start"], "actions": [], "progress": None}}

    for phase in OPERATOR_PHASES:
        goal = PHASE_GOALS.get(phase, "")
        phase_stages = [
            s for s in (stages or []) if (s.get("operator_phase") or stage_operator_phase(s.get("id", ""))) == phase
        ]
        done = sum(1 for s in phase_stages if s.get("status") == "done")
        total = len(phase_stages)
        progress = {"done": done, "total": total} if total else None

        actions: list[dict[str, Any]] = []
        for s in phase_stages:
            guidance = s.get("guidance") or {}
            for bucket in ("prerequisites", "actions"):
                for item in guidance.get(bucket) or []:
                    if item.get("status") == "todo":
                        actions.append({**item, "from_stage_id": s.get("id"), "from_stage_title": s.get("title")})
            if len(actions) >= 3:
                break

        if phase == "understand" and not actions:
            inv = _open_investigation_count(ctx)
            if inv > 0:
                actions.append(
                    _guidance_item(
                        "investigations",
                        f"Resolve {inv} open question(s) in Story Board",
                        "todo",
                        action="story_board",
                        kind="story_board",
                    )
                )
            if check_profile_gate_pending(ctx) and is_operator_profile_verified(ctx) is False:
                actions.append(
                    _guidance_item(
                        "profile",
                        "Mark interview profile verified",
                        "todo",
                        stage_id="analysis_profile",
                        kind="profile",
                    )
                )

        result[phase] = {"goal": goal, "actions": actions[:3], "progress": progress}

    return result


def attach_guidance_to_stages(
    ctx: RunContext,
    stages: list[dict[str, Any]],
    *,
    flow: str | None,
    g1_missing: list[str],
    transcript_review_pending: bool,
    profile_gate_pending: bool,
    profile_verified: bool,
) -> None:
    """Mutate stage dicts in place with guidance payloads."""
    for s in stages:
        sid = s.get("id") or ""
        if sid not in STAGE_UNLOCKS:
            continue
        s["guidance"] = build_stage_guidance(
            ctx,
            sid,
            status=str(s.get("status") or "pending"),
            flow=flow,
            g1_missing=g1_missing,
            transcript_review_pending=transcript_review_pending,
            profile_gate_pending=profile_gate_pending,
            profile_verified=profile_verified,
        )
