from __future__ import annotations

from datetime import datetime, timezone

from collections.abc import Callable
from typing import Any

from interview_mux.analysis_orchestrator import (
    ALL_LLM_STAGES,
    ANALYSIS_LLM_STAGES,
    drain_investigation_queue,
    llm_stage_runners,
    post_analysis_finalize,
    pre_analysis_init,
)
from interview_mux.gates import (
    check_disfluency_review_pending,
    check_g1_vo,
    check_transcript_review_pending,
    require_disfluency_review_clear,
    require_flow1_extended_gates,
    require_g1_clear,
    require_profile_verified_for_flow1_extended,
    require_selected_flow_flow1,
    require_selected_flow_flow2,
    require_transcript_review_clear,
    set_selected_flow,
)
from interview_mux.custom_run_handoff import active_pipeline_stage, pause_after_stage_if_needed
from interview_mux.run_context import RunContext
from interview_mux.stage_execution_reuse import resolve_before_stage_run
from interview_mux.stages import analysis_flow1_extended
from interview_mux.stages import assembly_flow1
from interview_mux.stages import assembly_flow2
from interview_mux.stages import audio_preclean
from interview_mux.stages import edl_narrative_audit
from interview_mux.stages import gaps
from interview_mux.stages import ingest
from interview_mux.stages import mastering
from interview_mux.stages import publishing_flow3
from interview_mux.stages import segmentation
from interview_mux.stages import selection_flow1
from interview_mux.stages import selection_flow2
from interview_mux.stages import sonic_context_stages
from interview_mux.stages import sound_design_stages
from interview_mux.stages import sound_design_vo_finalize
from interview_mux.stages import sfx_mmaudio
from interview_mux.stages import transcribe_aws
from interview_mux.stages import disfluency
from interview_mux.stages import transcript_review
from interview_mux.stages import understanding
from interview_mux.stages import interview_spine_stage

ANALYSIS_ORDER = [
    "audio_preclean",
    "ingest",
    "transcribe",
    "transcript_review_build",
    "disfluency_extract",
    "source_acoustic_profile",
    "interview_spine_build",
    "speaker_roles",
    "content_context",
    "boundary_detection",
    "segment_classification",
    "content_brief_reanchor",
    "sonic_context_build",
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
    "edl_narrative_audit",
    "edl_flow1",
    "assembly_preview",
    "sfx_prompt_craft",
    "mmaudio_sfx_flow1",
    "mix_flow1",
    "master_flow1",
]

FLOW2_ORDER = [
    "highlight_selection",
    "sound_design_plan_flow2",
    "sfx_prompt_craft",
    "mmaudio_sfx_flow2",
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
        "disfluency_extract": lambda: disfluency.run_disfluency_extract(ctx),
        "source_acoustic_profile": lambda: understanding.run_source_acoustic_profile(ctx),
        "interview_spine_build": lambda: interview_spine_stage.run_interview_spine_build(ctx),
        "speaker_roles": lambda: understanding.run_speaker_roles(ctx),
        "content_context": lambda: understanding.run_content_context(ctx),
        "boundary_detection": lambda: segmentation.run_boundaries(ctx),
        "segment_classification": lambda: segmentation.run_classification(ctx),
        "content_brief_reanchor": lambda: understanding.run_content_brief_reanchor(ctx),
        "sonic_context_build": lambda: sonic_context_stages.run_sonic_context_build(ctx),
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
        "edl_narrative_audit": lambda: edl_narrative_audit.run_edl_narrative_audit(ctx),
        "edl_flow1": assembly_flow1.run_edl,
        "assembly_preview": assembly_flow1.run_preview,
        "sfx_prompt_craft": lambda: sound_design_stages.run_sfx_prompt_craft(ctx),
        "mmaudio_sfx_flow1": lambda: sfx_mmaudio.run_sfx_generation(ctx, profile="podcast"),
        "mix_flow1": assembly_flow1.run_mix_flow1,
        "master_flow1": mastering.run_master_flow1,
    }


