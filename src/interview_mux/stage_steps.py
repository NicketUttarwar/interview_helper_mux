"""Numbered operator steps for the GUI step workbench — one list per pipeline stage."""

from __future__ import annotations

from typing import Any

from interview_mux.gates import check_disfluency_review_pending, check_g1_vo, get_selected_flow
from interview_mux.run_context import RunContext
from interview_mux.stage_guidance import LLM_HANDOFF_STAGES, STAGE_UNLOCKS
from interview_mux.web.stages import STAGE_BY_ID

GATE_STAGES = frozenset(
    {
        "transcript_review",
        "disfluency_review",
        "analysis_profile",
        "g1_vo_pickup",
        "g2_flow_select",
    }
)

PRECLEAN_STAGE = "audio_preclean"

NLE_EMBED_STAGES = frozenset({"full_master_ranking", "edl_flow1"})

LISTEN_STAGES = frozenset({"assembly_preview", "master_flow1", "master_flow2"})

POST_LISTEN_STAGES = frozenset({"mmaudio_sfx_flow1", "mmaudio_sfx_flow2"})

PROMPT_REVIEW_STAGE = "sfx_prompt_craft"

STAGE_REVIEW: dict[str, list[str]] = {
    "ingest": [
        "Play ingest/normalized.wav — confirm speech is audible",
        "Open ingest/checksums.json — file sizes are non-zero",
    ],
    "transcribe": [
        "Scroll the transcript preview — speakers are assigned",
        "Word count is greater than zero",
    ],
    "transcript_review_build": [
        "transcript/review_queue.json has chunks",
        "Review clips exist in review_clips/",
    ],
    "source_acoustic_profile": [
        "pace_class matches interview cadence",
        "mix_contract levels look reasonable",
    ],
    "speaker_roles": [
        "Interviewer vs interviewee roles are correct",
        "At least one interviewer speaker exists",
    ],
    "content_context": [
        "Thesis matches the interview",
        "Topics and key claims are populated",
    ],
    "boundary_detection": [
        "Boundaries do not overlap",
        "Segments are sorted by start time",
    ],
    "segment_classification": [
        "Segment types are varied (not all answers)",
        "Every segment_id exists in boundaries.json",
    ],
    "content_brief_reanchor": [
        "Topics have segment_ids",
        "Topic relationships are present",
    ],
    "sonic_context_build": ["Scenario posture looks plausible for this interview"],
    "sound_design_palettes": ["Palettes are grounded to segment_ids"],
    "missing_framing": ["Gap evaluations have plausible gap_type values"],
    "optimal_questions": [
        "gap_report.json is complete",
        "Interviewer script is readable",
    ],
    "assembly_preview": [
        "Listen to assembly_preview.wav — speech and VO are audible",
        "No obvious clipping or silence gaps",
    ],
    "mix_flow1": ["Listen to assembly.wav — beds and speech are balanced"],
    "mix_flow2": ["Listen to assembly.wav — montage levels are balanced"],
    "master_flow1": ["Listen to master.wav — final deliverable sounds correct"],
    "master_flow2": ["Listen to master.wav — highlight reel sounds correct"],
    "export_show_description": ["Open show_description.md — copy is ready to publish"],
}

STAGE_EMBED: dict[str, str] = {
    "transcribe": "transcript_dock",
    "transcript_review_build": "transcript_dock",
    "source_acoustic_profile": "acoustic_profile",
    "interview_spine_build": "interview_spine",
    "sonic_context_build": "sonic_context",
    "content_brief_reanchor": "coherence_risks",
    "full_master_ranking": "timeline",
    "edl_flow1": "timeline",
    "assembly_preview": "listen",
    "mmaudio_sfx_flow1": "post_listen",
    "mmaudio_sfx_flow2": "post_listen",
    "mix_flow1": "placement_qa",
    "mix_flow2": "placement_qa",
    "master_flow1": "deliverable",
    "master_flow2": "deliverable",
}


