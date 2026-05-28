"""Analysis pipeline orchestration with investigation queue draining."""

from __future__ import annotations

from typing import Any, Callable

from interview_mux.analysis_memory import (
    ORCHESTRATION_PATH,
    drain_open_investigations,
    ensure_analysis_workspace,
    load_queue,
    mark_investigation_done,
    save_queue,
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
        "sound_design_palettes",
        "missing_framing",
        "optimal_questions",
    }
)


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


def drain_investigation_queue(ctx: RunContext, stage_runners: dict[str, Callable[[], None]]) -> None:
    """Run suggested stages for open investigations (bounded)."""
    limit = max_queue_drains(ctx)
    open_items = drain_open_investigations(ctx, limit=limit)
    for item in open_items:
        action = item.get("suggested_action") or {}
        st = action.get("stage")
        if st and st in stage_runners:
            ctx.log(
                f"Investigation {item.get('id')}: re-running {st} — {item.get('question', '')[:80]}",
                level="info",
                stage="orchestrator",
            )
            stage_runners[st]()
            mark_investigation_done(ctx, item["id"])


def pre_analysis_init(ctx: RunContext) -> None:
    ensure_analysis_workspace(ctx)
    state_path = ctx.path("understanding", "analysis_state.json")
    if state_path.is_file():
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