def _flow2_stage_fns(ctx: RunContext) -> dict[str, Any]:
    return {
        "highlight_selection": selection_flow2.run_highlight_selection,
        "sound_design_plan_flow2": lambda: sound_design_stages.run_sound_design_plan_flow2(ctx),
        "sfx_prompt_craft": lambda: sound_design_stages.run_sfx_prompt_craft(ctx),
        "mmaudio_sfx_flow2": lambda: sfx_mmaudio.run_sfx_generation(ctx, profile="montage"),
        "mix_flow2": assembly_flow2.run_mix_flow2,
        "master_flow2": mastering.run_master_flow2,
    }


def _flow3_stage_fns(ctx: RunContext) -> dict[str, Any]:
    return {
        "podcast_show_description": publishing_flow3.run_podcast_show_description,
        "export_show_description": publishing_flow3.run_export_show_description,
    }


def _guard_stage_reuse(ctx: RunContext, stage: str) -> bool:
    """Return True when stage was satisfied via reuse (skip stage function)."""
    if resolve_before_stage_run(ctx, stage) == "skipped":
        return True
    return False


def _run_single_stage_impl(ctx: RunContext, stage: str) -> None:
    """Run exactly one pipeline stage (reads all inputs from disk)."""
    if stage == "transcript_review":
        transcript_review.mark_transcript_review_complete(ctx)
        return
    if stage == "disfluency_review":
        disfluency.mark_disfluency_review_complete(ctx)
        return
    if stage == "podcast_sfx_brief":
        # v1 legacy — not in FLOW1_ORDER; SDP + sfx_prompt_craft is the default path.
        selection_flow1.run_podcast_sfx_brief(ctx)
        return
    if stage == "sfx_brief":
        # v1 legacy — not in FLOW2_ORDER; SDP + sfx_prompt_craft is the default path.
        selection_flow2.run_sfx_brief(ctx)
        return
    if stage == "mux_flow1":
        assembly_flow1.run_mux(ctx)
        return
    if stage == "mux_flow2":
        assembly_flow2.run_micro_assembly(ctx)
        return
    if stage == "sfx_prompt_refine":
        sound_design_stages.run_sfx_prompt_refine(ctx)
        return

    if stage in ANALYSIS_ORDER:
        if stage not in (
            "audio_preclean",
            "ingest",
            "transcribe",
            "transcript_review_build",
        ):
            require_transcript_review_clear(ctx)
            require_disfluency_review_clear(ctx)
        fns = _analysis_stage_fns(ctx)
        if stage not in fns:
            raise ValueError(f"Unknown stage: {stage}")
        token = active_pipeline_stage.set(stage)
        try:
            fns[stage]()
        finally:
            active_pipeline_stage.reset(token)
        pause_after_stage_if_needed(ctx, stage)
        if stage == "transcript_review_build" and check_transcript_review_pending(ctx):
            msg = (
                "Transcript review required. Open the GUI to correct ranked clips, then complete review."
            )
            ctx.log(msg, level="warning", stage="transcript_review")
            raise SystemExit(msg)
        if stage == "disfluency_extract" and check_disfluency_review_pending(ctx):
            msg = "Disfluency review required. Confirm or reject filler events in the GUI."
            ctx.log(msg, level="warning", stage="disfluency_review")
            raise SystemExit(msg)
        if stage == "optimal_questions":
            missing = check_g1_vo(ctx)
            if missing:
                msg = f"Analysis complete with G1 pending. Record VO for {missing} → {ctx.path('vo_pickup')}"
                ctx.log(msg, level="warning", stage="g1_vo_pickup")
                raise SystemExit(msg)
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
        token = active_pipeline_stage.set(stage)
        try:
            fns[stage]()
        finally:
            active_pipeline_stage.reset(token)
        pause_after_stage_if_needed(ctx, stage)
        return

    if stage in FLOW2_ORDER:
        require_g1_clear(ctx)
        require_selected_flow_flow2(ctx)
        fns = _flow2_stage_fns(ctx)
        if stage not in fns:
            raise ValueError(f"Unknown stage: {stage}")
        token = active_pipeline_stage.set(stage)
        try:
            fns[stage]()
        finally:
            active_pipeline_stage.reset(token)
        pause_after_stage_if_needed(ctx, stage)
        return

    if stage in FLOW3_ORDER:
        require_g1_clear(ctx)
        fns = _flow3_stage_fns(ctx)
        if stage not in fns:
            raise ValueError(f"Unknown stage: {stage}")
        token = active_pipeline_stage.set(stage)
        try:
            fns[stage]()
        finally:
            active_pipeline_stage.reset(token)
        pause_after_stage_if_needed(ctx, stage)
        return

    if stage == "vo_ingest":
        gaps.ingest_vo_pickup(ctx)
        ctx.write_json(
            "analysis_complete.json",
            {"completed_at": datetime.now(timezone.utc).isoformat(), "run_id": ctx.run_id},
        )
        return

    raise ValueError(f"Unknown stage: {stage}")


