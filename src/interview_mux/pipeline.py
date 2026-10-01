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
    RETIRED_REFINE_GHOSTS,
    after_gap_compose_hook,
    refuse_retired_refine,
    run_gap_framing_recompose,
    run_selection_framing_apply,
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
from interview_mux.stages import vo_line_adjudicate
from interview_mux.stages import vo_synthesize
from interview_mux.stage_completion import heal_or_refuse_mark
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

_STAGE_ID_ALIASES: dict[str, str] = {
    "selection": "selection_order_sanitize",
    "selection_order": "selection_order_sanitize",
    "gap": "gap_report_sanitize",
    "gap_report": "gap_report_sanitize",
    "air_contract": "air_contract_sanitize",
    "air": "air_contract_sanitize",
}


def canonical_stage_id(stage: str) -> str:
    """Normalize legacy GUI/API stage ids to pipeline stage keys."""
    key = str(stage or "").strip()
    return _STAGE_ID_ALIASES.get(key, key)


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
        "framing_posture_decide": lambda: __import__(
            "interview_mux.stages.framing_posture_decide",
            fromlist=["run_framing_posture_decide"],
        ).run_framing_posture_decide(ctx),
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
        "chapter_close_hitch": lambda: __import__(
            "interview_mux.chapter_close_hitch", fromlist=["run_chapter_close_hitch"]
        ).run_chapter_close_hitch(ctx),
        "connector_fuse_pass_pre_ranking": lambda: __import__(
            "interview_mux.stages.low_conf_fuse_stages",
            fromlist=["run_connector_fuse_pass_pre_ranking"],
        ).run_connector_fuse_pass_pre_ranking(ctx),
        "full_master_ranking": lambda: selection.run_full_master_ranking(ctx),
        "selection_order_sanitize": lambda: __import__(
            "interview_mux.artifact_sanitize.selection",
            fromlist=["run_selection_order_sanitize"],
        ).run_selection_order_sanitize(ctx),
        "air_script_compose": lambda: __import__(
            "interview_mux.air_script", fromlist=["run_air_script_compose"]
        ).run_air_script_compose(ctx),
        "nugget_corpus_mine": lambda: analysis_extended.run_nugget_corpus_mine(ctx),
        "information_package_plan": lambda: __import__(
            "interview_mux.information_packages", fromlist=["run_information_package_plan"]
        ).run_information_package_plan(ctx),
        "nugget_layup_compose": lambda: analysis_extended.run_nugget_layup_compose(ctx),
        "gap_report_sanitize": lambda: __import__(
            "interview_mux.artifact_sanitize.gap_report",
            fromlist=["run_gap_report_sanitize"],
        ).run_gap_report_sanitize(ctx),
        # Refinement Pass (docs/cross-cutting/refinement-passes.md): L0 agenda +
        # gap recompose / framing apply only. Ghost *_refine ids are retired (F-06).
        "refinement_agenda": lambda: run_refinement_agenda(ctx, phase="confirm"),
        "gap_framing_recompose": lambda: run_gap_framing_recompose(ctx),
        "selection_framing_apply": lambda: run_selection_framing_apply(ctx),
        "air_script_seams": lambda: __import__(
            "interview_mux.air_script", fromlist=["run_air_script_seams"]
        ).run_air_script_seams(ctx),
        "air_contract_sanitize": lambda: __import__(
            "interview_mux.artifact_sanitize.air_script",
            fromlist=["run_air_contract_sanitize"],
        ).run_air_contract_sanitize(ctx),
        "transitions": lambda: selection.run_transitions(ctx),
        "sound_design_plan": lambda: sound_design_stages.run_sound_design_plan(ctx),
        "sound_design_vo_finalize": lambda: sound_design_vo_finalize.run_sound_design_vo_finalize(ctx),
        "vo_line_adjudicate": lambda: vo_line_adjudicate.run_vo_line_adjudicate(ctx),
        "vo_synthesize": lambda: vo_synthesize.run_vo_synthesize(ctx),
        "edl_narrative_audit": lambda: edl_narrative_audit.run_edl_narrative_audit(ctx),
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
        "master_transcript_build": lambda: __import__(
            "interview_mux.asset_transcripts", fromlist=["run_master_transcript_build"]
        ).run_master_transcript_build(ctx),
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


