from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from interview_mux.gates import (
    check_g1_vo,
    check_transcript_review_pending,
    require_analysis_artifacts_complete,
    require_delivery_gates,
    require_g1_clear,
    require_transcript_review_clear,
)
from interview_mux.refinement_agenda import run_refinement_agenda
from interview_mux.refinement_passes import (
    after_gap_compose_hook,
    run_edl_narrative_refine,
    run_gap_framing_recompose,
    run_narrative_arc_refine,
    run_ranking_refine,
    run_sdp_intent_refine,
    run_selection_framing_apply,
    run_transitions_refine,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_execution_reuse import resolve_before_stage_run
from interview_mux.stages import analysis_extended
from interview_mux.stages import assembly
from interview_mux.stages import audio_preclean
from interview_mux.stages import edl_narrative_audit
from interview_mux.stages import gaps
from interview_mux.stages import ingest
from interview_mux.stages import interview_spine_stage
from interview_mux.stages import mastering
from interview_mux.stages import segmentation
from interview_mux.stages import selection
from interview_mux.stages import sonic_context_stages
from interview_mux.stages import sound_design_stages
from interview_mux.stages import sound_design_vo_finalize
from interview_mux.stages import sfx_mmaudio
from interview_mux.stages import podcast_publish
from interview_mux.stages import transcribe_local
from interview_mux.stages import audio_probes
from interview_mux.stages import transcript_review
from interview_mux.stages import understanding
from interview_mux.v2.config import (
    ALL_LLM_STAGES_V2,
    ANALYSIS_ORDER_V2,
    DELIVERY_ORDER_V2,
    effective_analysis_order,
    effective_delivery_order,
    v2_g1_optional,
)

# Backward-compat aliases for remaining imports.
ANALYSIS_ORDER: tuple[str, ...] = ANALYSIS_ORDER_V2
DELIVERY_ORDER: tuple[str, ...] = DELIVERY_ORDER_V2
ALL_LLM_STAGES = ALL_LLM_STAGES_V2
ANALYSIS_LLM_STAGES: frozenset[str] = frozenset(
    stage for stage in ALL_LLM_STAGES_V2 if stage in ANALYSIS_ORDER_V2
)

# Legacy flow orders removed — empty tuples for import compatibility.
FLOW2_ORDER: tuple[str, ...] = ()
FLOW3_ORDER: tuple[str, ...] = ()


def _analysis_stage_fns(ctx: RunContext) -> dict[str, Callable[[], None]]:
    return {
        "audio_preclean": lambda: audio_preclean.run_audio_preclean(ctx),
        "ingest": lambda: ingest.run_ingest(ctx),
        "transcribe": lambda: transcribe_local.run_transcribe(ctx),
        "audio_probe_build": lambda: audio_probes.run_audio_probe_build(ctx),
        "transcript_review_build": lambda: transcript_review.run_transcript_review_build(ctx),
        "source_acoustic_profile": lambda: understanding.run_source_acoustic_profile(ctx),
        "interview_spine_build": lambda: interview_spine_stage.run_interview_spine_build(ctx),
        "speaker_roles": lambda: understanding.run_speaker_roles(ctx),
        "source_topology_build": lambda: __import__(
            "interview_mux.source_topology", fromlist=["run_source_topology_build"]
        ).run_source_topology_build(ctx),
        "content_context": lambda: understanding.run_content_context(ctx),
        "talking_points_compose": lambda: understanding.run_talking_points_compose(ctx),
        "ideal_cuts_propose": lambda: understanding.run_ideal_cuts_propose(ctx),
        "ideal_cuts_materialize": lambda: __import__(
            "interview_mux.ideal_cuts", fromlist=["run_ideal_cuts_materialize"]
        ).run_ideal_cuts_materialize(ctx),
        "boundary_detection": lambda: segmentation.run_boundaries(ctx),
        "segment_classification": lambda: segmentation.run_classification(ctx),
        "content_brief_reanchor": lambda: understanding.run_content_brief_reanchor(ctx),
        "boundary_topic_resplit": lambda: segmentation.run_boundary_topic_resplit(ctx),
        "vernacular_segment_sanitize": lambda: audio_probes.run_vernacular_segment_sanitize(ctx),
        "low_conf_island_scan": lambda: __import__(
            "interview_mux.stages.low_conf_fuse_stages", fromlist=["run_low_conf_island_scan"]
        ).run_low_conf_island_scan(ctx),
        "connector_fuse_pass": lambda: __import__(
            "interview_mux.stages.low_conf_fuse_stages", fromlist=["run_connector_fuse_pass"]
        ).run_connector_fuse_pass(ctx),
        "sonic_context_build": lambda: sonic_context_stages.run_sonic_context_build(ctx),
        "sound_design_palettes": lambda: sound_design_stages.run_sound_design_palettes(ctx),
        "mastering_research_routing": lambda: __import__(
            "interview_mux.mastering_research", fromlist=["run_mastering_research_routing"]
        ).run_mastering_research_routing(ctx),
        "mastering_research_waves": lambda: __import__(
            "interview_mux.mastering_research", fromlist=["run_mastering_research_waves"]
        ).run_mastering_research_waves(ctx),
        "mastering_research_rollup": lambda: __import__(
            "interview_mux.mastering_research", fromlist=["run_mastering_research_rollup"]
        ).run_mastering_research_rollup(ctx),
        "mastering_shape_agenda": lambda: __import__(
            "interview_mux.mastering_shape_runtime", fromlist=["run_mastering_shape_agenda"]
        ).run_mastering_shape_agenda(ctx),
        "mastering_shape_candidates": lambda: __import__(
            "interview_mux.mastering_shape_runtime", fromlist=["run_mastering_shape_candidates"]
        ).run_mastering_shape_candidates(ctx),
        "mastering_plan_synthesize": lambda: __import__(
            "interview_mux.mastering_shape_runtime", fromlist=["run_mastering_plan_synthesize"]
        ).run_mastering_plan_synthesize(ctx),
        "missing_framing": lambda: _run_missing_framing_stage(ctx),
        "mastering_plan_confirm": lambda: __import__(
            "interview_mux.mastering_shape_runtime", fromlist=["run_mastering_plan_confirm"]
        ).run_mastering_plan_confirm(ctx),
        "gap_framing_compose": lambda: _run_gap_framing_compose_stage(ctx),
        "optimal_questions": lambda: _run_gap_framing_compose_stage(ctx),
        "delivery_brief_build": lambda: __import__(
            "interview_mux.delivery_brief", fromlist=["run_delivery_brief_build"]
        ).run_delivery_brief_build(ctx),
        "soundscape_policy_build": lambda: __import__(
            "interview_mux.soundscape_policy", fromlist=["run_soundscape_policy_build"]
        ).run_soundscape_policy_build(ctx),
        "episode_structure_compose": lambda: __import__(
            "interview_mux.episode_structure", fromlist=["run_episode_structure_compose"]
        ).run_episode_structure_compose(ctx),
        "vo_ingest": lambda: gaps.ingest_vo_pickup(ctx),
    }


def _delivery_stage_fns(ctx: RunContext) -> dict[str, Callable[[], None]]:
    return {
        "topic_coverage_audit": lambda: analysis_extended.run_topic_coverage(ctx),
        "narrative_arc_plan": lambda: analysis_extended.run_narrative_arc(ctx),
        "connector_fuse_pass_pre_ranking": lambda: __import__(
            "interview_mux.stages.low_conf_fuse_stages",
            fromlist=["run_connector_fuse_pass_pre_ranking"],
        ).run_connector_fuse_pass_pre_ranking(ctx),
        "full_master_ranking": lambda: selection.run_full_master_ranking(ctx),
        "nugget_corpus_mine": lambda: analysis_extended.run_nugget_corpus_mine(ctx),
        "information_package_plan": lambda: __import__(
            "interview_mux.information_packages", fromlist=["run_information_package_plan"]
        ).run_information_package_plan(ctx),
        "nugget_layup_compose": lambda: analysis_extended.run_nugget_layup_compose(ctx),
        # Refinement Pass (docs/cross-cutting/refinement-passes.md): L0 agenda + deterministic
        # recompose/refine stages. No LLM calls — gated by refinement_gate.decide_pass.
        "refinement_agenda": lambda: run_refinement_agenda(ctx, phase="confirm"),
        "gap_framing_recompose": lambda: run_gap_framing_recompose(ctx),
        "selection_framing_apply": lambda: run_selection_framing_apply(ctx),
        "ranking_refine": lambda: run_ranking_refine(ctx),
        "narrative_arc_refine": lambda: run_narrative_arc_refine(ctx),
        "transitions": lambda: selection.run_transitions(ctx),
        "transitions_refine": lambda: run_transitions_refine(ctx),
        "sound_design_plan": lambda: sound_design_stages.run_sound_design_plan(ctx),
        "sdp_intent_refine": lambda: run_sdp_intent_refine(ctx),
        "sound_design_vo_finalize": lambda: sound_design_vo_finalize.run_sound_design_vo_finalize(ctx),
        "edl_narrative_audit": lambda: edl_narrative_audit.run_edl_narrative_audit(ctx),
        "edl_narrative_refine": lambda: run_edl_narrative_refine(ctx),
        "edl": lambda: assembly.run_edl(ctx),
        "assembly_preview": lambda: assembly.run_preview(ctx),
        "listen_delight_audit": lambda: __import__(
            "interview_mux.listen_delight", fromlist=["run_listen_delight_audit"]
        ).run_listen_delight_audit(ctx),
        "music_palette_compose": lambda: __import__(
            "interview_mux.stages.music_palette_compose",
            fromlist=["run_music_palette_compose"],
        ).run_music_palette_compose(ctx),
        "sfx_prompt_craft": lambda: sound_design_stages.run_sfx_prompt_craft(ctx),
        "mmaudio_sfx": lambda: sfx_mmaudio.run_sfx_generation(ctx, profile="podcast"),
        "mix": lambda: assembly.run_mix(ctx),
        "junction_snip_qa": lambda: __import__(
            "interview_mux.junction_snip_qa", fromlist=["run_junction_snip_qa"]
        ).run_junction_snip_qa(ctx),
        "master_finalize": lambda: mastering.run_master_finalize(ctx),
        "episode_meta_build": lambda: podcast_publish.run_episode_meta_build(ctx),
        "episode_cover_prompt_craft": lambda: podcast_publish.run_episode_cover_prompt_craft(ctx),
        "podcast_encode_mp3": lambda: podcast_publish.run_podcast_encode_mp3(ctx),
        "episode_cover_generate": lambda: podcast_publish.run_episode_cover_generate(ctx),
        "podcast_publish": lambda: podcast_publish.run_podcast_publish(ctx),
    }


def _guard_stage_reuse(ctx: RunContext, stage: str) -> bool:
    """Return True when stage was satisfied via reuse (skip stage function)."""
    return resolve_before_stage_run(ctx, stage) == "skipped"


def _gap_path_skipped(ctx: RunContext) -> bool:
    from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
    from interview_mux.gap_vo_gates import gap_framing_enabled

    return gap_fill_was_skipped(ctx) or not gap_framing_enabled(ctx)


def _run_missing_framing_stage(ctx: RunContext) -> None:
    from interview_mux.gap_fill_eligibility import (
        assess_gap_fill_eligibility,
        gap_fill_auto_skip_enabled,
    )
    from interview_mux.gap_vo_gates import (
        gap_framing_enabled,
        maybe_auto_accept_gap_gate_defaults,
        require_gap_framing_decision_clear,
        require_gap_path_clear,
    )

    maybe_auto_accept_gap_gate_defaults(ctx)
    require_gap_framing_decision_clear(ctx)
    if not gap_framing_enabled(ctx):
        gaps.ensure_gap_fill_skipped(
            ctx,
            reason="gap_framing_disabled_by_operator",
            signals={"skip_signal": "gap_framing_no"},
        )
        return
    require_gap_path_clear(ctx)
    if _gap_path_skipped(ctx):
        return
    decision = assess_gap_fill_eligibility(ctx)
    if not decision.eligible:
        if gap_fill_auto_skip_enabled():
            gaps.ensure_gap_fill_skipped(ctx, reason=decision.reason, signals=decision.signals)
            return
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            f"Gap framing is enabled but this interview is not eligible for interviewer VO: "
            f"{decision.reason}",
            stage="missing_framing",
            reason="gap_fill_ineligible",
            detail={
                "signals": decision.signals,
                "hint": (
                    "Fix speaker roles / topology so a clear interviewer frame exists, "
                    "or explicitly choose No at G-Framing / Skip gap-fill. "
                    "Set analysis.gap_fill.auto_skip_when_ineligible=true only if silent skip is desired."
                ),
            },
            action_id="pipeline.gap_fill.ineligible_hard_stop",
        )
    gaps.run_missing_framing(ctx)