def _step(
    step_id: str,
    number: int,
    label: str,
    *,
    instruction: str = "",
    review: list[str] | None = None,
    primary_button: str | None = None,
    secondary_button: str | None = None,
    kind: str = "info",
    status: str = "todo",
    embed: str | None = None,
    next_hint: str | None = None,
    blocking_reason: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": step_id,
        "number": number,
        "label": label,
        "instruction": instruction,
        "review": review or [],
        "kind": kind,
        "status": status,
    }
    if primary_button:
        row["primary_button"] = primary_button
    if secondary_button:
        row["secondary_button"] = secondary_button
    if embed:
        row["embed"] = embed
    if next_hint:
        row["next_hint"] = next_hint
    if blocking_reason:
        row["blocking_reason"] = blocking_reason
    return row


def _next_stage_title(stage_id: str) -> str:
    unlock = STAGE_UNLOCKS.get(stage_id, "")
    if " — " in unlock:
        return unlock.split(" — ", 1)[0].strip()
    if unlock:
        return unlock.split("(")[0].strip()
    info = STAGE_BY_ID.get(stage_id)
    return info.title if info else stage_id


def _prereqs_met(guidance: dict[str, Any]) -> bool:
    prereqs = guidance.get("prerequisites") or []
    return all(p.get("status") != "todo" for p in prereqs)


def _job_running_stage(ctx: RunContext, stage_id: str) -> bool:
    if not ctx.artifact_exists("gui_job.json"):
        return False
    try:
        job = ctx.read_json("gui_job.json")
    except Exception:
        return False
    st = job.get("status")
    if st not in ("running", "running_with_warnings"):
        return False
    cur = job.get("current_stage") or job.get("stage")
    return str(cur or "") == stage_id


def _needs_reuse(ctx: RunContext, stage_id: str) -> bool:
    if not ctx.artifact_exists("gui_job.json"):
        return False
    try:
        job = ctx.read_json("gui_job.json")
    except Exception:
        return False
    return bool(job.get("needs_stage_reuse") and job.get("stage") == stage_id)


def _needs_write(ctx: RunContext, stage_id: str) -> bool:
    from interview_mux.write_staging import has_pending_writes, write_approval_enabled

    return write_approval_enabled() and has_pending_writes(ctx, stage_id)


def _needs_handoff(ctx: RunContext, stage_id: str, status: str) -> bool:
    if status != "done" or stage_id not in LLM_HANDOFF_STAGES:
        return False
    from interview_mux.custom_run_handoff import handoff_acknowledged

    if handoff_acknowledged(ctx, stage_id):
        return False
    info = STAGE_BY_ID.get(stage_id)
    if not info:
        return False
    return any(ctx.artifact_exists(p) for p in info.artifacts if p and not p.endswith("/"))


