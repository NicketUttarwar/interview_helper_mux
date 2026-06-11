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
        "optimal_questions",
    }
)

FLOW_CRITICAL_LLM_STAGES = frozenset(
    {
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "highlight_selection",
        "podcast_show_description",
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
)

# Immediate upstream LLM stage for pipeline pre-checks (None = no LLM upstream).
LLM_UPSTREAM_STAGE: dict[str, str | None] = {
    "speaker_roles": None,
    "content_context": "speaker_roles",
    "boundary_detection": "content_context",
    "segment_classification": "boundary_detection",
    "content_brief_reanchor": "segment_classification",
    "sound_design_palettes": "content_brief_reanchor",
    "missing_framing": "content_brief_reanchor",
    "optimal_questions": "missing_framing",
    "topic_coverage_audit": "optimal_questions",
    "narrative_arc_plan": "topic_coverage_audit",
    "full_master_ranking": "narrative_arc_plan",
    "transitions": "full_master_ranking",
    "highlight_selection": "optimal_questions",
    "sound_design_plan_flow1": "full_master_ranking",
    "sound_design_plan_flow2": "highlight_selection",
    "podcast_show_description": "full_master_ranking",
}


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
    """Block ElevenLabs/mix spend when upstream craft artifacts are incomplete."""
    if not flow_hardening_enabled() or not is_spend_block_stage(stage_key):
        return
    from interview_mux.artifact_completeness import artifact_status
    from interview_mux.g15_prompt_review import can_run_elevenlabs_generation

    if stage_key.startswith("elevenlabs_sfx"):
        ok, msg = can_run_elevenlabs_generation(ctx)
        if not ok:
            raise SystemExit(msg or "G1.5: prompt approval required before ElevenLabs generation.")
        rel = "sound_design/elevenlabs_prompts.json"
        if artifact_status(rel, ctx) != "complete":
            raise SystemExit(
                f"Spend gate: {rel} incomplete. Run elevenlabs_prompt_craft and approve prompts first."
            )
    if stage_key in ("mix_flow1", "mix_flow2"):
        if flow_hardening_cfg().get("block_mix_without_sfx_when_enabled"):
            flow = "flow1" if stage_key == "mix_flow1" else "flow2"
            from interview_mux.sdp_cross_validate import validate_pre_mix

            errors = validate_pre_mix(ctx, flow)
            if errors:
                raise SystemExit(f"Mix gate: {'; '.join(errors[:3])}")


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
    """True when stage envelope and on-disk producer artifact are acceptable for progression."""
    if envelope.get("status") != "complete":
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

    rel = producer_artifact_path(stage_key)
    if rel and stage_key in STAGE_ARTIFACT_SCHEMAS:
        if artifact_status(rel, ctx) != "complete":
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

    if not flow_hardening_enabled(cfg):
        ctx.mark_done(stage_key)
        return True

    fh = flow_hardening_cfg(cfg)
    critical = stage_key in ALL_CRITICAL_LLM_STAGES
    if critical and fh.get("strict_critical_stages", True):
        rel = producer_artifact_path(stage_key) or "(no artifact)"
        status = envelope.get("status", "?")
        needs = envelope.get("needs") or []
        schema_bit = f"; schema_errors={schema_errors[:2]}" if schema_errors else ""
        ctx.log(
            f"Stage {stage_key} failed hardening (status={status}) — pipeline halted.",
            level="action",
            stage=stage_key,
            detail={"artifact": rel, "needs": needs[:3], "schema_errors": (schema_errors or [])[:4]},
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
        raise SystemExit(
            f"Prerequisite stage {upstream_stage} is not complete. "
            f"Run analysis from --from-stage {upstream_stage}."
        )
    rel = producer_artifact_path(upstream_stage)
    if rel and artifact_status(rel, ctx) != "complete":
        raise SystemExit(
            f"Prerequisite artifact {rel} from stage {upstream_stage} is incomplete. "
            f"Use Fill gaps or re-run --from-stage {upstream_stage}."
        )


def maybe_require_upstream_llm_progress(ctx: RunContext, stage_key: str) -> None:
    """When hardening is on, verify immediate upstream LLM stage before running stage_key."""
    if not flow_hardening_enabled():
        return
    upstream = LLM_UPSTREAM_STAGE.get(stage_key)
    if upstream:
        require_llm_stage_progress(ctx, upstream)