def _run_gap_framing_compose_stage(ctx: RunContext) -> None:
    if _gap_path_skipped(ctx):
        return
    gaps.run_gap_framing_compose(ctx)
    # Refinement Pass: seed the gap_vo champion/draft snapshot so
    # gap_framing_recompose (Pass 2) has a baseline to compare against.
    after_gap_compose_hook(ctx)


def _run_optimal_questions_stage(ctx: RunContext) -> None:
    _run_gap_framing_compose_stage(ctx)


def shared_analysis_chain_complete(ctx: RunContext) -> bool:
    """True when the last shared analysis stage (episode structure) finished."""
    return ctx.is_done("episode_structure_compose")


def maybe_finalize_shared_analysis(ctx: RunContext, *, strict: bool = False) -> bool:
    """Write analysis_complete.json when the shared analysis chain is ready. Idempotent."""
    from interview_mux.analysis_memory import update_completion_from_analysis
    from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

    if ctx.artifact_exists("analysis_complete.json"):
        return True
    if not shared_analysis_chain_complete(ctx):
        if not strict:
            return False
    if not _gap_path_skipped(ctx) and not gaps.gap_compose_stage_done(ctx):
        return False
    missing = check_g1_vo(ctx)
    if missing and not _gap_path_skipped(ctx):
        if v2_g1_optional():
            ctx.log(
                f"Analysis complete — G1 optional: {len(missing)} VO line(s) not recorded (continue or record in GUI).",
                level="info",
                stage="g1_vo_pickup",
            )
        elif strict:
            msg = f"Analysis complete with G1 pending. Record VO for {missing} → {ctx.path('vo_pickup')}"
            ctx.log(msg, level="warning", stage="g1_vo_pickup")
            raise SystemExit(msg)
        else:
            return False
    completion = update_completion_from_analysis(ctx)
    ctx.write_json(
        "analysis_complete.json",
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "run_id": ctx.run_id,
            "completion": completion,
        },
    )
    ctx.log(
        "Shared analysis complete — delivery stages unlocked.",
        level="success",
        stage="episode_structure_compose",
        detail={"gap_fill_skipped": _gap_path_skipped(ctx)},
    )
    return True