def run_single_stage(ctx: RunContext, stage: str) -> None:
    """Run exactly one pipeline stage (reads all inputs from disk)."""
    from interview_mux.web.job_progress import notify_stage_start

    notify_stage_start(
        ctx.run_id,
        stage,
        index=1,
        total=1,
        stages_planned=[stage],
    )
    ctx.log(
        f"Stage start: {stage}",
        level="action",
        stage=stage,
        detail={"journey_kind": "execute", "event": "stage_start"},
    )
    if stage not in (
        "transcript_review",
        "disfluency_review",
        "podcast_sfx_brief",
        "sfx_brief",
        "mux_flow1",
        "mux_flow2",
        "sfx_prompt_refine",
    ) and _guard_stage_reuse(ctx, stage):
        from interview_mux.write_staging import (
            after_stage_write_check,
            has_pending_writes,
            write_approval_enabled,
        )

        if write_approval_enabled() and has_pending_writes(ctx, stage):
            after_stage_write_check(ctx, stage)
        return
    from interview_mux.analysis_orchestrator import ALL_LLM_STAGES, drain_investigation_queue, llm_stage_runners
    from interview_mux.write_staging import run_wrapped_stage

    def _impl() -> None:
        if stage in ALL_LLM_STAGES:
            from interview_mux.llm_flow_hardening import maybe_require_upstream_llm_progress

            maybe_require_upstream_llm_progress(ctx, stage)
        _run_single_stage_impl(ctx, stage)
        if stage in ALL_LLM_STAGES:
            drain_investigation_queue(ctx, llm_stage_runners(ctx))
            from interview_mux.artifact_issue_triage import (
                maybe_repair_before_cross_validate,
                run_triage_pipeline,
                triage_enabled,
            )

            if triage_enabled():
                run_triage_pipeline(ctx, stage, staged=True)
            if maybe_repair_before_cross_validate(ctx, stage):
                from interview_mux.artifact_cross_validate import maybe_cross_validate_after_stage

                maybe_cross_validate_after_stage(ctx, stage)

    run_wrapped_stage(ctx, stage, _impl)