def _gate_steps(ctx: RunContext, stage_id: str, status: str) -> list[dict[str, Any]]:
    if stage_id == "transcript_review":
        return [
            _step(
                "listen_clips",
                1,
                "Listen to review clips",
                instruction="Work through clips from lowest confidence first. Use Previous/Next or the dropdown.",
                review=["Play each clip audio", "Compare audio to displayed text"],
                kind="gate",
                status="todo" if status == "action_required" else "done",
                embed="transcript_review",
            ),
            _step(
                "fix_errors",
                2,
                "Fix transcript errors",
                instruction="Double-click a word in the transcript dock to edit. Use Fix similar words to batch-correct repeated mishearings.",
                review=["Dock: click word to seek audio", "Fuzzy replace: set strictness 80–100%"],
                kind="embed_transcript_dock",
                status="todo" if status == "action_required" else "done",
            ),
            _step(
                "mark_reviewed",
                3,
                "Mark chunks reviewed",
                instruction="Save each chunk or click Mark reviewed (no change) to advance.",
                review=["Progress shows X of Y chunks reviewed"],
                kind="gate",
                status="todo" if status == "action_required" else "done",
                embed="transcript_review",
            ),
            _step(
                "complete_g0",
                4,
                "Complete transcript review",
                instruction="Merges corrections into full.json. Required before any analysis stage.",
                review=["Correction summary shows edit count"],
                primary_button="Complete transcript review",
                kind="gate",
                status="todo" if status == "action_required" else "done",
                embed="transcript_review",
                next_hint="Next: Disfluency extract or source acoustic profile",
            ),
        ]
    if stage_id == "disfluency_review":
        return [
            _step(
                "review_fillers",
                1,
                "Review filler clips",
                instruction="Listen to each detected filler. Confirm real fillers; reject false positives.",
                review=["Play clip", "Read surrounding context"],
                kind="gate",
                status="todo" if status == "action_required" else "done",
                embed="disfluency_review",
            ),
            _step(
                "restore_pref",
                2,
                "Set restore preference",
                instruction="For confirmed fillers, toggle Include in assembly restore if desired.",
                kind="gate",
                status="todo" if status == "action_required" else "done",
                embed="disfluency_review",
            ),
            _step(
                "complete_g05",
                3,
                "Complete disfluency review",
                instruction="Required before source acoustic profile when disfluency is enabled.",
                primary_button="Complete review",
                kind="gate",
                status="todo" if status == "action_required" else "done",
                embed="disfluency_review",
            ),
        ]
    if stage_id == "analysis_profile":
        return [
            _step(
                "review_profile",
                1,
                "Review AI story profile",
                instruction="Read themes, major questions, and style. Edit inline if the AI misread the interview.",
                review=["Themes match content", "tone_class and format_class are sensible"],
                kind="embed_story_board",
                status="todo" if status == "action_required" else "done",
            ),
            _step(
                "investigations",
                2,
                "Resolve investigations",
                instruction="Open investigation items flagged during analysis. Dismiss or re-run affected stages.",
                review=["Investigation count reaches zero"],
                kind="embed_story_board",
                status="todo" if status == "action_required" else "done",
            ),
            _step(
                "verify_profile",
                3,
                "Mark profile verified",
                instruction="Required before Flow 1 extended stages (topic coverage and later).",
                primary_button="Mark profile verified",
                kind="gate",
                status="todo" if status == "action_required" else "done",
                embed="analysis_profile",
            ),
        ]
    if stage_id == "g1_vo_pickup":
        g1 = check_g1_vo(ctx)
        return [
            _step(
                "review_lines",
                1,
                "Review required pickup lines",
                instruction="These lines need human recordings. Read each script line below.",
                review=["Open interviewer_script.txt", "Note line_id for each record line"],
                kind="gate",
                status="todo" if g1 else "done",
                embed="vo_pickup",
            ),
            _step(
                "record_lines",
                2,
                "Record or upload each line",
                instruction="Record in the GUI or upload WAV to vo_pickup/{line_id}.wav",
                review=["Each line shows checkmark when file present", "Play back recording"],
                kind="gate",
                status="todo" if g1 else "done",
                embed="vo_pickup",
            ),
            _step(
                "preclean_pickup",
                3,
                "Optional — clean pickup audio",
                instruction="Remove background noise from new recordings only.",
                kind="preclean",
                status="todo",
            ),
            _step(
                "continue_g2",
                4,
                "Continue to flow selection",
                instruction="All delivery:record lines must have WAV files before G2.",
                primary_button="Continue to Confirm output",
                kind="gate",
                status="todo" if g1 else "done",
                next_hint="Next: Confirm output (G2)",
            ),
        ]
    if stage_id == "g2_flow_select":
        return [
            _step(
                "review_summary",
                1,
                "Review analysis summary",
                instruction="Analysis is complete. Pick what you want to produce.",
                review=["gap_report reviewed", "Profile verified if planning Flow 1"],
                kind="info",
                status="todo" if status == "action_required" else "done",
            ),
            _step(
                "choose_flow",
                2,
                "Choose output flow",
                instruction="Flow 1 = full podcast. Flow 2 = highlights. Flow 3 = show description (no audio).",
                kind="gate",
                status="todo" if status == "action_required" else "done",
                embed="flow_select",
            ),
            _step(
                "confirm_flow",
                3,
                "Confirm selection",
                instruction="This commits selected_flow in run_meta.json.",
                primary_button="Confirm output type",
                kind="gate",
                status="todo" if status == "action_required" else "done",
                embed="flow_select",
            ),
        ]
    return []