def _skip_ineligible_gap_fill_unattended(ctx: RunContext) -> bool:
    """Silent skip only for true monologue / operator skip — never hosted interviews."""
    from interview_mux.gap_fill_eligibility import (
        assess_gap_fill_eligibility,
        silent_skip_allowed,
    )

    return silent_skip_allowed(assess_gap_fill_eligibility(ctx))


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
    # Hard contract input — do not burn LLM shards without a mastering plan (exec_13159).
    if not ctx.artifact_exists("mastering/mastering_plan.json"):
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            "missing_framing hard input mastering/mastering_plan.json is absent — "
            "resume mastering_plan_synthesize before gap evaluation",
            stage="missing_framing",
            reason="missing_hard_input_mastering_plan",
            detail={
                "hint": "Run mastering_plan_synthesize (or --from-stage mastering_plan_synthesize).",
                "resume_stage": "mastering_plan_synthesize",
            },
            action_id="pipeline.missing_framing.missing_hard_plan",
        )
    decision = assess_gap_fill_eligibility(ctx)
    if not decision.eligible:
        if gap_fill_auto_skip_enabled() or _skip_ineligible_gap_fill_unattended(ctx):
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
        from interview_mux.gap_fill_eligibility import assess_gap_fill_eligibility

        decision = assess_gap_fill_eligibility(ctx)
        gaps.ensure_gap_fill_skipped(ctx, reason=decision.reason, signals=decision.signals)
        return
    # Compose-safe admit: refuse hollow/sealed/incomplete missing_framing evals
    # before LLM compose (Phase 4A — pin upstream, not hollow compose).
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled
        from interview_mux.stage_completion import stage_artifact_incompleteness

        if gap_framing_enabled(ctx):
            mf_reason = stage_artifact_incompleteness(ctx, "missing_framing")
            if mf_reason:
                raise RuntimeError(
                    f"gap_framing_compose blocked — missing_framing incomplete: {mf_reason}"
                )
            # R5: hollow / absent mastering plan — refuse inventing narrative priors.
            shape_reason = _compose_shape_plan_admit_reason(ctx)
            if shape_reason:
                raise RuntimeError(
                    f"gap_framing_compose blocked — {shape_reason}"
                )
    except RuntimeError:
        raise
    except Exception as exc:
        ctx.log(
            f"gap_framing_compose: missing_framing preflight skipped: {exc}",
            level="warning",
            stage="gap_framing_compose",
        )
    gaps.run_gap_framing_compose(ctx)
    # Refinement Pass: seed the gap_vo champion/draft snapshot so
    # gap_framing_recompose (Pass 2) has a baseline to compare against.
    after_gap_compose_hook(ctx)


def _compose_shape_plan_admit_reason(ctx: RunContext) -> str | None:
    """R5: framing Yes requires a non-absent mastering plan artifact (advisory OK)."""
    rel = "mastering/mastering_plan.json"
    if not ctx.artifact_exists(rel):
        return (
            "mastering_plan missing — resume mastering_plan_confirm: "
            "gap_framing_compose needs a plan summary (soft-gate advisory allowed)"
        )
    try:
        plan = ctx.read_json(rel)
    except Exception:
        return "mastering_plan unreadable — resume mastering_plan_confirm"
    if not isinstance(plan, dict) or not plan:
        return "mastering_plan hollow — resume mastering_plan_synthesize"
    status = str(plan.get("plan_status") or "").strip().lower()
    if status in {"", "absent_legacy"} and not (
        plan.get("narrative_mode") or plan.get("montage_grammar") or plan.get("pov")
    ):
        return (
            "mastering_plan empty of narrative priors — resume mastering_plan_confirm"
        )
    return None


def _run_optimal_questions_stage(ctx: RunContext) -> None:
    _run_gap_framing_compose_stage(ctx)