def _finalize_analysis_completion(ctx: RunContext) -> None:
    """Write analysis_complete.json when gap path finishes (LLM or skip)."""
    maybe_finalize_shared_analysis(ctx, strict=True)


def _run_single_stage_impl(ctx: RunContext, stage: str) -> None:
    """Run exactly one pipeline stage (reads all inputs from disk)."""
    if stage == "transcript_review":
        transcript_review.mark_transcript_review_complete(ctx)
        return
    if stage == "sfx_prompt_refine":
        sound_design_stages.run_sfx_prompt_refine(ctx)
        return

    analysis_order = effective_analysis_order()
    delivery_order = effective_delivery_order()

    if stage in analysis_order:
        if stage not in (
            "audio_preclean",
            "ingest",
            "transcribe",
            "transcript_review_build",
        ):
            from interview_mux.stages.transcript_review import maybe_auto_complete_transcript_review

            maybe_auto_complete_transcript_review(ctx)
            require_transcript_review_clear(ctx)
        if stage in ("missing_framing", "gap_framing_compose", "optimal_questions"):
            from interview_mux.gap_vo_gates import (
                gap_framing_enabled,
                maybe_auto_accept_gap_gate_defaults,
                require_gap_framing_decision_clear,
            )
            from interview_mux.source_topology import (
                maybe_auto_confirm_pickup_speaker,
                require_pickup_speaker_clear,
            )

            maybe_auto_accept_gap_gate_defaults(ctx)
            require_gap_framing_decision_clear(ctx)
            if gap_framing_enabled(ctx):
                maybe_auto_confirm_pickup_speaker(ctx)
                require_pickup_speaker_clear(ctx)
        fns = _analysis_stage_fns(ctx)
        if stage not in fns:
            raise ValueError(f"Unknown stage: {stage}")
        fns[stage]()
        if stage == "transcript_review_build" and check_transcript_review_pending(ctx):
            msg = (
                "Transcript review required. Open the GUI to correct ranked clips, then complete review."
            )
            ctx.log(msg, level="warning", stage="transcript_review")
            raise SystemExit(msg)
        if stage in ("gap_framing_compose", "optimal_questions"):
            _finalize_analysis_completion(ctx)
        return

    if stage in delivery_order:
        if not v2_g1_optional():
            require_g1_clear(ctx)
        if stage == "topic_coverage_audit":
            from interview_mux.progression_readiness import assert_delivery_ready

            assert_delivery_ready(ctx, target_stage="topic_coverage_audit")
        fns = _delivery_stage_fns(ctx)
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

    if stage == "vo_boundary_detect":
        from interview_mux.vo_boundary_detect import run_vo_boundary_detect

        run_vo_boundary_detect(ctx)
        return

    raise ValueError(f"Unknown stage: {stage}")


