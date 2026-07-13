"""Analysis pipeline orchestration with investigation queue draining."""

from __future__ import annotations

from typing import Any, Callable

from interview_mux.analysis_memory import (
    ORCHESTRATION_PATH,
    drain_open_investigations,
    ensure_analysis_workspace,
    load_queue,
    mark_investigation_done,
    update_completion_from_analysis,
)
from interview_mux.run_context import RunContext

# Stages that use the analysis envelope + memory loop
ANALYSIS_LLM_STAGES = frozenset(
    {
        "speaker_roles",
        "content_context",
        "boundary_detection",
        "segment_classification",
        "content_brief_reanchor",
        "sound_design_palettes",
        "missing_framing",
        "optimal_questions",
    }
)

FLOW_LLM_STAGES = frozenset(
    {
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "transitions",
        "sound_design_plan",
        "sfx_prompt_craft",
        "edl_narrative_audit",
    }
)

ALL_LLM_STAGES = ANALYSIS_LLM_STAGES | FLOW_LLM_STAGES

def max_iterations_for_stage(ctx: RunContext) -> int:
    if ctx.artifact_exists(ORCHESTRATION_PATH):
        orch = ctx.read_json(ORCHESTRATION_PATH)
        return int(orch.get("max_iterations_per_stage", 3))
    return 3

def max_queue_drains(ctx: RunContext) -> int:
    if ctx.artifact_exists(ORCHESTRATION_PATH):
        orch = ctx.read_json(ORCHESTRATION_PATH)
        return int(orch.get("max_queue_drains_per_stage", 5))
    return 5

def max_investigation_reruns_per_kind(cfg: dict[str, Any] | None = None) -> int:
    from interview_mux.llm_flow_hardening import flow_hardening_cfg

    return int(flow_hardening_cfg(cfg).get("max_investigation_reruns_per_kind", 2))

def _investigation_rerun_counts(ctx: RunContext) -> dict[str, int]:
    if not ctx.artifact_exists(ORCHESTRATION_PATH):
        return {}
    orch = ctx.read_json(ORCHESTRATION_PATH)
    raw = orch.get("investigation_rerun_counts") or {}
    return {str(k): int(v) for k, v in raw.items()}

def _record_investigation_rerun(ctx: RunContext, kind: str) -> None:
    ensure_analysis_workspace(ctx)
    orch = ctx.read_json(ORCHESTRATION_PATH) if ctx.artifact_exists(ORCHESTRATION_PATH) else {}
    counts = dict(orch.get("investigation_rerun_counts") or {})
    counts[kind] = int(counts.get(kind, 0)) + 1
    orch["investigation_rerun_counts"] = counts
    ctx.write_json(ORCHESTRATION_PATH, orch, skip_handoff=True)

def process_needs_after_stage(ctx: RunContext, stage_key: str, envelope: dict[str, Any]) -> list[str]:
    """Apply non-blocking needs; return stage ids suggested for rerun."""
    reruns: list[str] = []
    for need in envelope.get("needs") or []:
        ntype = need.get("type")
        if ntype == "rerun_stage" and need.get("stage"):
            reruns.append(str(need["stage"]))
        elif ntype == "operator":
            ctx.log(
                f"Operator input requested ({stage_key}): {need.get('reason', '')}",
                level="warning",
                stage=stage_key,
            )
    return list(dict.fromkeys(reruns))

def llm_stage_runners(ctx: RunContext) -> dict[str, Callable[[], None]]:
    """Lazy-built map of rerunnable LLM stage functions (analysis + delivery)."""
    from interview_mux.pipeline import (
        _analysis_stage_fns,
        _delivery_stage_fns,
    )

    runners: dict[str, Callable[[], None]] = {}
    for name, fn in _analysis_stage_fns(ctx).items():
        if name in ANALYSIS_LLM_STAGES:
            runners[name] = fn
    for name, fn in _delivery_stage_fns(ctx).items():
        if name in FLOW_LLM_STAGES:
            runners[name] = fn
    return runners

def default_specialist_input(ctx: RunContext, parent_stage: str) -> dict[str, Any]:
    """Minimal stage input for specialist passes triggered by the investigation queue."""
    payload: dict[str, Any] = {}
    if ctx.artifact_exists("segments/manifest.json"):
        payload["segments"] = ctx.read_json("segments/manifest.json")
    if ctx.artifact_exists("understanding/content_brief.json"):
        payload["content_brief"] = ctx.read_json("understanding/content_brief.json")
    if parent_stage in {"missing_framing", "optimal_questions"}:
        if ctx.artifact_exists("understanding/gap_evaluations.json"):
            payload["gap_evaluations"] = ctx.read_json("understanding/gap_evaluations.json")
    if parent_stage in {"topic_coverage_audit", "full_master_ranking", "narrative_arc_plan"}:
        if ctx.artifact_exists("master/coverage_audit.json"):
            payload["coverage_audit"] = ctx.read_json("master/coverage_audit.json")
        if ctx.artifact_exists("master/narrative_plan.json"):
            payload["narrative_plan"] = ctx.read_json("master/narrative_plan.json")
    if parent_stage == "full_master_ranking" and ctx.artifact_exists("master/selection.json"):
        payload["selection"] = ctx.read_json("master/selection.json")
    return payload

