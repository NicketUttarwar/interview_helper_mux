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
    require_flow1_extended_gates,
    require_g1_clear,
    require_profile_verified_for_flow1_extended,
    require_selected_flow_flow1,
    require_selected_flow_flow2,
    require_transcript_review_clear,
    set_selected_flow,
)
from interview_mux.run_context import RunContext
from interview_mux.stages import analysis_flow1_extended
from interview_mux.stages import assembly_flow1
from interview_mux.stages import assembly_flow2
from interview_mux.stages import audio_preclean
from interview_mux.stages import gaps
from interview_mux.stages import ingest
from interview_mux.stages import mastering
from interview_mux.stages import publishing_flow3
from interview_mux.stages import segmentation
from interview_mux.stages import selection_flow1
from interview_mux.stages import selection_flow2
from interview_mux.stages import sound_design_stages
from interview_mux.stages import sound_design_vo_finalize
from interview_mux.stages import sfx_elevenlabs
from interview_mux.stages import transcribe_aws
from interview_mux.stages import transcript_review
from interview_mux.stages import understanding

ANALYSIS_ORDER = [
    "audio_preclean",
    "ingest",
    "transcribe",
    "transcript_review_build",
    "source_acoustic_profile",
    "speaker_roles",
    "content_context",
    "boundary_detection",
    "segment_classification",
    "sound_design_palettes",
    "missing_framing",
    "optimal_questions",
]

FLOW1_ORDER = [
    "topic_coverage_audit",
    "narrative_arc_plan",
    "full_master_ranking",
    "transitions",
    "sound_design_plan_flow1",
    "sound_design_vo_finalize",
    "edl_flow1",
    "assembly_preview",
    "elevenlabs_prompt_craft",
    "elevenlabs_sfx_flow1",
    "mix_flow1",
    "master_flow1",
]

FLOW2_ORDER = [
    "highlight_selection",
    "sound_design_plan_flow2",
    "elevenlabs_prompt_craft",
    "elevenlabs_sfx_flow2",
    "mix_flow2",
    "master_flow2",
]

FLOW3_ORDER = [
    "podcast_show_description",
    "export_show_description",
]


def _analysis_stage_fns(ctx: RunContext) -> dict[str, Any]:
    return {
        "audio_preclean": lambda: audio_preclean.run_audio_preclean(ctx),
        "ingest": lambda: ingest.run_ingest(ctx),
        "transcribe": lambda: transcribe_aws.run_transcribe(ctx),
        "transcript_review_build": lambda: transcript_review.run_transcript_review_build(ctx),
        "source_acoustic_profile": lambda: understanding.run_source_acoustic_profile(ctx),
        "speaker_roles": lambda: understanding.run_speaker_roles(ctx),
        "content_context": lambda: understanding.run_content_context(ctx),
        "boundary_detection": lambda: segmentation.run_boundaries(ctx),
        "segment_classification": lambda: segmentation.run_classification(ctx),
        "sound_design_palettes": lambda: sound_design_stages.run_sound_design_palettes(ctx),
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
        "sound_design_plan_flow1": lambda: sound_design_stages.run_sound_design_plan_flow1(ctx),
        "sound_design_vo_finalize": lambda: sound_design_vo_finalize.run_sound_design_vo_finalize(ctx),
        "edl_flow1": assembly_flow1.run_edl,
        "assembly_preview": assembly_flow1.run_preview,
        "elevenlabs_prompt_craft": lambda: sound_design_stages.run_elevenlabs_prompt_craft(ctx),
        "elevenlabs_sfx_flow1": lambda: sfx_elevenlabs.run_sfx_generation(ctx, profile="podcast"),
        "mix_flow1": assembly_flow1.run_mix_flow1,
        "master_flow1": mastering.run_master_flow1,
    }


def _flow2_stage_fns(ctx: RunContext) -> dict[str, Any]:
    return {
        "highlight_selection": selection_flow2.run_highlight_selection,
        "sound_design_plan_flow2": lambda: sound_design_stages.run_sound_design_plan_flow2(ctx),
        "elevenlabs_prompt_craft": lambda: sound_design_stages.run_elevenlabs_prompt_craft(ctx),
        "elevenlabs_sfx_flow2": lambda: sfx_elevenlabs.run_sfx_generation(ctx, profile="montage"),
        "mix_flow2": assembly_flow2.run_mix_flow2,
        "master_flow2": mastering.run_master_flow2,
    }


def _flow3_stage_fns(ctx: RunContext) -> dict[str, Any]:
    return {
        "podcast_show_description": publishing_flow3.run_podcast_show_description,
        "export_show_description": publishing_flow3.run_export_show_description,
    }