def run_single_stage(ctx: RunContext, stage: str) -> None:
    """Run exactly one pipeline stage (reads all inputs from disk)."""
    from interview_mux.artifact_lifecycle import LifecyclePhase, run_phase_checks
    from interview_mux.web.job_progress import notify_stage_start
    from interview_mux.write_staging import (
        after_stage_write_check,
        has_pending_writes,
        run_wrapped_stage,
        write_approval_enabled,
    )

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

    pre_errors = run_phase_checks(ctx, stage, LifecyclePhase.PRESTAGE)
    if pre_errors:
        raise ValueError(f"Pre-stage lifecycle failed for {stage}: {'; '.join(pre_errors[:4])}")

    if stage not in ("transcript_review", "sfx_prompt_refine") and _guard_stage_reuse(ctx, stage):
        from interview_mux.artifact_completeness import should_run_stage_for_artifact

        if should_run_stage_for_artifact(ctx, stage):
            ctx.log(
                f"Re-running {stage}: stage marked done but artifact incomplete",
                level="info",
                stage=stage,
            )
        elif write_approval_enabled() and has_pending_writes(ctx, stage):
            after_stage_write_check(ctx, stage)
            return
        else:
            return

    def _impl() -> None:
        setattr(ctx, "_lifecycle_consumer_stage", stage)
        try:
            _run_single_stage_impl(ctx, stage)
        finally:
            if hasattr(ctx, "_lifecycle_consumer_stage"):
                delattr(ctx, "_lifecycle_consumer_stage")

    try:
        from interview_mux.stage_resilience import record_resilience_event

        record_resilience_event(ctx, stage, event="stage_start", action="pass")
    except Exception:
        pass
    try:
        run_wrapped_stage(ctx, stage, _impl)
    except Exception as exc:
        if not getattr(ctx, "_recovery_retrying", False):
            result = None
            try:
                from interview_mux.recovery_controller import handle_stage_failure

                result = handle_stage_failure(ctx, stage, exc)
            except Exception:
                result = None
            if result is not None and result.status == "recovered":
                setattr(ctx, "_recovery_retrying", True)
                try:
                    ctx.log(
                        f"recovery_controller recovered {result.signature} "
                        f"via {result.playbook_id}",
                        level="warning",
                        stage=stage,
                    )
                    run_wrapped_stage(ctx, stage, _impl)
                    return
                except Exception as retry_exc:
                    exc = retry_exc
                finally:
                    setattr(ctx, "_recovery_retrying", False)
        try:
            from interview_mux.stage_resilience import escalate_stage_failure, record_resilience_event

            record_resilience_event(
                ctx,
                stage,
                event="stage_fail",
                action="halt",
                reasons=[str(exc)[:240]],
            )
            escalate_stage_failure(
                ctx,
                stage,
                failed_invariant=str(exc)[:400],
                evidence={"error_class": type(exc).__name__},
            )
        except Exception:
            pass
        raise