def apply_needs_reruns(
    ctx: RunContext,
    stage_key: str,
    envelope: dict[str, Any],
    stage_runners: dict[str, Callable[[], None]],
) -> None:
    """Run bounded non-blocking rerun_stage needs from an accepted envelope."""
    reruns = process_needs_after_stage(ctx, stage_key, envelope)
    if not reruns:
        return
    limit = max_queue_drains(ctx)
    for rerun_stage in reruns[:limit]:
        runner = stage_runners.get(rerun_stage)
        if not runner:
            ctx.log(
                f"Need rerun_stage={rerun_stage} from {stage_key} — no runner registered",
                level="warning",
                stage="orchestrator",
            )
            continue
        ctx.log(
            f"Envelope need: re-running {rerun_stage} (from {stage_key})",
            level="info",
            stage="orchestrator",
        )
        runner()

def drain_investigation_queue(
    ctx: RunContext,
    stage_runners: dict[str, Callable[[], None]],
    *,
    specialist_input_fn: Callable[[RunContext, str], dict[str, Any]] | None = None,
) -> None:
    """Run suggested stages or specialists for open investigations (bounded)."""
    from interview_mux.llm_specialists import run_specialist, specialists_enabled

    limit = max_queue_drains(ctx)
    open_items = drain_open_investigations(ctx, limit=limit)
    input_fn = specialist_input_fn or default_specialist_input

    for item in open_items:
        action = item.get("suggested_action") or {}
        action_type = action.get("type")
        parent_stage = action.get("stage")

        if action_type == "run_specialist":
            spec_key = action.get("specialist")
            if not parent_stage or not spec_key:
                continue
            if not specialists_enabled(stage_key=parent_stage):
                ctx.log(
                    f"Investigation {item.get('id')}: specialist {spec_key} skipped (disabled)",
                    level="info",
                    stage="orchestrator",
                )
                continue
            ctx.log(
                f"Investigation {item.get('id')}: running specialist {spec_key} "
                f"on {parent_stage} — {item.get('question', '')[:80]}",
                level="info",
                stage="orchestrator",
            )
            try:
                stage_input = input_fn(ctx, str(parent_stage))
                env = run_specialist(ctx, str(spec_key), str(parent_stage), stage_input)
            except Exception as exc:
                ctx.log(
                    f"Investigation specialist {spec_key} failed: {exc}",
                    level="warning",
                    stage="orchestrator",
                )
                continue
            if not isinstance(env, dict) or env.get("status") not in ("complete", "partial"):
                ctx.log(
                    f"Investigation {item.get('id')}: specialist {spec_key} did not return "
                    f"parseable envelope (status={env.get('status') if isinstance(env, dict) else '?'})",
                    level="warning",
                    stage="orchestrator",
                )
                continue
            mark_investigation_done(ctx, item["id"])
            continue

        st = parent_stage
        if st and st in stage_runners:
            from interview_mux.artifact_completeness import artifact_status
            from interview_mux.llm_flow_hardening import producer_artifact_path

            kind = str(item.get("kind") or "unknown")
            rerun_counts = _investigation_rerun_counts(ctx)
            cap = max_investigation_reruns_per_kind()
            if rerun_counts.get(kind, 0) >= cap:
                ctx.log(
                    f"Investigation {item.get('id')}: rerun cap reached for kind={kind} "
                    f"({cap} max) — skipping {st}",
                    level="warning",
                    stage="orchestrator",
                )
                continue

            rel = producer_artifact_path(st)
            before_status = artifact_status(rel, ctx) if rel else None
            ctx.log(
                f"Investigation {item.get('id')}: re-running {st} — {item.get('question', '')[:80]}",
                level="info",
                stage="orchestrator",
            )
            stage_runners[st]()
            _record_investigation_rerun(ctx, kind)
            after_status = artifact_status(rel, ctx) if rel else None
            improved = ctx.is_done(st) and after_status == "complete"
            if not improved and before_status and after_status and after_status != before_status:
                improved = after_status == "complete"
            if improved:
                mark_investigation_done(ctx, item["id"])
            else:
                ctx.log(
                    f"Investigation {item.get('id')}: {st} rerun did not improve artifact "
                    f"({before_status} → {after_status}) — leaving open",
                    level="warning",
                    stage="orchestrator",
                )

def pre_analysis_init(ctx: RunContext) -> None:
    ensure_analysis_workspace(ctx)
    if ctx.artifact_exists("understanding/analysis_state.json"):
        state = ctx.read_json("understanding/analysis_state.json")
        ident = state.get("interview_identity") or {}
        if not ident.get("source_audio_note"):
            ident["source_audio_note"] = str(ctx.input_audio())
            state["interview_identity"] = ident
            ctx.write_json("understanding/analysis_state.json", state)

def post_analysis_finalize(ctx: RunContext) -> dict[str, Any]:
    completion = update_completion_from_analysis(ctx)
    queue = load_queue(ctx)
    open_count = sum(1 for it in queue.get("items") or [] if it.get("status") == "open")
    ctx.log(
        f"Analysis memory finalized — ready={completion.get('analysis_ready')} "
        f"open_investigations={open_count}",
        level="info",
        stage="orchestrator",
    )
    return completion