def _preclean_steps(status: str) -> list[dict[str, Any]]:
    return [
        _step(
            "review_offer",
            1,
            "Review the pre-clean offer",
            instruction="Optional: remove steady background noise from your source recording before ingest.",
            review=["Read scope (full source vs pickup-only)"],
            primary_button="Run audio cleaning",
            secondary_button="Skip this optional step",
            kind="preclean",
            status="todo" if status != "done" else "done",
        ),
        _step(
            "wait_run",
            2,
            "Wait for cleaning to finish",
            instruction="DeepFilterNet runs locally. Watch the activity log.",
            primary_button="Running…",
            kind="run",
            status="waiting",
        ),
        _step(
            "continue_ingest",
            3,
            "Continue to ingest",
            instruction="Pre-clean is complete or skipped. Ingest will use the cleaned WAV if you accepted.",
            primary_button="Continue to Ingest",
            kind="info",
            status="done" if status == "done" else "todo",
            next_hint="Next: Ingest",
        ),
    ]


def _locked_steps(stage_id: str, guidance: dict[str, Any]) -> list[dict[str, Any]]:
    blocking = next(
        (p for p in (guidance.get("prerequisites") or []) if p.get("status") == "todo"),
        None,
    )
    label = blocking.get("label", "prerequisites") if blocking else "earlier steps"
    target = blocking.get("stage_id") if blocking else None
    return [
        _step(
            "locked",
            1,
            f"Waiting for {label}",
            instruction=f"Complete the blocking step before running {STAGE_BY_ID.get(stage_id, stage_id)}.",
            primary_button=f"Go to {target or 'blocking stage'}",
            kind="locked",
            status="blocked",
            blocking_reason=target,
        )
    ]


def _done_steps(stage_id: str) -> list[dict[str, Any]]:
    info = STAGE_BY_ID.get(stage_id)
    title = info.title if info else stage_id
    nxt = _next_stage_title(stage_id)
    return [
        _step(
            "complete",
            1,
            "Step complete",
            instruction=f"{title} finished successfully.",
            review=["Expand Outputs below to inspect artifacts"],
            primary_button=f"Continue to {nxt}" if nxt else "Continue",
            secondary_button="Redo from this step",
            kind="done",
            status="done",
        )
    ]