def run_analysis(
    ctx: RunContext,
    *,
    from_stage: str | None = None,
    until_stage: str | None = None,
) -> None:
    if from_stage:
        ctx.clear_from(from_stage, ANALYSIS_ORDER)

    stages = _analysis_stage_fns(ctx)
    llm_runners = llm_stage_runners(ctx)

    start_idx = 0
    if from_stage:
        if from_stage not in stages:
            raise ValueError(f"Unknown from_stage: {from_stage}")
        start_idx = list(stages.keys()).index(from_stage)

    pre_analysis_init(ctx)

    from interview_mux.artifact_completeness import should_run_stage_for_artifact

    stage_items = list(stages.items())[start_idx:]
    planned: list[str] = []
    for name, _fn in stage_items:
        if ctx.is_done(name) and from_stage != name:
            if name in ANALYSIS_LLM_STAGES and should_run_stage_for_artifact(ctx, name):
                planned.append(name)
            else:
                continue
        else:
            planned.append(name)
        if until_stage and name == until_stage:
            break

    total = len(planned) or 1
    for idx, (name, fn) in enumerate(stage_items, start=1):
        if ctx.is_done(name) and from_stage != name:
            if name in ANALYSIS_LLM_STAGES and should_run_stage_for_artifact(ctx, name):
                ctx.log(
                    f"Re-running {name}: artifact incomplete or invalid",
                    level="info",
                    stage=name,
                )
            else:
                continue
        if resolve_before_stage_run(ctx, name) == "skipped":
            continue
        try:
            plan_idx = planned.index(name) + 1 if name in planned else idx
        except ValueError:
            plan_idx = idx
        from interview_mux.web.job_progress import notify_stage_start

        notify_stage_start(
            ctx.run_id,
            name,
            index=plan_idx,
            total=total,
            stages_planned=planned,
        )
        if name in ALL_LLM_STAGES:
            from interview_mux.llm_flow_hardening import maybe_require_upstream_llm_progress

            maybe_require_upstream_llm_progress(ctx, name)
        from interview_mux.write_staging import run_wrapped_stage

        token = active_pipeline_stage.set(name)
        try:
            run_wrapped_stage(ctx, name, fn)
        finally:
            active_pipeline_stage.reset(token)
        pause_after_stage_if_needed(ctx, name)
        if name in ALL_LLM_STAGES:
            drain_investigation_queue(ctx, llm_runners)
            from interview_mux.artifact_cross_validate import maybe_cross_validate_after_stage

            maybe_cross_validate_after_stage(ctx, name)
        if until_stage and name == until_stage:
            break
        if name == "transcript_review_build" and check_transcript_review_pending(ctx):
            msg = (
                "Analysis paused for transcript review. Correct STT in the GUI, "
                "then complete review before continuing."
            )
            ctx.log(msg, level="warning", stage="transcript_review")
            raise SystemExit(msg)
        if name == "disfluency_extract" and check_disfluency_review_pending(ctx):
            msg = "Disfluency review required. Confirm or reject filler events in the GUI."
            ctx.log(msg, level="warning", stage="disfluency_review")
            raise SystemExit(msg)

    if check_transcript_review_pending(ctx):
        msg = "Transcript review incomplete. Finish STT corrections in the GUI before downstream stages."
        ctx.log(msg, level="warning", stage="transcript_review")
        raise SystemExit(msg)

    if check_disfluency_review_pending(ctx):
        msg = "Disfluency review incomplete. Confirm or reject filler events in the GUI."
        ctx.log(msg, level="warning", stage="disfluency_review")
        raise SystemExit(msg)

    if until_stage and until_stage != "optimal_questions":
        return

    completion = post_analysis_finalize(ctx)
    missing = check_g1_vo(ctx)
    if missing:
        msg = f"Analysis complete with G1 pending. Record VO for {missing} → {ctx.path('vo_pickup')}"
        ctx.log(msg, level="warning", stage="g1_vo_pickup")
        raise SystemExit(msg)

    ctx.write_json(
        "analysis_complete.json",
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "run_id": ctx.run_id,
            "completion": completion,
        },
    )


def run_flow1(
    ctx: RunContext,
    *,
    from_stage: str | None = None,
    until_stage: str | None = None,
    preclean_hook: Callable[[str], None] | None = None,
) -> None:
    from interview_mux.gates import require_analysis_artifacts_complete

    require_g1_clear(ctx)
    require_analysis_artifacts_complete(ctx)
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
        ("edl_narrative_audit", lambda: edl_narrative_audit.run_edl_narrative_audit(ctx)),
        ("edl_flow1", assembly_flow1.run_edl),
        ("assembly_preview", assembly_flow1.run_preview),
        ("sfx_prompt_craft", lambda: sound_design_stages.run_sfx_prompt_craft(ctx)),
        ("mmaudio_sfx_flow1", lambda: sfx_mmaudio.run_sfx_generation(ctx, profile="podcast")),
        ("mix_flow1", assembly_flow1.run_mix_flow1),
        ("master_flow1", mastering.run_master_flow1),
    ]
    _run_steps(ctx, steps, from_stage, until_stage=until_stage, preclean_hook=preclean_hook)