def run_analysis(
    ctx: RunContext,
    *,
    from_stage: str | None = None,
    until_stage: str | None = None,
    invalidate: bool = False,
) -> None:
    from interview_mux.artifact_completeness import should_run_stage_for_artifact
    from interview_mux.web.job_progress import notify_stage_start
    from interview_mux.write_staging import run_wrapped_stage

    analysis_order = effective_analysis_order()
    if (
        not invalidate
        and from_stage
        and (
            ctx.artifact_exists("understanding/gap_report.json")
            or ctx.is_done("gap_framing_compose")
        )
        and from_stage in analysis_order
        and "gap_framing_compose" in analysis_order
        and analysis_order.index(from_stage) < analysis_order.index("gap_framing_compose")
    ):
        ctx.log(
            f"spine freeze: refusing rewind from {from_stage} past existing gap artifacts",
            level="warning",
            stage=from_stage,
        )
        from_stage = "gap_framing_compose"
    if from_stage and invalidate:
        ctx.clear_from(from_stage, analysis_order)

    stages = _analysis_stage_fns(ctx)
    start_idx = 0
    order_keys = [s for s in analysis_order if s in stages]
    if from_stage:
        if from_stage not in stages:
            raise ValueError(f"Unknown from_stage: {from_stage}")
        start_idx = order_keys.index(from_stage) if from_stage in order_keys else list(stages.keys()).index(from_stage)

    stage_items = [(k, stages[k]) for k in order_keys[start_idx:]]
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
        notify_stage_start(
            ctx.run_id,
            name,
            index=plan_idx,
            total=total,
            stages_planned=planned,
        )
        run_wrapped_stage(ctx, name, fn)
        if until_stage and name == until_stage:
            break
        if name == "transcript_review_build" and check_transcript_review_pending(ctx):
            msg = (
                "Analysis paused for transcript review. Correct STT in the GUI, "
                "then complete review before continuing."
            )
            ctx.log(msg, level="warning", stage="transcript_review")
            raise SystemExit(msg)

    if check_transcript_review_pending(ctx):
        msg = "Transcript review incomplete. Finish STT corrections in the GUI before downstream stages."
        ctx.log(msg, level="warning", stage="transcript_review")
        raise SystemExit(msg)

    if until_stage and until_stage != "optimal_questions":
        return

    from interview_mux.analysis_memory import update_completion_from_analysis

    completion = update_completion_from_analysis(ctx)
    missing = check_g1_vo(ctx)
    if missing and not v2_g1_optional():
        msg = f"Analysis complete with G1 pending. Record VO for {missing} → {ctx.path('vo_pickup')}"
        ctx.log(msg, level="warning", stage="g1_vo_pickup")
        raise SystemExit(msg)
    if missing and v2_g1_optional():
        ctx.log(
            f"Analysis complete — optional G1: {len(missing)} VO line(s) pending.",
            level="info",
            stage="g1_vo_pickup",
        )

    ctx.write_json(
        "analysis_complete.json",
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "run_id": ctx.run_id,
            "completion": completion,
        },
    )


