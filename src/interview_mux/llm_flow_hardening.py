"""Flow-hardening policy: stage completion truth, fail-closed critical path."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_completeness import artifact_status
from interview_mux.config import merged_config
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS, STAGE_ARTIFACT_SCHEMAS
from interview_mux.run_context import RunContext

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
    "full_master_ranking": "narrative_arc_plan",
    "transitions": "full_master_ranking",
    "sound_design_plan": "transitions",
    "edl_narrative_audit": "sound_design_plan",
    "sfx_prompt_craft": "sound_design_plan",
    "episode_meta_build": None,
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
        ctx.mark_done(stage_key)
        return True

    if stage_key == "segment_classification":
        from interview_mux.segment_good_enough import try_good_enough_advance

        ge = try_good_enough_advance(ctx, stage_key, None)
        if ge.cleared:
            ctx.mark_done(stage_key)
            from interview_mux.gui_job_reconcile import reconcile_llm_gate_if_cleared

            reconcile_llm_gate_if_cleared(ctx, stage_key)
            return True

    if not flow_hardening_enabled(cfg):
        ctx.mark_done(stage_key)
        return True

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
    if not ctx.is_done(upstream_stage):
        exit_msg = (
            f"Prerequisite stage {upstream_stage} is not complete. "
            f"Run analysis from --from-stage {upstream_stage}."
        )
        ctx.log(exit_msg, level="error", stage=upstream_stage)
        raise SystemExit(exit_msg)
    rel = producer_artifact_path(upstream_stage)
    if not rel:
        return
    from interview_mux.llm_output_resilience import upstream_artifact_acceptable

    if upstream_artifact_acceptable(upstream_stage, rel, ctx):
        return
    exit_msg = (
        f"Prerequisite artifact {rel} from stage {upstream_stage} is incomplete. "
        f"Use Fill gaps or re-run --from-stage {upstream_stage}."
    )
    ctx.log(exit_msg, level="error", stage=upstream_stage)
    raise SystemExit(exit_msg)


def maybe_require_upstream_llm_progress(ctx: RunContext, stage_key: str) -> None:
    """When hardening is on, verify immediate upstream LLM stage before running stage_key."""
    if not flow_hardening_enabled():
        return
    upstream = resolve_llm_upstream_stage(ctx, stage_key)
    if upstream:
        require_llm_stage_progress(ctx, upstream)