def run_single_stage(ctx: RunContext, stage: str) -> None:
    """Run exactly one pipeline stage (reads all inputs from disk)."""
    if stage == "transcript_review":
        transcript_review.mark_transcript_review_complete(ctx)
        return
    if stage == "podcast_sfx_brief":
        # v1 legacy — not in FLOW1_ORDER; SDP + elevenlabs_prompt_craft is the default path.
        selection_flow1.run_podcast_sfx_brief(ctx)
        return
    if stage == "sfx_brief":
        # v1 legacy — not in FLOW2_ORDER; SDP + elevenlabs_prompt_craft is the default path.
        selection_flow2.run_sfx_brief(ctx)
        return
    if stage == "mux_flow1":
        assembly_flow1.run_mux(ctx)
        return
    if stage == "mux_flow2":
        assembly_flow2.run_micro_assembly(ctx)
        return

    if stage in ANALYSIS_ORDER:
        if stage not in ("audio_preclean", "ingest", "transcribe", "transcript_review_build"):
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
        require_selected_flow_flow1(ctx)
        if stage == "topic_coverage_audit":
            require_profile_verified_for_flow1_extended(ctx)
        fns = _flow1_stage_fns(ctx)
        if stage not in fns:
            raise ValueError(f"Unknown stage: {stage}")
        fns[stage]()
        return

    if stage in FLOW2_ORDER:
        require_g1_clear(ctx)
        require_selected_flow_flow2(ctx)
        fns = _flow2_stage_fns(ctx)
        if stage not in fns:
            raise ValueError(f"Unknown stage: {stage}")
        fns[stage]()
        return

    if stage in FLOW3_ORDER:
        require_g1_clear(ctx)
        fns = _flow3_stage_fns(ctx)
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
    require_flow1_extended_gates(ctx, from_stage=from_stage)
    if from_stage:
        ctx.clear_from(from_stage, FLOW1_ORDER)

    steps = [
        ("topic_coverage_audit", analysis_flow1_extended.run_topic_coverage),
        ("narrative_arc_plan", analysis_flow1_extended.run_narrative_arc),
        ("full_master_ranking", selection_flow1.run_full_master_ranking),
        ("transitions", selection_flow1.run_transitions),
        ("sound_design_plan_flow1", lambda: sound_design_stages.run_sound_design_plan_flow1(ctx)),
        ("sound_design_vo_finalize", lambda: sound_design_vo_finalize.run_sound_design_vo_finalize(ctx)),
        ("edl_flow1", assembly_flow1.run_edl),
        ("assembly_preview", assembly_flow1.run_preview),
        ("elevenlabs_prompt_craft", lambda: sound_design_stages.run_elevenlabs_prompt_craft(ctx)),
        ("elevenlabs_sfx_flow1", lambda: sfx_elevenlabs.run_sfx_generation(ctx, profile="podcast")),
        ("mix_flow1", assembly_flow1.run_mix_flow1),
        ("master_flow1", mastering.run_master_flow1),
    ]
    _run_steps(ctx, steps, from_stage)


def run_flow2(ctx: RunContext, *, from_stage: str | None = None) -> None:
    require_g1_clear(ctx)
    require_selected_flow_flow2(ctx)
    if from_stage:
        ctx.clear_from(from_stage, FLOW2_ORDER)

    steps = [
        ("highlight_selection", selection_flow2.run_highlight_selection),
        ("sound_design_plan_flow2", lambda: sound_design_stages.run_sound_design_plan_flow2(ctx)),
        ("elevenlabs_prompt_craft", lambda: sound_design_stages.run_elevenlabs_prompt_craft(ctx)),
        ("elevenlabs_sfx_flow2", lambda: sfx_elevenlabs.run_sfx_generation(ctx, profile="montage")),
        ("mix_flow2", assembly_flow2.run_mix_flow2),
        ("master_flow2", mastering.run_master_flow2),
    ]
    _run_steps(ctx, steps, from_stage)


def run_flow3(ctx: RunContext, *, from_stage: str | None = None) -> None:
    require_g1_clear(ctx)
    if from_stage:
        ctx.clear_from(from_stage, FLOW3_ORDER)

    ctx.log(
        "Running Flow 3 — podcast show description (text only, no master.wav).",
        level="info",
        stage="flow3",
    )
    steps = [
        ("podcast_show_description", publishing_flow3.run_podcast_show_description),
        ("export_show_description", publishing_flow3.run_export_show_description),
    ]
    _run_steps(ctx, steps, from_stage)
    ctx.log(
        "Flow 3 complete — copy ready for podcast directories.",
        level="success",
        stage="flow3",
        detail=str(ctx.path("flow_3_description/show_description.md")),
    )


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