def run_delivery(
    ctx: RunContext,
    *,
    from_stage: str | None = None,
    until_stage: str | None = None,
    preclean_hook: Callable[[str], None] | None = None,
    invalidate: bool = False,
) -> None:
    if not v2_g1_optional():
        require_g1_clear(ctx)
    require_analysis_artifacts_complete(ctx)
    require_delivery_gates(ctx, from_stage=from_stage)

    delivery_order = effective_delivery_order()
    if from_stage and invalidate:
        ctx.clear_from(from_stage, delivery_order)

    stages = _delivery_stage_fns(ctx)
    steps = [(name, stages[name]) for name in delivery_order if name in stages]
    _run_steps(ctx, steps, from_stage, until_stage=until_stage, preclean_hook=preclean_hook)


def _run_steps(
    ctx: RunContext,
    steps: list[tuple[str, Callable[[], None]]],
    from_stage: str | None,
    *,
    until_stage: str | None = None,
    preclean_hook: Callable[[str], None] | None = None,
) -> None:
    from interview_mux.artifact_completeness import should_run_stage_for_artifact
    from interview_mux.gap_fill_eligibility import filter_visible_job_stages
    from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS
    from interview_mux.web.job_progress import notify_stage_start
    from interview_mux.write_staging import run_wrapped_stage

    start = 0
    if from_stage:
        names = [s[0] for s in steps]
        if from_stage not in names:
            raise ValueError(f"Unknown from_stage: {from_stage}")
        start = names.index(from_stage)

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

    visible_planned = filter_visible_job_stages(ctx, planned)
    total = len(visible_planned) or 1
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
        if name in visible_planned:
            plan_idx = visible_planned.index(name) + 1
        notify_stage_start(
            ctx.run_id,
            name,
            index=plan_idx if name in visible_planned else max(plan_idx, 1),
            total=total,
            stages_planned=visible_planned,
        )
        if preclean_hook is not None:
            preclean_hook(name)
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
        if until_stage and name == until_stage:
            break
