from __future__ import annotations

from datetime import datetime, timezone

from typing import Any

from interview_mux.analysis_orchestrator import (
    ANALYSIS_LLM_STAGES,
    drain_investigation_queue,
    post_analysis_finalize,
    pre_analysis_init,

)
from interview_mux.gates import (
    check_g1_vo,
    check_transcript_review_pending,
    require_g1_clear,
    require_transcript_review_clear,
    set_selected_flow,
)
from interview_mux.run_context import RunContext
from interview_mux.stages import analysis_flow1_extended
from interview_mux.stages import assembly_flow1
from interview_mux.stages import assembly_flow2
from interview_mux.stages import gaps
from interview_mux.stages import ingest
from interview_mux.stages import mastering
from interview_mux.stages import segmentation
from interview_mux.stages import selection_flow1
from interview_mux.stages import selection_flow2
from interview_mux.stages import sfx_elevenlabs
from interview_mux.stages import transcribe_aws
from interview_mux.stages import transcript_review
from interview_mux.stages import understanding

ANALYSIS_ORDER = [
    "ingest",
    "transcribe",
    "transcript_review_build",
    "speaker_roles",
    "content_context",
    "boundary_detection",
    "segment_classification",
    "missing_framing",
    "optimal_questions",
]

FLOW1_ORDER = [
    "topic_coverage_audit",
    "narrative_arc_plan",
    "full_master_ranking",
    "transitions",
    "podcast_sfx_brief",
    "elevenlabs_sfx_flow1",
    "edl_flow1",
    "mux_flow1",
    "master_flow1",
]

FLOW2_ORDER = [
    "highlight_selection",
    "sfx_brief",
    "elevenlabs_sfx_flow2",
    "mux_flow2",
    "master_flow2",
]


def _analysis_stage_fns(ctx: RunContext) -> dict[str, Any]:
    return {
        "ingest": lambda: ingest.run_ingest(ctx),
        "transcribe": lambda: transcribe_aws.run_transcribe(ctx),
        "transcript_review_build": lambda: transcript_review.run_transcript_review_build(ctx),
        "speaker_roles": lambda: understanding.run_speaker_roles(ctx),
        "content_context": lambda: understanding.run_content_context(ctx),
        "boundary_detection": lambda: segmentation.run_boundaries(ctx),
        "segment_classification": lambda: segmentation.run_classification(ctx),
        "missing_framing": lambda: gaps.run_missing_framing(ctx),
        "optimal_questions": lambda: gaps.run_optimal_questions(ctx),
        "vo_ingest": lambda: gaps.ingest_vo_pickup(ctx),
    }


def _flow1_stage_fns(ctx: RunContext) -> dict[str, Any]:
    return {
        "topic_coverage_audit": analysis_flow1_extended.run_topic_coverage,
        "narrative_arc_plan": analysis_flow1_extended.run_narrative_arc,
        "full_master_ranking": selection_flow1.run_full_master_ranking,
        "transitions": selection_flow1.run_transitions,
        "podcast_sfx_brief": selection_flow1.run_podcast_sfx_brief,
        "elevenlabs_sfx_flow1": lambda: sfx_elevenlabs.run_sfx_generation(ctx, profile="podcast"),
        "edl_flow1": assembly_flow1.run_edl,
        "mux_flow1": assembly_flow1.run_mux,
        "master_flow1": mastering.run_master_flow1,
    }


def _flow2_stage_fns(ctx: RunContext) -> dict[str, Any]:
    return {
        "highlight_selection": selection_flow2.run_highlight_selection,
        "sfx_brief": selection_flow2.run_sfx_brief,
        "elevenlabs_sfx_flow2": lambda: sfx_elevenlabs.run_sfx_generation(ctx, profile="montage"),
        "mux_flow2": assembly_flow2.run_micro_assembly,
        "master_flow2": mastering.run_master_flow2,
    }


