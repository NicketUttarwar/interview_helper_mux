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
    "edl_narrative_audit": "sound_design_plan_flow1",
    # podcast_show_description and sfx_prompt_craft resolved per selected_flow — see resolve_llm_upstream_stage
}


def resolve_llm_upstream_stage(ctx: RunContext, stage_key: str) -> str | None:
    """Flow-aware upstream LLM stage (None = no LLM upstream)."""
    from interview_mux.gates import get_selected_flow

    flow = get_selected_flow(ctx)
    if stage_key == "podcast_show_description":
        if flow == "flow3":
            return "optimal_questions"
        return "full_master_ranking"
    if stage_key == "sfx_prompt_craft":
        if flow == "flow2":
            return "sound_design_plan_flow2"
        return "sound_design_plan_flow1"
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
    if stage_key in ("mix_flow1", "mix_flow2"):
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
            flow = "flow1" if stage_key == "mix_flow1" else "flow2"
            from interview_mux.sdp_cross_validate import validate_pre_mix

            errors = validate_pre_mix(ctx, flow)
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
    """True when stage envelope and on-disk producer artifact are acceptable for progression."""
    from interview_mux.llm_output_resilience import (
        artifact_mass_score,
        is_degraded_continue,
        is_spend_stage_strict,
        resilience_cfg,
    )

    cfg = cfg or merged_config()
    routing = envelope.get("_routing_meta") or {}
    persist_action = routing.get("persist_action")
    degraded = is_degraded_continue(cfg) and not is_spend_stage_strict(stage_key, cfg)

    fh = flow_hardening_cfg(cfg)
    if (
        flow_hardening_enabled(cfg)
        and fh.get("clarification_before_halt", True)
        and persist_action in ("partial", "full")
    ):
        from interview_mux.artifact_issue_triage import triage_enabled

        rel_early = producer_artifact_path(stage_key)
        if triage_enabled(cfg) and rel_early and ctx.artifact_exists(rel_early):
            return True

    if degraded and persist_action in ("partial", "full"):
        rel = producer_artifact_path(stage_key)
        if rel and ctx.artifact_exists(rel):
            mass_req = (resilience_cfg(cfg).get("min_artifact_mass") or {}).get(stage_key)
            if mass_req:
                raw = ctx.read_json(rel)
                data = raw if isinstance(raw, dict) else {}
                if artifact_mass_score(stage_key, data, cfg) > 0:
                    return True
            elif artifact_status(rel, ctx) in ("partial", "complete"):
                return True

    if envelope.get("status") != "complete" and not (degraded and persist_action == "partial"):
        return False
    if _blocking_non_operator_needs(envelope):
        return False

    fh = flow_hardening_cfg(cfg)
    if flow_hardening_enabled(cfg) and fh.get("halt_on_schema_errors_with_accept", True):
        if schema_errors and not degraded:
            return False

    if flow_hardening_enabled(cfg) and arbiter_result is not None and not degraded:
        from interview_mux.analysis_memory import should_merge_envelope

        if not should_merge_envelope(
            arbiter_result,
            envelope,
            routed_via_collate=routed_via_collate,
        ):
            return False

    rel = producer_artifact_path(stage_key)
    if rel and stage_key in STAGE_ARTIFACT_SCHEMAS:
        status = artifact_status(rel, ctx)
        if degraded and status in ("partial", "complete"):
            pass
        elif status != "complete":
            return False

    from interview_mux.null_field_policy import find_null_fields, null_policy_enabled, partition_nulls

    if null_policy_enabled(cfg):
        if rel and ctx.artifact_exists(rel):
            raw = ctx.read_json(rel)
            if isinstance(raw, dict):
                paths = find_null_fields(stage_key, raw)
                critical, _ = partition_nulls(stage_key, paths)
                if critical:
                    return False
        if routing.get("critical_null_paths"):
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

    from interview_mux.llm_output_resilience import (
        ResilienceReport,
        is_degraded_continue,
        is_spend_stage_strict,
        log_resilience_event,
        record_degraded_stage,
    )

    cfg = cfg or merged_config()
    degraded = is_degraded_continue(cfg) and not is_spend_stage_strict(stage_key, cfg)
    routing = envelope.get("_routing_meta") or {}
    resilience_raw = routing.get("resilience_report") or {}
    rel = producer_artifact_path(stage_key)

    if degraded and routing.get("persist_action") in ("partial", "full") and rel and ctx.artifact_exists(rel):
        report = ResilienceReport(
            stage_key=stage_key,
            artifact_path=rel,
            summary=str(resilience_raw.get("summary") or "Partial artifact persisted"),
            stripped=list(resilience_raw.get("stripped") or []),
            generated=list(resilience_raw.get("generated") or []),
            kept_paths=list(resilience_raw.get("kept_paths") or []),
        )
        record_degraded_stage(ctx, stage_key, report)
        log_resilience_event(
            ctx,
            stage_key,
            "degraded_continue",
            report,
            arbiter_result=arbiter_result,
            envelope=envelope,
        )
        ctx.mark_done(stage_key)
        return True

    fh = flow_hardening_cfg(cfg)
    critical = stage_key in ALL_CRITICAL_LLM_STAGES
    if critical and fh.get("strict_critical_stages", True) and not degraded:
        rel = producer_artifact_path(stage_key) or "(no artifact)"
        if (
            fh.get("clarification_before_halt", True)
            and rel != "(no artifact)"
            and ctx.artifact_exists(rel)
        ):
            from interview_mux.artifact_issue_triage import triage_enabled

            if triage_enabled(cfg):
                triage_meta = routing.get("triage") or {}
                ctx.log(
                    f"Stage {stage_key}: deferring hard halt — artifact persisted "
                    f"(open_blocking={triage_meta.get('open_blocking', '?')}).",
                    level="warning",
                    stage=stage_key,
                    detail={"triage": triage_meta},
                )
                ctx.mark_done(stage_key)
                return True
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