def shared_analysis_chain_complete(ctx: RunContext) -> bool:
    """True when the last shared analysis stage is land-honest complete."""
    from interview_mux.done_authority import may_skip_as_complete

    return may_skip_as_complete(ctx, "episode_structure_compose")


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
    try:
        from interview_mux.execution_invariants import run_execution_invariants

        run_execution_invariants(ctx, reason="analysis_to_delivery", consumer_stage="topic_coverage_audit")
    except Exception:
        pass
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
        if getattr(ctx, "_homunculus_seed_walk", False) or getattr(
            ctx, "_homunculus_inner_stage", False
        ):
            raise SystemExit(
                "g0_pending: transcript_review operator must-act — "
                "driver owns complete_g0 / wait_for_operator_g0"
            )
        transcript_review.mark_transcript_review_complete(ctx)
        return
    if stage == "sfx_prompt_refine":
        sound_design_stages.run_sfx_prompt_refine(ctx)
        return
    if stage in RETIRED_REFINE_GHOSTS:
        refuse_retired_refine(stage)

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
                require_gap_path_clear,
            )
            from interview_mux.source_topology import (
                maybe_auto_confirm_pickup_speaker,
            )

            maybe_auto_accept_gap_gate_defaults(ctx)
            require_gap_framing_decision_clear(ctx)
            if gap_framing_enabled(ctx):
                maybe_auto_confirm_pickup_speaker(ctx)
                # Full ladder SSOT (pickup + voice-ref + delivery + consent).
                require_gap_path_clear(ctx)
        fns = _analysis_stage_fns(ctx)
        if stage not in fns:
            raise ValueError(f"Unknown stage: {stage}")
        fns[stage]()
        if stage == "transcript_review_build" and check_transcript_review_pending(ctx):
            # SystemExit would skip run_wrapped_stage's after_stage_write_check and
            # leave review_queue+clips in .pending_writes (exec_11871 G0 thrash).
            try:
                from interview_mux.write_staging import (
                    _commit_stage_writes,
                    has_pending_writes,
                    write_approval_enabled,
                )

                if not write_approval_enabled() and has_pending_writes(ctx, stage):
                    flushed = _commit_stage_writes(ctx, stage)
                    ctx.log(
                        f"transcript_review_build: flushed {len(flushed)} pending "
                        "path(s) before G0 pause",
                        level="info",
                        stage=stage,
                        detail={"flushed": flushed[:24]},
                    )
            except Exception as flush_exc:
                ctx.log(
                    f"transcript_review_build: pre-G0 flush failed: {flush_exc}",
                    level="warning",
                    stage=stage,
                )
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
    from interview_mux.artifact_lifecycle import (
        LifecyclePhase,
        prestage_refused,
        run_phase_checks,
    )
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
        ctx=ctx,
    )
    try:
        from interview_mux.delivery_recovery import MUSIC_BEFORE_MIX
        from interview_mux.delivery_guardrails import music_epoch_complete, music_skip_allowed

        if stage in MUSIC_BEFORE_MIX and music_skip_allowed(ctx, stage) and music_epoch_complete(ctx):
            from interview_mux.done_authority import land_honest

            # Land Honesty: hollow .stage_done must not skip regenerate.
            if not land_honest(ctx, stage):
                # TH1b music-epoch skip: heal only marks when incompleteness empty
                # (epoch seal / WAVs present). Hollow force stamp is refused.
                heal_or_refuse_mark(ctx, stage, force=True)
            if land_honest(ctx, stage):
                ctx.log(
                    f"{stage}: music epoch complete — skip regenerate",
                    level="info",
                    stage=stage,
                )
                return
            # Not land-honest after heal → fall through and re-run.
    except Exception:
        pass
    try:
        from interview_mux.delivery_guardrails import (
            MIX_EPOCH_RUN_BLOCK,
            mix_epoch_block,
            upstream_stale_blockers,
        )

        if stage in MIX_EPOCH_RUN_BLOCK:
            mix_b = mix_epoch_block(ctx, stage=stage)
            if mix_b:
                raise ValueError(f"cannot run {stage}: delivery epoch {mix_b}")
        stale = upstream_stale_blockers(ctx, stage)
        if stale:
            raise ValueError(f"cannot run {stage}: stale upstream {', '.join(stale[:4])}")
    except ValueError:
        raise
    except Exception:
        pass
    ctx.log(
        f"Stage start: {stage}",
        level="action",
        stage=stage,
        detail={"journey_kind": "execute", "event": "stage_start"},
    )

    pre_errors = run_phase_checks(ctx, stage, LifecyclePhase.PRESTAGE)
    if pre_errors:
        raise ValueError(f"Pre-stage lifecycle failed for {stage}: {'; '.join(pre_errors[:4])}")

    # The non-fatal half of that call: an absent declared hard input is recorded as
    # a refusal rather than returned as an error, and a recorded refusal has to be
    # able to stop the stage without a `ValueError`. Returning leaves no done marker,
    # so the downstream rails (`stage_input_checks`, seed order, stage-body reads)
    # still own every refusal this channel does not cover.
    if prestage_refused(ctx, stage):
        return

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
        from interview_mux.homunculus.runtime import dispatch_stage, has_dispatch_ledger

        inner = bool(getattr(ctx, "_homunculus_inner_stage", False))
        if has_dispatch_ledger(ctx) and not inner:
            def _host(sid: str) -> None:
                prev = getattr(ctx, "_homunculus_inner_stage", False)
                ctx._homunculus_inner_stage = True
                try:
                    run_single_stage(ctx, sid)
                finally:
                    if prev:
                        ctx._homunculus_inner_stage = prev
                    elif hasattr(ctx, "_homunculus_inner_stage"):
                        delattr(ctx, "_homunculus_inner_stage")

            dispatch_stage(ctx, stage, _host, source="operator")
        else:
            run_wrapped_stage(ctx, stage, _impl)
        if stage in {"master_finalize", "master_transcript_build"} and ctx.artifact_exists(
            "master/master.wav"
        ):
            try:
                from interview_mux.homunculus.runtime import has_dispatch_ledger
                from interview_mux.homunculus.judge import after_complete_master

                if has_dispatch_ledger(ctx):
                    after_complete_master(ctx)
            except Exception:
                pass
    except Exception as exc:
        if not getattr(ctx, "_recovery_retrying", False):
            skip_recovery = False
            try:
                from interview_mux.homunculus.runtime import (
                    conductor_owns_control_flow,
                    recovery_allowed,
                )

                # Control flow: only a conductor can hold recovery for analysis.
                skip_recovery = conductor_owns_control_flow(ctx) and not recovery_allowed(
                    ctx, stage, exc=exc
                )
            except Exception:
                skip_recovery = False
            result = None
            if not skip_recovery:
                try:
                    from interview_mux.recovery_controller import handle_stage_failure

                    result = handle_stage_failure(ctx, stage, exc)
                except Exception:
                    result = None
            if result is not None and result.status == "recovered":
                # Post-Heal Accounting P11: identical/budget accounting already ran
                # inside handle_stage_failure → _append_action →
                # finalize_post_heal_accounting. Do not bump identical or stamp
                # budget_epoch here (anti-C / no silent second path).
                if (
                    result.playbook_id == "speaker_roles_dominant_fallback"
                    and ctx.artifact_exists("understanding/speakers.json")
                ):
                    from interview_mux.done_authority import land_honest

                    # Land Honesty: hollow stamp must not skip LLM re-run.
                    if land_honest(ctx, stage):
                        ctx.log(
                            f"recovery_controller recovered {result.signature} "
                            f"via {result.playbook_id} — skip LLM re-run",
                            level="warning",
                            stage=stage,
                        )
                        return
                resume = str(result.resume_stage or "").strip() or stage
                # Heal Success V5: prefer admit-clamped resume; do not blindly
                # re-run a failed consumer when recovery pinned a producer.
                try:
                    from interview_mux.heal_pin_authority import admit_resume

                    resume = admit_resume(
                        ctx,
                        resume,
                        current=stage,
                        error=str(exc)[:160],
                        intent="heal_success",
                    )
                except Exception:
                    pass
                setattr(ctx, "_recovery_retrying", True)
                try:
                    ctx.log(
                        f"recovery_controller recovered {result.signature} "
                        f"via {result.playbook_id} resume={resume}",
                        level="warning",
                        stage=stage,
                    )
                    if resume != stage:
                        # Propagate producer pin — do not fake-success the consumer.
                        raise RuntimeError(
                            f"Complete {resume} before running {stage} "
                            f"(recovery:{result.playbook_id})"
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
        # Flush sealable pending before re-raise so HC-3 pending_only does not
        # deadlock the next execute (vo_line wrote adjudication then raised).
        try:
            from interview_mux.write_staging import has_pending_writes

            if has_pending_writes(ctx, stage):
                heal_or_refuse_mark(ctx, stage, force=False)
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

    try:
        from interview_mux.stage_order_migration import migrate_stale_stage_order_on_resume

        migrate_stale_stage_order_on_resume(ctx)
    except Exception:
        pass

    analysis_order = effective_analysis_order()
    gap_compose_honest = False
    try:
        from interview_mux.done_authority import may_skip_as_complete

        gap_compose_honest = may_skip_as_complete(ctx, "gap_framing_compose")
    except Exception:
        gap_compose_honest = False
    if (
        not invalidate
        and from_stage
        and (
            ctx.artifact_exists("understanding/gap_report.json")
            or gap_compose_honest
        )
        and from_stage in analysis_order
        and "gap_framing_compose" in analysis_order
        and analysis_order.index(from_stage) < analysis_order.index("gap_framing_compose")
    ):
        # Do not spine-freeze bump past an open missing_framing incompleteness —
        # that hollow-finishes "Gap evaluation" and thrash-pins (exec_13181).
        keep_from = False
        try:
            from interview_mux.stage_completion import stage_artifact_incompleteness

            if stage_artifact_incompleteness(ctx, "missing_framing"):
                keep_from = True
        except Exception:
            keep_from = False
        if keep_from:
            ctx.log(
                f"spine freeze: keeping {from_stage} (missing_framing incompleteness open)",
                level="info",
                stage=from_stage,
            )
        else:
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
        from interview_mux.done_authority import may_skip_as_complete

        if may_skip_as_complete(ctx, name) and from_stage != name:
            if name in ANALYSIS_LLM_STAGES and should_run_stage_for_artifact(ctx, name):
                planned.append(name)
            else:
                continue
        else:
            planned.append(name)
        if until_stage and name == until_stage:
            break

    total = len(planned) or 1
    from interview_mux.homunculus.runtime import has_dispatch_ledger

    if (
        has_dispatch_ledger(ctx)
        and not getattr(ctx, "_homunculus_seed_walk", False)
        and planned
    ):
        from interview_mux.homunculus.agenda import run_homunculus_phase

        run_homunculus_phase(ctx, "analysis", planned)
        if check_transcript_review_pending(ctx):
            msg = (
                "Analysis paused for transcript review. Correct STT in the GUI, "
                "then complete review before continuing."
            )
            ctx.log(msg, level="warning", stage="transcript_review")
            raise SystemExit(msg)
        if until_stage and until_stage != "optimal_questions":
            return
        from interview_mux.homunculus.agenda import pending_analysis_for_delivery

        blocked = pending_analysis_for_delivery(ctx)
        if blocked:
            ctx.log(
                "Analysis incomplete — delivery prereqs missing: " + ", ".join(blocked),
                level="warning",
                stage=blocked[0],
            )
            return
        from interview_mux.analysis_memory import update_completion_from_analysis

        completion = update_completion_from_analysis(ctx)
        ctx.write_json(
            "analysis_complete.json",
            {
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "run_id": ctx.run_id,
                "completion": completion,
            },
        )
        return
    for idx, (name, fn) in enumerate(stage_items, start=1):
        from interview_mux.done_authority import may_skip_as_complete

        if may_skip_as_complete(ctx, name) and from_stage != name:
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
            ctx=ctx,
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


def stages_within_until(
    stages: list[str], order: list[str], until_stage: str | None
) -> list[str]:
    """Drop stages that sit after ``until_stage`` in ``order`` (ISSUES 98)."""
    if not until_stage or until_stage not in order:
        return list(stages)
    limit = order.index(until_stage)
    kept: list[str] = []
    for sid in stages:
        if sid in order and order.index(sid) > limit:
            continue
        kept.append(sid)
    return kept


def _run_delivery_conductor_until_stalled(
    ctx: RunContext, planned: list[str], run_phase: Any
) -> dict[str, Any]:
    """Re-enter the delivery conductor while each pass lands new stages.

    The conductor pins itself to the seed front and walks one producer per
    pass, then reports the rest as ``remaining_after``. Raising after every
    single landing made a 37-stage delivery need a resume per stage
    (ISSUES entry 47). Loop here while the done count grows and no master is
    committed; stop on the first pass that lands nothing and let the existing
    incomplete handling name the resume stage.
    """
    from interview_mux.done_authority import may_skip_as_complete
    from interview_mux.v2.config import DELIVERY_ORDER

    def _done_count() -> int:
        # Land-honest census between passes: a hollow stamp is not progress.
        return sum(1 for sid in DELIVERY_ORDER if may_skip_as_complete(ctx, sid))

    result: dict[str, Any] = {}
    for _pass in range(len(DELIVERY_ORDER) + 2):
        before = _done_count()
        result = run_phase(ctx, "delivery", planned)
        if not isinstance(result, dict):
            result = {}
        if (result.get("conductor") or {}).get("blocked_on_analysis"):
            break
        remaining = list(result.get("remaining_after") or [])
        if not remaining or ctx.final_path("master", "master.wav").is_file():
            break
        landed = _done_count() - before
        if landed <= 0:
            break
        ctx.log(
            f"delivery conductor landed {landed} stage(s); "
            f"{len(remaining)} remaining, re-entering from {remaining[0]}",
            level="info",
            stage=str(remaining[0]),
        )
    return result


def run_delivery(
    ctx: RunContext,
    *,
    from_stage: str | None = None,
    until_stage: str | None = None,
    preclean_hook: Callable[[str], None] | None = None,
    invalidate: bool = False,
) -> None:
    try:
        from interview_mux.stage_order_migration import migrate_stale_stage_order_on_resume

        migrate_stale_stage_order_on_resume(ctx)
    except Exception:
        pass

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
    if from_stage is not None:
        from interview_mux.artifact_ownership import assert_execute_from_stage

        from_stage = assert_execute_from_stage(ctx, str(from_stage or ""))
    if from_stage:
        names = [s[0] for s in steps]
        if from_stage not in names:
            raise ValueError(f"Unknown from_stage: {from_stage}")
        start = names.index(from_stage)

    slice_steps = steps[start:]
    try:
        from interview_mux.homunculus.agenda import prepare_delivery_guardrails

        prepare_delivery_guardrails(ctx, [name for name, _fn in slice_steps])
    except Exception:
        pass
    planned: list[str] = []
    for name, _fn in slice_steps:
        from interview_mux.done_authority import may_skip_as_complete

        if may_skip_as_complete(ctx, name) and from_stage != name:
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
    from interview_mux.homunculus.runtime import has_dispatch_ledger

    if (
        has_dispatch_ledger(ctx)
        and not getattr(ctx, "_homunculus_seed_walk", False)
        and planned
    ):
        from interview_mux.homunculus.agenda import run_homunculus_phase

        result = _run_delivery_conductor_until_stalled(ctx, planned, run_homunculus_phase)
        blocked = (result.get("conductor") or {}).get("blocked_on_analysis") if isinstance(result, dict) else None
        if blocked:
            raise RuntimeError(
                "Delivery blocked — analysis incomplete: " + ", ".join(str(s) for s in blocked)
            )
        remaining_after = list((result or {}).get("remaining_after") or [])
        # Filter remaining so ESR/raise pins seed-complete-ordered head (exec_13165).
        try:
            from interview_mux.delivery_guardrails import filter_delivery_candidates

            filtered = filter_delivery_candidates(ctx, remaining_after)
            if filtered:
                remaining_after = filtered
        except Exception:
            pass
        committed_master = ctx.final_path("master", "master.wav").is_file()
        if remaining_after and not committed_master:
            if isinstance(result, dict) and result.get("esr_wait"):
                lease = str(result.get("resume") or remaining_after[0])
                ctx.log(
                    f"Delivery ESR wait — walking producer {lease} without HARD sticky",
                    level="warning",
                    stage=lease,
                )
                # Refuse hollow success: agenda already walked the lease; if the
                # producer still has no outputs, raise so the driver resumes
                # (exec_13170: music ESR walk skipped → Finished without sound_design/).
                try:
                    from interview_mux.delivery_guardrails import seed_stage_complete
                    from interview_mux.mix_junction_seat import next_delivery_seat

                    landed = seed_stage_complete(ctx, lease)
                    if not landed:
                        resume = lease
                        if lease in {
                            "music_palette_compose",
                            "sfx_prompt_craft",
                            "mmaudio_sfx",
                        }:
                            resume = next_delivery_seat(ctx) or "mix"
                        raise RuntimeError(
                            "Delivery incomplete after conductor — ESR wait walk "
                            f"did not land {lease}; resume={resume}"
                        )
                except RuntimeError:
                    raise
                except Exception:
                    pass
                return
            try:
                from interview_mux.thrash_hardening import (
                    FAIL_CLASS_DELIVERY_BLOCKED,
                    canonical_resume_pin,
                )

                pin = canonical_resume_pin(
                    ctx, FAIL_CLASS_DELIVERY_BLOCKED, hint=remaining_after[0]
                )
            except Exception:
                pin = remaining_after[0]
            try:
                from interview_mux.execution_status import (
                    should_wait_incomplete_after_conductor,
                )

                wait_row = should_wait_incomplete_after_conductor(
                    ctx, pin=pin, remaining=remaining_after
                )
                if wait_row is not None:
                    lease = str(
                        wait_row.get("lease_stage") or pin or remaining_after[0]
                    )
                    # HAU speech-first: never hollow-return while MusicGen is the
                    # lease but only preview assembly exists (exec_13170).
                    try:
                        from interview_mux.mix_junction_seat import (
                            music_admit_block_reason,
                            next_delivery_seat,
                        )

                        if (
                            lease
                            in {
                                "music_palette_compose",
                                "sfx_prompt_craft",
                                "mmaudio_sfx",
                            }
                            and music_admit_block_reason(ctx)
                        ):
                            lease = next_delivery_seat(ctx) or "mix"
                    except Exception:
                        pass
                    ctx.log(
                        "Delivery incomplete after conductor — ESR wait "
                        f"({wait_row.get('why')}); resume={lease}",
                        level="warning",
                        stage=lease,
                    )
                    try:
                        from interview_mux.homunculus.agenda import walk_seed_agenda
                        from interview_mux.delivery_guardrails import seed_stage_complete

                        if not seed_stage_complete(ctx, lease):
                            walk_seed_agenda(
                                ctx,
                                [lease],
                                reason="esr_wait_incomplete_after_conductor",
                            )
                            if not seed_stage_complete(ctx, lease):
                                raise RuntimeError(
                                    "Delivery incomplete after conductor — ESR wait "
                                    f"did not land {lease}; resume={lease}"
                                )
                    except RuntimeError:
                        raise
                    except Exception:
                        raise RuntimeError(
                            "Delivery incomplete after conductor — ESR wait "
                            f"({wait_row.get('why')}); resume={lease}"
                        )
                    return
            except Exception:
                pass
            raise RuntimeError(
                "Delivery incomplete after conductor — remaining stages: "
                + ", ".join(str(s) for s in remaining_after[:12])
                + f"; resume={pin}"
            )
        if committed_master:
            from interview_mux.homunculus.agenda import (
                backfill_ship_holes_after_master,
                ship_after_master_remaining,
            )
            from interview_mux.homunculus.judge import after_complete_master

            # Ship outputs current for this master but unmarked after a
            # re-entry get their markers back here; stale ones are walked
            # again below (ISSUES 112).
            try:
                backfill_ship_holes_after_master(ctx)
            except Exception:
                pass

            # The engine's stop-before-publish boundary (partial mode) applies
            # to this walk too: it used to carry the run straight through
            # podcast_publish past the operator's sign-off (ISSUES 98).
            left = stages_within_until(
                ship_after_master_remaining(ctx),
                [name for name, _fn in steps],
                until_stage,
            )
            if left:
                # Pending/promoted master with failing PMQ must remutate — not
                # raise a ship-stage incomplete loop (exec_10066).
                publish_ok = False
                try:
                    if ctx.artifact_exists("master/post_master_quality.json"):
                        pmq = ctx.read_json("master/post_master_quality.json")
                        publish_ok = bool(
                            isinstance(pmq, dict) and pmq.get("publish_allowed")
                        )
                except Exception:
                    publish_ok = False
                if not publish_ok:
                    raise RuntimeError(
                        "Delivery incomplete after conductor — master present but "
                        "not publishable; remaining stages: "
                        + ", ".join(str(s) for s in (remaining_after or left)[:12])
                    )
                # Walk ship in-place (align with agenda delivery_walk_to_publish).
                try:
                    from interview_mux.homunculus.agenda import walk_seed_agenda

                    ctx.log(
                        "Delivery walking remaining ship stages "
                        f"({len(left)} stage(s))",
                        level="warning",
                        stage=left[0],
                    )
                    walk_seed_agenda(ctx, left, reason="delivery_walk_to_publish")
                except Exception as walk_exc:
                    raise RuntimeError(
                        "Delivery incomplete after conductor — remaining ship stages: "
                        + ", ".join(left)
                        + f"; walk_failed={walk_exc}"
                    ) from walk_exc
            after_complete_master(ctx)
        return
    plan_idx = 0
    for name, fn in slice_steps:
        from interview_mux.done_authority import may_skip_as_complete

        if may_skip_as_complete(ctx, name) and from_stage != name:
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
            ctx=ctx,
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