def _automated_steps(
    ctx: RunContext,
    stage_id: str,
    status: str,
    guidance: dict[str, Any],
) -> list[dict[str, Any]]:
    info = STAGE_BY_ID.get(stage_id)
    title = info.title if info else stage_id
    nxt = _next_stage_title(stage_id)
    steps: list[dict[str, Any]] = []
    num = 1

    prereq_items = [p.get("label", "") for p in (guidance.get("prerequisites") or []) if p.get("label")]
    prereq_status = "done" if _prereqs_met(guidance) or status == "done" else "todo"
    steps.append(
        _step(
            "prereqs",
            num,
            "Check prerequisites",
            instruction="This step needs the outputs listed below from earlier steps.",
            review=prereq_items[:6] if prereq_items else ["All prior stages complete"],
            primary_button="Continue" if prereq_status == "done" else None,
            kind="info",
            status=prereq_status,
        )
    )
    num += 1

    if _needs_reuse(ctx, stage_id):
        steps.append(
            _step(
                "reuse",
                num,
                "Choose reuse or run fresh",
                instruction="A prior run used the same source audio. Reuse saves time; run fresh if you changed upstream artifacts.",
                review=["Compare candidate run date", "Confirm same audio hash"],
                primary_button="Reuse outputs",
                secondary_button="Run fresh instead",
                kind="reuse",
                status="todo",
            )
        )
        num += 1

    run_status = "active" if _job_running_stage(ctx, stage_id) else (
        "done" if status == "done" or ctx.is_done(stage_id) else "todo"
    )
    if status == "locked":
        run_status = "blocked"
    steps.append(
        _step(
            "run",
            num,
            f"Run {title}",
            instruction="Click Run to start. Progress appears in the activity log on the right.",
            review=["Watch for errors in the Live log tab"],
            primary_button=f"Run {title}",
            kind="run",
            status=run_status,
        )
    )
    num += 1

    review_bullets = STAGE_REVIEW.get(stage_id, [])
    embed = STAGE_EMBED.get(stage_id)

    if stage_id in NLE_EMBED_STAGES:
        steps.append(
            _step(
                "timeline",
                num,
                "Review segment order",
                instruction="Use the timeline below to verify segment order. Trim or exclude segments if needed.",
                review=["Source timeline shows all segments", "QC checklist items resolved"],
                kind="embed_timeline",
                status="todo" if status != "done" else "done",
                embed="timeline",
            )
        )
        num += 1

    if stage_id == PROMPT_REVIEW_STAGE:
        from interview_mux.config import merged_config

        cfg = merged_config()
        if cfg.get("g1_5_require_prompt_approval", False):
            steps.append(
                _step(
                    "prompt_review",
                    num,
                    "Review SFX prompts",
                    instruction="Edit prompts before MMAudio generation. Bad prompts waste generation time.",
                    review=["Each asset has a prompt", "Edit text if needed"],
                    primary_button="Approve prompts",
                    kind="gate",
                    status="todo" if status != "done" else "done",
                    embed="sfx_prompt_review",
                )
            )
            num += 1

    if _needs_write(ctx, stage_id) or status == "awaiting_write_approval":
        steps.append(
            _step(
                "write_approval",
                num,
                "Review outputs before saving",
                instruction="Preview staged files before they are written to disk.",
                review=review_bullets or ["Open each staged JSON", "Play any staged WAV"],
                primary_button="Save & continue",
                secondary_button="Discard & re-run",
                kind="write_approval",
                status="todo",
                embed=embed,
            )
        )
        num += 1
    elif review_bullets or embed:
        listen_kind = "listen" if embed == "listen" else "info"
        steps.append(
            _step(
                "review_outputs",
                num,
                "Review outputs",
                instruction="Spot-check the generated artifacts below.",
                review=review_bullets,
                primary_button="I've reviewed — continue" if embed == "listen" else None,
                kind=listen_kind,
                status="todo" if status != "done" else "done",
                embed=embed,
            )
        )
        num += 1

    if stage_id in POST_LISTEN_STAGES and status == "done":
        steps.append(
            _step(
                "post_listen",
                num,
                "Post-listen QA",
                instruction="Listen to each generated SFX. Pass or fail each asset.",
                review=["Inline audio plays for each asset"],
                kind="embed_post_listen",
                status="todo",
                embed="post_listen",
            )
        )
        num += 1

    if _needs_handoff(ctx, stage_id, status):
        steps.append(
            _step(
                "handoff",
                num,
                "Review AI outputs",
                instruction="Skim the generated files below, then acknowledge to continue.",
                review=["Spot-check key fields match the interview"],
                primary_button="Acknowledge & continue",
                kind="handoff",
                status="todo",
            )
        )
        num += 1

    if stage_id in LLM_HANDOFF_STAGES:
        steps.append(
            _step(
                "debug",
                num,
                "Engineering debug (optional)",
                instruction="LLM routing and volley memory for troubleshooting.",
                kind="embed_debug",
                status="done",
                embed="debug",
            )
        )
        num += 1

    if status == "done":
        for s in steps:
            if s["status"] == "todo":
                s["status"] = "done"
        steps.append(
            _step(
                "complete",
                num,
                "Step complete",
                instruction=f"{title} finished. Continue to the next stage.",
                primary_button=f"Continue to {nxt}" if nxt else "Continue",
                secondary_button="Redo from this step",
                kind="done",
                status="done",
                next_hint=f"Next: {nxt}" if nxt else None,
            )
        )

    return steps


def build_stage_steps(
    ctx: RunContext,
    stage_id: str,
    *,
    status: str,
    guidance: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build numbered operator steps for one stage."""
    if stage_id not in STAGE_UNLOCKS:
        raise KeyError(f"Missing STAGE_UNLOCKS for {stage_id}")

    if status == "locked":
        return _locked_steps(stage_id, guidance)

    if stage_id == PRECLEAN_STAGE:
        return _preclean_steps(status)

    if stage_id in GATE_STAGES:
        return _gate_steps(ctx, stage_id, status)

    if status == "done" and not _needs_handoff(ctx, stage_id, status) and not _needs_write(ctx, stage_id):
        if not _needs_reuse(ctx, stage_id):
            return _done_steps(stage_id)

    return _automated_steps(ctx, stage_id, status, guidance)


def attach_steps_to_guidance(
    ctx: RunContext,
    stage_id: str,
    guidance: dict[str, Any],
    *,
    status: str,
) -> None:
    """Mutate guidance dict to include steps list."""
    guidance["steps"] = build_stage_steps(ctx, stage_id, status=status, guidance=guidance)