def run_single_stage(ctx: RunContext, stage: str) -> None:
    """Run exactly one pipeline stage (reads all inputs from disk)."""
    if stage == "transcript_review":
        transcript_review.mark_transcript_review_complete(ctx)
        return

    if stage in ANALYSIS_ORDER:
        if stage != "ingest" and stage != "transcribe" and stage != "transcript_review_build":
            require_transcript_review_clear(ctx)
        fns = _analysis_stage_fns(ctx)
        if stage not in fns:
            raise ValueError(f"Unknown stage: {stage}")
        fns[stage]()
        if stage == "transcript_review_build" and check_transcript_review_pending(ctx):
            raise SystemExit(
                "Transcript review required. Open the GUI to correct ranked clips, then complete review."
            )
        if stage == "optimal_questions":
            missing = check_g1_vo(ctx)
            if missing:
                raise SystemExit(
                    f"Analysis complete with G1 pending. Record VO for {missing} → {ctx.path('vo_pickup')}"
                )
            ctx.write_json(
                "analysis_complete.json",
                {"completed_at": datetime.now(timezone.utc).isoformat(), "run_id": ctx.run_id},
            )
        return

    if stage in FLOW1_ORDER:
        require_g1_clear(ctx)
        fns = _flow1_stage_fns(ctx)
        if stage not in fns:
            raise ValueError(f"Unknown stage: {stage}")
        fns[stage]()
        return

    if stage in FLOW2_ORDER:
        require_g1_clear(ctx)
        fns = _flow2_stage_fns(ctx)
        if stage not in fns:
            raise ValueError(f"Unknown stage: {stage}")
        fns[stage]()
        return

    if stage == "vo_ingest":
        gaps.ingest_vo_pickup(ctx)
        ctx.write_json(
            "analysis_complete.json",
            {"completed_at": datetime.now(timezone.utc).isoformat(), "run_id": ctx.run_id},
        )
        return

    raise ValueError(f"Unknown stage: {stage}")


def run_analysis(ctx: RunContext, *, from_stage: str | None = None) -> None:
    if from_stage:
        ctx.clear_from(from_stage, ANALYSIS_ORDER)

    stages = _analysis_stage_fns(ctx)
    llm_runners = {k: v for k, v in stages.items() if k in ANALYSIS_LLM_STAGES}

    start_idx = 0
    if from_stage:
        if from_stage not in stages:
            raise ValueError(f"Unknown from_stage: {from_stage}")
        start_idx = list(stages.keys()).index(from_stage)

    pre_analysis_init(ctx)

    for name, fn in list(stages.items())[start_idx:]:
        if ctx.is_done(name) and from_stage != name:
            continue
        fn()
        if name in ANALYSIS_LLM_STAGES:
            drain_investigation_queue(ctx, llm_runners)
        if name == "transcript_review_build" and check_transcript_review_pending(ctx):
            raise SystemExit(
                "Analysis paused for transcript review. Correct STT in the GUI, "
                "then complete review before continuing."
            )

    if check_transcript_review_pending(ctx):
        raise SystemExit(
            "Transcript review incomplete. Finish STT corrections in the GUI before downstream stages."
        )

    completion = post_analysis_finalize(ctx)
    missing = check_g1_vo(ctx)
    if missing:
        raise SystemExit(
            f"Analysis complete with G1 pending. Record VO for {missing} → {ctx.path('vo_pickup')}"
        )

    ctx.write_json(
        "analysis_complete.json",
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "run_id": ctx.run_id,
            "completion": completion,
        },
    )


def run_flow1(ctx: RunContext, *, from_stage: str | None = None) -> None:
    require_g1_clear(ctx)
    if from_stage:
        ctx.clear_from(from_stage, FLOW1_ORDER)

    steps = [
        ("topic_coverage_audit", analysis_flow1_extended.run_topic_coverage),
        ("narrative_arc_plan", analysis_flow1_extended.run_narrative_arc),
        ("full_master_ranking", selection_flow1.run_full_master_ranking),
        ("transitions", selection_flow1.run_transitions),
        ("podcast_sfx_brief", selection_flow1.run_podcast_sfx_brief),
        ("elevenlabs_sfx_flow1", lambda: sfx_elevenlabs.run_sfx_generation(ctx, profile="podcast")),
        ("edl_flow1", assembly_flow1.run_edl),
        ("mux_flow1", assembly_flow1.run_mux),
        ("master_flow1", mastering.run_master_flow1),
    ]
    _run_steps(ctx, steps, from_stage)


def run_flow2(ctx: RunContext, *, from_stage: str | None = None) -> None:
    require_g1_clear(ctx)
    if from_stage:
        ctx.clear_from(from_stage, FLOW2_ORDER)

    steps = [
        ("highlight_selection", selection_flow2.run_highlight_selection),
        ("sfx_brief", selection_flow2.run_sfx_brief),
        ("elevenlabs_sfx_flow2", lambda: sfx_elevenlabs.run_sfx_generation(ctx, profile="montage")),
        ("mux_flow2", assembly_flow2.run_micro_assembly),
        ("master_flow2", mastering.run_master_flow2),
    ]
    _run_steps(ctx, steps, from_stage)


def _run_steps(ctx: RunContext, steps: list, from_stage: str | None) -> None:
    start = 0
    if from_stage:
        names = [s[0] for s in steps]
        if from_stage not in names:
            raise ValueError(f"Unknown from_stage: {from_stage}")
        start = names.index(from_stage)
    for name, fn in steps[start:]:
        if ctx.is_done(name) and from_stage != name:
            continue
        fn()