def run_flow2(
    ctx: RunContext,
    *,
    from_stage: str | None = None,
    until_stage: str | None = None,
    preclean_hook: Callable[[str], None] | None = None,
) -> None:
    from interview_mux.gates import require_analysis_artifacts_complete

    require_g1_clear(ctx)
    require_analysis_artifacts_complete(ctx)
    require_selected_flow_flow2(ctx)
    if from_stage:
        ctx.clear_from(from_stage, FLOW2_ORDER)

    steps = [
        ("highlight_selection", selection_flow2.run_highlight_selection),
        ("sound_design_plan_flow2", lambda: sound_design_stages.run_sound_design_plan_flow2(ctx)),
        ("sfx_prompt_craft", lambda: sound_design_stages.run_sfx_prompt_craft(ctx)),
        ("mmaudio_sfx_flow2", lambda: sfx_mmaudio.run_sfx_generation(ctx, profile="montage")),
        ("mix_flow2", assembly_flow2.run_mix_flow2),
        ("master_flow2", mastering.run_master_flow2),
    ]
    _run_steps(ctx, steps, from_stage, until_stage=until_stage, preclean_hook=preclean_hook)


def run_flow3(
    ctx: RunContext,
    *,
    from_stage: str | None = None,
    until_stage: str | None = None,
    preclean_hook: Callable[[str], None] | None = None,
) -> None:
    from interview_mux.gates import require_analysis_artifacts_complete

    require_g1_clear(ctx)
    require_analysis_artifacts_complete(ctx)
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
    _run_steps(ctx, steps, from_stage, until_stage=until_stage, preclean_hook=preclean_hook)
    ctx.log(
        "Flow 3 complete — copy ready for podcast directories.",
        level="success",
        stage="flow3",
        detail=str(ctx.path("flow_3_description/show_description.md")),
    )


def _run_steps(
    ctx: RunContext,
    steps: list,
    from_stage: str | None,
    *,
    until_stage: str | None = None,
    preclean_hook: Callable[[str], None] | None = None,
) -> None:
    from interview_mux.artifact_completeness import should_run_stage_for_artifact
    from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS

    start = 0
    if from_stage:
        names = [s[0] for s in steps]
        if from_stage not in names:
            raise ValueError(f"Unknown from_stage: {from_stage}")
        start = names.index(from_stage)
    flow_llm_runners = llm_stage_runners(ctx)
    slice_steps = steps[start:]
    planned: list[str] = []
    for name, _fn in slice_steps:
        if ctx.is_done(name) and from_stage != name:
            if name in STAGE_ARTIFACT_SCHEMAS and should_run_stage_for_artifact(ctx, name):
                planned.append(name)
            else:
                continue
        else:
            planned.append(name)
        if until_stage and name == until_stage:
            break
    total = len(planned) or 1
    plan_idx = 0
    for name, fn in slice_steps:
        if ctx.is_done(name) and from_stage != name:
            if name in STAGE_ARTIFACT_SCHEMAS and should_run_stage_for_artifact(ctx, name):
                ctx.log(
                    f"Re-running {name}: artifact incomplete or invalid",
                    level="info",
                    stage=name,
                )
            else:
                continue
        if resolve_before_stage_run(ctx, name) == "skipped":
            continue
        if name in planned:
            plan_idx = planned.index(name) + 1
        from interview_mux.web.job_progress import notify_stage_start

        notify_stage_start(
            ctx.run_id,
            name,
            index=plan_idx or 1,
            total=total,
            stages_planned=planned,
        )
        if preclean_hook is not None:
            preclean_hook(name)
        if name in ALL_LLM_STAGES:
            from interview_mux.llm_flow_hardening import maybe_require_upstream_llm_progress

            maybe_require_upstream_llm_progress(ctx, name)
        from interview_mux.write_staging import run_wrapped_stage

        token = active_pipeline_stage.set(name)
        try:
            run_wrapped_stage(ctx, name, fn)
        except Exception:
            ctx.log(
                f"Pipeline batch aborted at {name} ({plan_idx}/{total})",
                level="error",
                stage=name,
                detail={
                    "event": "batch_abort",
                    "failed_stage": name,
                    "stage_index": plan_idx,
                    "stage_total": total,
                    "stages_planned": planned,
                    "journey_kind": "execute",
                },
            )
            raise
        finally:
            active_pipeline_stage.reset(token)
        pause_after_stage_if_needed(ctx, name)
        if name in ALL_LLM_STAGES:
            drain_investigation_queue(ctx, flow_llm_runners)
            from interview_mux.artifact_cross_validate import maybe_cross_validate_after_stage

            maybe_cross_validate_after_stage(ctx, name)
        if until_stage and name == until_stage:
            break
