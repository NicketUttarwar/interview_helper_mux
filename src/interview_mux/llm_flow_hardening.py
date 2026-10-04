"""Flow-hardening policy: stage completion truth, fail-closed critical path."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_completeness import artifact_status
from interview_mux.config import merged_config
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS, STAGE_ARTIFACT_SCHEMAS
from interview_mux.run_context import RunContext
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER
from interview_mux.stage_completion import heal_or_refuse_mark

CRITICAL_LLM_STAGES = frozenset(
    {
        "speaker_roles",
        "content_context",
        "boundary_detection",
        "segment_classification",
        "content_brief_reanchor",
        "missing_framing",
        "gap_framing_compose",
        "optimal_questions",
    }
)

FLOW_CRITICAL_LLM_STAGES = frozenset(
    {
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "transitions",
        "sound_design_plan",
        "edl_narrative_audit",
    }
)

ALL_CRITICAL_LLM_STAGES = CRITICAL_LLM_STAGES | FLOW_CRITICAL_LLM_STAGES

ANALYSIS_READY_ARTIFACT_PATHS = (
    "understanding/speakers.json",
    "understanding/content_brief.json",
    "segments/manifest.json",
    "understanding/gap_evaluations.json",
    "understanding/gap_report.json",
    "understanding/analysis_state.json",
    "understanding/delivery_brief.json",
)

# Immediate upstream LLM stage for pipeline pre-checks (None = no LLM upstream).
LLM_UPSTREAM_STAGE: dict[str, str | None] = {
    "speaker_roles": None,
    "content_context": "speaker_roles",
    "boundary_detection": "content_context",
    "segment_classification": "boundary_detection",
    "content_brief_reanchor": "segment_classification",
    "boundary_topic_resplit": "content_brief_reanchor",
    "sound_design_palettes": "boundary_topic_resplit",
    "missing_framing": "boundary_topic_resplit",
    "optimal_questions": "missing_framing",
    "gap_framing_compose": "missing_framing",
    "delivery_brief_build": "gap_framing_compose",
    "topic_coverage_audit": "delivery_brief_build",
    "narrative_arc_plan": "topic_coverage_audit",
    "chapter_close_hitch": "narrative_arc_plan",
    "full_master_ranking": "connector_fuse_pass_pre_ranking",
    "air_script_compose": "full_master_ranking",
    "nugget_corpus_mine": "air_script_compose",
    "nugget_layup_compose": "information_package_plan",
    "information_package_plan": "nugget_corpus_mine",
    "transitions": "nugget_layup_compose",
    "sound_design_plan": "transitions",
    "edl_narrative_audit": "sound_design_plan",
    "sfx_prompt_craft": "sound_design_plan",
    "episode_meta_build": None,
    "master_transcript_build": None,
    "episode_cover_prompt_craft": "episode_meta_build",
}


def resolve_llm_upstream_stage(ctx: RunContext, stage_key: str) -> str | None:
    """Upstream LLM stage (None = no LLM upstream)."""
    _ = ctx
    return LLM_UPSTREAM_STAGE.get(stage_key)


def flow_hardening_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = cfg or merged_config()
    return (resolved.get("analysis") or {}).get("flow_hardening") or {}


def flow_hardening_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(flow_hardening_cfg(cfg).get("enabled", True))


def spend_block_stages(cfg: dict[str, Any] | None = None) -> frozenset[str]:
    raw = flow_hardening_cfg(cfg).get("spend_block_stages") or []
    if isinstance(raw, list):
        return frozenset(str(s) for s in raw)
    return frozenset()


def is_spend_block_stage(stage_key: str, cfg: dict[str, Any] | None = None) -> bool:
    return stage_key in spend_block_stages(cfg)


def require_spend_artifacts_complete(ctx: RunContext, stage_key: str) -> None:
    """Block SFX/mix spend when upstream craft artifacts are incomplete."""
    if not flow_hardening_enabled() or not is_spend_block_stage(stage_key):
        return
    from interview_mux.artifact_completeness import artifact_status
    from interview_mux.sfx_prompt_review import can_run_sfx_generation

    if stage_key.startswith("mmaudio_sfx"):
        ok, msg = can_run_sfx_generation(ctx)
        if not ok:
            exit_msg = msg or "G1.5: prompt approval required before SFX generation."
            ctx.log(exit_msg, level="error", stage=stage_key)
            raise SystemExit(exit_msg)
        rel = "sound_design/sfx_prompts.json"
        if artifact_status(rel, ctx) != "complete":
            exit_msg = (
                f"Spend gate: {rel} incomplete. Run sfx_prompt_craft and approve prompts first."
            )
            ctx.log(exit_msg, level="error", stage=stage_key)
            raise SystemExit(exit_msg)
    if stage_key == "mix":
        from interview_mux.gates import require_post_listen_clear

        require_post_listen_clear(ctx, stage=stage_key)
        # HAU speech-first: seats assembly before beds — skip SFX/mmaudio spend gates.
        try:
            from interview_mux.mix_junction_seat import beds_deferred_for_mix

            if beds_deferred_for_mix(ctx):
                return
        except Exception:
            pass
        sound_cfg = merged_config().get("sound_design") or {}
        if bool(sound_cfg.get("block_mix_on_mmaudio_qa_fail", False)):
            if ctx.artifact_exists("sound_design/mmaudio_qa.json"):
                qa = ctx.read_json("sound_design/mmaudio_qa.json")
                rows = qa.get("assets") if isinstance(qa, dict) else []
                failing = []
                for row in rows or []:
                    if not isinstance(row, dict):
                        continue
                    aid = str(row.get("asset_id") or "")
                    verdict = str(row.get("verdict") or "").lower()
                    status = str(row.get("generation_status") or "").lower()
                    if verdict == "fail" or status in {"failed", "placeholder"}:
                        if aid:
                            failing.append(aid)
                if failing:
                    from interview_mux.mix_completeness import qa_failures_that_block_mix

                    failing = sorted(qa_failures_that_block_mix(ctx, failing))
                if failing:
                    exit_msg = f"Mix gate: mmaudio_qa failed asset(s): {', '.join(sorted(set(failing))[:6])}"
                    ctx.log(exit_msg, level="error", stage=stage_key)
                    raise SystemExit(exit_msg)
        if flow_hardening_cfg().get("block_mix_without_sfx_when_enabled"):
            from interview_mux.coverage_limits import soft_progression_enabled
            from interview_mux.creative_delivery import creative_delivery_required

            # Soft progression must not bypass SFX completeness when creative delivery
            # is required — that shipped source-like masters with thin/missing SFX.
            if soft_progression_enabled() and not creative_delivery_required():
                ctx.log(
                    "Mix gate: block_mix_without_sfx skipped (soft_progression)",
                    level="warning",
                    stage=stage_key,
                )
            else:
                flow = "podcast"
                from interview_mux.sdp_cross_validate import validate_pre_mix

                errors = validate_pre_mix(ctx, flow)
                if not ctx.artifact_exists("sound_design/mmaudio_qa.json"):
                    errors = list(errors) + ["sound_design/mmaudio_qa.json missing"]
                if errors:
                    exit_msg = f"Mix gate: {'; '.join(errors[:3])}"
                    ctx.log(exit_msg, level="error", stage=stage_key)
                    raise SystemExit(exit_msg)


def is_critical_stage(stage_key: str) -> bool:
    return stage_key in ALL_CRITICAL_LLM_STAGES


def is_soft_llm_stage(stage_key: str) -> bool:
    return stage_key in _soft_llm_stages()


def _soft_llm_stages() -> frozenset[str]:
    return frozenset(STAGE_ARTIFACT_SCHEMAS.keys() - ALL_CRITICAL_LLM_STAGES)


def _blocking_non_operator_needs(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        n
        for n in envelope.get("needs") or []
        if n.get("blocking") and n.get("type") != "operator"
    ]


def producer_artifact_path(stage_key: str) -> str | None:
    return STAGE_ARTIFACT_DISK_PATHS.get(stage_key)


def llm_stage_progress_ok(
    ctx: RunContext,
    stage_key: str,
    envelope: dict[str, Any],
    *,
    schema_errors: list[str] | None = None,
    arbiter_result: dict[str, Any] | None = None,
    routed_via_collate: bool = False,
    cfg: dict[str, Any] | None = None,
) -> bool:
    """True when stage envelope and producer artifact pass strict acceptance."""
    cfg = cfg or merged_config()

    if envelope.get("status") != "complete":
        return False
    trunc_meta = (envelope.get("_llm_meta") or {}).get("truncation_escalation") or {}
    if trunc_meta.get("final_flags"):
        return False
    if _blocking_non_operator_needs(envelope):
        return False

    fh = flow_hardening_cfg(cfg)
    if flow_hardening_enabled(cfg) and fh.get("halt_on_schema_errors_with_accept", True):
        if schema_errors:
            return False

    if flow_hardening_enabled(cfg) and arbiter_result is not None:
        from interview_mux.analysis_memory import should_merge_envelope

        if not should_merge_envelope(
            arbiter_result,
            envelope,
            routed_via_collate=routed_via_collate,
        ):
            return False

    routing = envelope.get("_routing_meta") or {}
    if routing.get("structural_repair_cleared"):
        from interview_mux.stage_acceptance import stage_acceptance_ok
        from interview_mux.write_staging import staged_path, write_approval_enabled

        rel = producer_artifact_path(stage_key)
        if rel:
            use_staged = write_approval_enabled() and staged_path(ctx, rel, stage_id=stage_key).is_file()
            return stage_acceptance_ok(
                ctx,
                stage_key,
                staged=use_staged,
                include_cross_validate=False,
            ).ok

    rel = producer_artifact_path(stage_key)
    if rel and stage_key in STAGE_ARTIFACT_SCHEMAS:
        from interview_mux.stage_acceptance import stage_acceptance_ok
        from interview_mux.write_staging import staged_path, write_approval_enabled

        use_staged = write_approval_enabled() and staged_path(ctx, rel, stage_id=stage_key).is_file()
        if use_staged or ctx.artifact_exists(rel):
            acceptance = stage_acceptance_ok(
                ctx,
                stage_key,
                staged=use_staged,
                include_cross_validate=False,
            )
            if not acceptance.ok:
                return False
        elif artifact_status(rel, ctx) != "complete":
            return False

    return True


def complete_llm_stage_or_halt(
    ctx: RunContext,
    stage_key: str,
    envelope: dict[str, Any],
    *,
    schema_errors: list[str] | None = None,
    arbiter_result: dict[str, Any] | None = None,
    routed_via_collate: bool = False,
    cfg: dict[str, Any] | None = None,
) -> bool:
    """
    Mark stage done when progress OK; halt critical failures when hardening enabled.
    Returns True if stage marked done.
    """
    ok = llm_stage_progress_ok(
        ctx,
        stage_key,
        envelope,
        schema_errors=schema_errors,
        arbiter_result=arbiter_result,
        routed_via_collate=routed_via_collate,
        cfg=cfg,
    )
    if ok:
        try:
            from interview_mux.done_authority import try_mark_done

            return bool(try_mark_done(ctx, stage_key))
        except Exception as exc:
            from interview_mux.artifact_ownership import AuthorityDenied

            if isinstance(exc, AuthorityDenied):
                return False
            raise

    if stage_key == "segment_classification":
        from interview_mux.segment_good_enough import try_good_enough_advance

        ge = try_good_enough_advance(ctx, stage_key, None)
        if ge.cleared:
            try:
                from interview_mux.done_authority import try_mark_done

                if not try_mark_done(ctx, stage_key):
                    return False
            except Exception as exc:
                from interview_mux.artifact_ownership import AuthorityDenied

                if isinstance(exc, AuthorityDenied):
                    return False
                raise
            from interview_mux.gui_job_reconcile import reconcile_llm_gate_if_cleared

            reconcile_llm_gate_if_cleared(ctx, stage_key)
            return True

    if not flow_hardening_enabled(cfg):
        try:
            from interview_mux.done_authority import try_mark_done

            return bool(try_mark_done(ctx, stage_key))
        except Exception as exc:
            from interview_mux.artifact_ownership import AuthorityDenied

            if isinstance(exc, AuthorityDenied):
                return False
            raise

    fh = flow_hardening_cfg(cfg)
    rel = producer_artifact_path(stage_key)
    critical = stage_key in ALL_CRITICAL_LLM_STAGES
    if critical and fh.get("strict_critical_stages", True):
        rel_disp = rel or "(no artifact)"
        status = envelope.get("status", "?")
        needs = envelope.get("needs") or []
        schema_bit = f"; schema_errors={schema_errors[:2]}" if schema_errors else ""
        ctx.log(
            f"Stage {stage_key} failed hardening (status={status}) — pipeline halted.",
            level="action",
            stage=stage_key,
            detail={"artifact": rel_disp, "needs": needs[:3], "schema_errors": (schema_errors or [])[:4]},
        )
        raise SystemExit(
            f"LLM stage gate ({stage_key}): artifact not complete or envelope not acceptable "
            f"(status={status}). Review understanding/stage_runs/{stage_key}/, fix artifacts, "
            f"then re-run from --from-stage {stage_key}.{schema_bit}"
        )

    ctx.log(
        f"Stage {stage_key}: soft LLM failure — not marking done (status={envelope.get('status')}).",
        level="warning",
        stage=stage_key,
    )
    return False


def require_llm_stage_progress(ctx: RunContext, upstream_stage: str) -> None:
    """Raise SystemExit when an upstream LLM stage is not done with complete artifact."""
    if not flow_hardening_enabled():
        return
    rel = producer_artifact_path(upstream_stage)
    if not rel:
        return
    from interview_mux.llm_output_resilience import upstream_artifact_acceptable

    if ctx.artifact_exists(rel) and upstream_artifact_acceptable(upstream_stage, rel, ctx):
        if not ctx.is_done(upstream_stage):
            heal_or_refuse_mark(ctx, upstream_stage, force=True)
        return
    if not ctx.is_done(upstream_stage):
        exit_msg = (
            f"Prerequisite stage {upstream_stage} is not complete. "
            f"Run analysis from --from-stage {upstream_stage}."
        )
        ctx.log(exit_msg, level="error", stage=upstream_stage)
        raise SystemExit(exit_msg)
    if upstream_artifact_acceptable(upstream_stage, rel, ctx):
        return
    exit_msg = (
        f"Prerequisite artifact {rel} from stage {upstream_stage} is incomplete. "
        f"Use Fill gaps or re-run --from-stage {upstream_stage}."
    )
    ctx.log(exit_msg, level="error", stage=upstream_stage)
    raise SystemExit(exit_msg)


def _seed_order_skip_stage(ctx: RunContext, stage_id: str) -> bool:
    """True when seed-order should treat ``stage_id`` as satisfied (e.g. deferred preclean)."""
    if stage_id != "audio_preclean":
        return False
    try:
        from interview_mux.automation_run import is_partially_accelerated_run
        from interview_mux.homunculus.packer import g0_closed
        from interview_mux.stage_completion import heal_or_refuse_mark
        from interview_mux.stages.audio_preclean import preclean_was_skipped

        if preclean_was_skipped(ctx):
            try:
                heal_or_refuse_mark(ctx, "audio_preclean", force=True)
            except Exception:
                pass
            return True
        meta: dict = {}
        if ctx.artifact_exists("run_meta.json"):
            raw = ctx.read_json("run_meta.json")
            if isinstance(raw, dict):
                meta = raw
        if not is_partially_accelerated_run(meta):
            return False
        if g0_closed(ctx):
            return False
        if ctx.is_done("audio_preclean"):
            return False
        return True
    except Exception:
        return False


def _earliest_incomplete_seed_stage(ctx: RunContext, stage_key: str) -> str | None:
    """First not-done seed-order stage before `stage_key`.

    After a complete master, ship stages must not rewind into unmarked holes
    (e.g. vo_synthesize inserted after edl/mix already finished).
    """
    from interview_mux.v2.config import SHIP_AFTER_MASTER
    from interview_mux.delivery_invariants import committed_master_wav

    # Freeze = seal: sticky-complete all freeze no-op stages before scanning.
    try:
        from interview_mux.seed_policy import seal_freeze_sticky_stages

        seal_freeze_sticky_stages(ctx)
    except Exception:
        pass

    post_master_ship = False
    try:
        from interview_mux.done_authority import honest_finalize_seeded

        post_master_ship = (
            stage_key in SHIP_AFTER_MASTER
            and committed_master_wav(ctx)
            and honest_finalize_seeded(ctx)
        )
    except Exception:
        post_master_ship = (
            stage_key in SHIP_AFTER_MASTER
            and committed_master_wav(ctx)
            and ctx.is_done("master_finalize")
        )
    for order in (ANALYSIS_ORDER, DELIVERY_ORDER):
        if stage_key not in order:
            continue
        earlier_list = list(order[: order.index(stage_key)])
        if post_master_ship:
            earlier_list = [
                s for s in earlier_list if s in SHIP_AFTER_MASTER or s == "master_finalize"
            ]
        for earlier in earlier_list:
            if _seed_order_skip_stage(ctx, earlier):
                continue
            if earlier in DELIVERY_ORDER:
                try:
                    from interview_mux.delivery_guardrails import seed_stage_complete

                    if seed_stage_complete(ctx, earlier):
                        continue
                except Exception:
                    if ctx.is_done(earlier):
                        continue
                # Orphan WAV: assembly present but .stage_done cleared → promote,
                # do not block mix/junction/finalize (exec_5404 seed thrash).
                if earlier == "assembly_preview":
                    try:
                        from interview_mux.delivery_guardrails import (
                            assembly_wav_present,
                            promote_complete_orphan_stage_done,
                            seed_stage_complete as _seed_ok,
                        )

                        if assembly_wav_present(ctx):
                            promote_complete_orphan_stage_done(
                                ctx, ("assembly_preview",)
                            )
                            if _seed_ok(ctx, "assembly_preview") or assembly_wav_present(
                                ctx
                            ):
                                continue
                    except Exception:
                        pass
                # Delight seed skip = progress clearance only (seed_complete or
                # quality_waived). waived_unattended is telemetry — never skip.
                if earlier == "listen_delight_audit":
                    try:
                        from interview_mux.delivery_guardrails import (
                            listen_delight_cleared_for_progress,
                        )

                        if listen_delight_cleared_for_progress(ctx):
                            continue
                    except Exception:
                        pass
                # Hard seat freeze + EDL done: framing apply is intentionally a
                # no-op — do not block mix/junction on an unmarked freeze pass.
                if earlier in {
                    "selection_framing_apply",
                    "gap_framing_recompose",
                } and stage_key in {
                    "mix",
                    "junction_snip_qa",
                    "master_finalize",
                    "edl_narrative_audit",
                }:
                    try:
                        from interview_mux.seed_policy import apply_seed_policy_skips

                        if apply_seed_policy_skips(ctx, earlier):
                            continue
                    except Exception:
                        pass
                    try:
                        from interview_mux.seat_authority import hard_freeze_active
                        from interview_mux.stage_completion import heal_or_refuse_mark

                        if earlier == "selection_framing_apply" and ctx.is_done(
                            "edl"
                        ) and hard_freeze_active(ctx):
                            if not ctx.is_done("selection_framing_apply"):
                                heal_or_refuse_mark(
                                    ctx, "selection_framing_apply", force=True
                                )
                            continue
                    except Exception:
                        pass
                # Junction autopsy committed for live assembly size but mtime skew
                # after mix touch — promote orphan rather than finalize thrash.
                if earlier == "junction_snip_qa" and stage_key in {
                    "master_finalize",
                    "master_transcript_build",
                }:
                    try:
                        from interview_mux.delivery_guardrails import (
                            promote_complete_orphan_stage_done,
                            seed_stage_complete as _seed_ok,
                        )
                        from interview_mux.homunculus.agenda import (
                            stage_outputs_present,
                        )

                        if stage_outputs_present(ctx, "junction_snip_qa"):
                            promote_complete_orphan_stage_done(
                                ctx, ("junction_snip_qa",)
                            )
                            if _seed_ok(ctx, "junction_snip_qa"):
                                continue
                    except Exception:
                        pass
                # Remutate can clear .stage_done on air_script_seams while plan +
                # mix remain — promote rather than rewind past a seated master path.
                if earlier in {"air_script_seams", "transitions"} and stage_key in {
                    "mix",
                    "junction_snip_qa",
                    "master_finalize",
                }:
                    try:
                        from interview_mux.delivery_guardrails import (
                            promote_complete_orphan_stage_done,
                            seed_stage_complete as _seed_ok,
                        )
                        from interview_mux.homunculus.agenda import (
                            stage_outputs_present,
                        )

                        if stage_outputs_present(ctx, earlier):
                            promote_complete_orphan_stage_done(ctx, (earlier,))
                            if _seed_ok(ctx, earlier):
                                continue
                    except Exception:
                        pass
                # Assembly already rendered: missing transition-pair WAVs are
                # mix last-chance work, not a vo_synthesize seed-front rewind —
                # BUT only when the *consumer* is mix/junction/finalize. Never
                # skip incomplete vo_synthesize when walking toward edl /
                # narrative (expanded WS2 O10).
                if (
                    earlier == "vo_synthesize"
                    and ctx.artifact_exists("master/assembly.wav")
                    and stage_key
                    in {
                        "mix",
                        "junction_snip_qa",
                        "master_finalize",
                        *SHIP_AFTER_MASTER,
                    }
                ):
                    try:
                        from interview_mux.delivery_guardrails import (
                            may_rewind_to_vo_synthesize,
                            record_wasted_work,
                        )

                        if not may_rewind_to_vo_synthesize(ctx):
                            record_wasted_work(
                                ctx,
                                event="refuse_vo_synthesize_rewind",
                                stage="vo_synthesize",
                                detail={"reason": "monotonic_seed_order"},
                            )
                            continue
                    except Exception:
                        pass
                    try:
                        from interview_mux.gates import check_g1_vo
                        from interview_mux.stage_completion import (
                            heal_or_refuse_mark,
                            stage_artifact_incompleteness,
                        )

                        if not check_g1_vo(ctx):
                            inc = stage_artifact_incompleteness(ctx, earlier)
                            if inc and "transition pairs missing" in str(inc):
                                continue
                    except Exception:
                        pass
                return earlier
            if not ctx.is_done(earlier):
                return earlier
        return None
    return None


def maybe_require_upstream_llm_progress(ctx: RunContext, stage_key: str) -> None:
    """When hardening is on, verify seed-order progress before running stage_key."""
    if not flow_hardening_enabled():
        return
    if stage_key == "chapter_close_hitch":
        try:
            latch = (
                ctx.read_json("mastering/chapter_close_hitch.json")
                if ctx.artifact_exists("mastering/chapter_close_hitch.json")
                else {}
            )
            if isinstance(latch, dict) and str(latch.get("status") or "") == "running":
                # Hitch archives its own upstreams, then restages them internally.
                return
        except Exception:
            pass
    earliest = _earliest_incomplete_seed_stage(ctx, stage_key)
    if earliest and earliest != stage_key:
        # Ordering exceptions live in one place (ISSUES entry 62).
        from interview_mux.ordering_authority import ordering_exempt

        if ordering_exempt(ctx, stage_key, earliest):
            return
        require_llm_stage_progress(ctx, earliest)
        return
    upstream = resolve_llm_upstream_stage(ctx, stage_key)
    if upstream:
        require_llm_stage_progress(ctx, upstream)
